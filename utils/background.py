import asyncio
import logging
from database.repo import SubRepo
from utils.vless_checker import VlessChecker
from utils.collector import SubscriptionCollector

logger = logging.getLogger(__name__)

class BackgroundTasks:
    _tasks = []

    @classmethod
    async def start_scheduler(cls):
        logger.info("⏳ Background scheduler started.")
        cls._tasks.append(asyncio.create_task(cls.checker_loop(), name="checker"))
        cls._tasks.append(asyncio.create_task(cls.collector_loop(), name="collector"))

    @classmethod
    async def stop(cls):
        logger.info("🛑 Stopping background tasks...")
        
        if not cls._tasks:
            logger.info("✅ No background tasks to stop.")
            return

        for task in cls._tasks:
            if not task.done():
                task.cancel()
        
        # Ждем завершения с таймаутом 5 секунд
        try:
            await asyncio.wait_for(
                asyncio.gather(*cls._tasks, return_exceptions=True),
                timeout=5.0
            )
        except asyncio.TimeoutError:
             logger.warning("⚠️ Background tasks stop timed out! Some tasks might still be running.")
        
        cls._tasks.clear()
        logger.info("✅ Background tasks stopped.")

    @staticmethod
    async def collector_loop():
        while True:
            try: 
                await SubscriptionCollector.run_collection()
            except asyncio.CancelledError:
                logger.info("🛑 Collector loop cancelled.")
                break
            except Exception as e: 
                logger.error(f"❌ Collector error: {e}")
            
            try:
                await asyncio.sleep(3600)
            except asyncio.CancelledError:
                logger.info("🛑 Collector sleep cancelled.")
                break

    @staticmethod
    async def checker_loop():
        while True:
            try:
                logger.info("🔄 Starting periodic subscription check...")
                await BackgroundTasks.check_all_subscriptions()
                logger.info("✅ Periodic check completed. Waiting 10 minutes.")
            except asyncio.CancelledError:
                logger.info("🛑 Checker loop cancelled.")
                break
            except Exception as e:
                logger.error(f"❌ Error in background task: {e}")
            
            try:
                await asyncio.sleep(600)
            except asyncio.CancelledError:
                logger.info("🛑 Checker sleep cancelled.")
                break

    @staticmethod
    async def check_all_subscriptions():
        subs = await SubRepo.get_all_subscriptions_for_check()
        if not subs: return

        queue = asyncio.Queue()
        for sub in subs: queue.put_nowait(sub)

        stats = {"checked": 0, "died": 0, "revived": 0, "total": len(subs)}
        workers = []
        WORKERS_COUNT = 50

        async def worker():
            while True:
                try:
                    sub = queue.get_nowait()
                except asyncio.QueueEmpty:
                    break
                except asyncio.CancelledError:
                    return

                try:
                    is_alive, region, latency, ai_available, err = await VlessChecker.process_subscription(sub.vless_key)

                    should_update = False
                    if sub.is_active and not is_alive:
                        stats["died"] += 1
                        should_update = True
                    elif not sub.is_active and is_alive:
                        stats["revived"] += 1
                        should_update = True
                    elif is_alive and abs(sub.latency_ms - latency) > 50:
                        should_update = True
                    elif sub.ai_available != ai_available:
                        should_update = True

                    if should_update:
                         new_latency = latency if is_alive else 9999
                         await SubRepo.update_sub_status(
                             sub.id, 
                             is_active=is_alive, 
                             latency=new_latency,
                             ai_available=ai_available
                         )
                         
                         if is_alive and region and "Unknown" not in region and sub.region != region:
                             await SubRepo.update_sub_region(sub.id, region)

                except asyncio.CancelledError:
                    raise
                except Exception:
                    pass 
                finally:
                    queue.task_done()

        for _ in range(WORKERS_COUNT):
            workers.append(asyncio.create_task(worker()))

        try:
            await queue.join()
        except asyncio.CancelledError:
            for w in workers: w.cancel()
            raise
        finally:
            for w in workers: w.cancel()
            try:
                await asyncio.wait_for(asyncio.gather(*workers, return_exceptions=True), timeout=3.0)
            except asyncio.TimeoutError:
                pass

        logger.info(f"📊 Report: Checked {stats['total']} | Revived: {stats['revived']} | Died: {stats['died']}")
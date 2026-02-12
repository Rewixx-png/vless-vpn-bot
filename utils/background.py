import asyncio
import logging
from database.repo import SubRepo
from utils.vless_checker import VlessChecker
from utils.collector import SubscriptionCollector

logger = logging.getLogger(__name__)

class BackgroundTasks:
    @staticmethod
    async def start_scheduler():
        logger.info("⏳ Background scheduler started.")
        asyncio.create_task(BackgroundTasks.checker_loop())
        asyncio.create_task(BackgroundTasks.collector_loop())

    @staticmethod
    async def collector_loop():
        while True:
            try: await SubscriptionCollector.run_collection()
            except Exception as e: logger.error(f"❌ Collector error: {e}")
            await asyncio.sleep(3600)

    @staticmethod
    async def checker_loop():
        while True:
            try:
                logger.info("🔄 Starting periodic subscription check...")
                await BackgroundTasks.check_all_subscriptions()
                logger.info("✅ Periodic check completed. Waiting 10 minutes.")
            except Exception as e:
                logger.error(f"❌ Error in background task: {e}")
            await asyncio.sleep(600)

    @staticmethod
    async def check_all_subscriptions():
        subs = await SubRepo.get_all_subscriptions_for_check()
        if not subs: return

        queue = asyncio.Queue()
        for sub in subs: queue.put_nowait(sub)

        stats = {"checked": 0, "died": 0, "revived": 0, "total": len(subs)}

        async def worker():
            while True:
                try:
                    sub = queue.get_nowait()
                except asyncio.QueueEmpty: break
                
                try:
                    # Обновленный вызов check
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
                    elif sub.ai_available != ai_available: # Если статус AI изменился
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

                except Exception as e:
                    logger.error(f"Error checking sub {sub.id}: {e}")
                finally:
                    stats["checked"] += 1
                    queue.task_done()

        workers = [asyncio.create_task(worker()) for _ in range(80)]
        await asyncio.gather(*workers)
        logger.info(f"📊 Report: Checked {stats['total']} | Revived: {stats['revived']} | Died: {stats['died']}")
import asyncio
import logging
from database.repo import SubRepo
import tasks 

logger = logging.getLogger("Scheduler")

class BackgroundTasks:
    _tasks = []

    @classmethod
    async def start_scheduler(cls):
        cls._tasks.append(asyncio.create_task(cls.checker_scheduler(), name="checker_scheduler"))
        cls._tasks.append(asyncio.create_task(cls.collector_scheduler(), name="collector_scheduler"))
        cls._tasks.append(asyncio.create_task(cls.cleanup_scheduler(), name="cleanup_scheduler"))

    @classmethod
    async def stop(cls):
        for task in cls._tasks:
            if not task.done():
                task.cancel()

    @staticmethod
    async def checker_scheduler():
        while True:
            try:
                await BackgroundTasks.dispatch_checks()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"❌ Checker Scheduler Error: {e}")
            
            await asyncio.sleep(300) 

    @staticmethod
    async def collector_scheduler():
        while True:
            try:
                tasks.run_collector_task.delay()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"❌ Collector Scheduler Error: {e}")
            
            await asyncio.sleep(1200)

    @staticmethod
    async def cleanup_scheduler():
        while True:
            try:
                tasks.cleanup_database_task.delay()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"❌ Cleanup Scheduler Error: {e}")
            
            await asyncio.sleep(180)

    @staticmethod
    async def dispatch_checks():
        subs = await SubRepo.get_all_subscriptions_for_check()
        if not subs: 
            return

        BATCH_SIZE = 50
        sub_ids = [sub.id for sub in subs]
        
        batches = [sub_ids[i:i + BATCH_SIZE] for i in range(0, len(sub_ids), BATCH_SIZE)]
        
        for batch in batches:
            tasks.check_subs_batch_task.delay(batch)
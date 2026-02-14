import asyncio
import logging
from database.repo import SubRepo
from tasks import check_subs_batch_task, run_collector_task

logger = logging.getLogger("Scheduler")

class BackgroundTasks:
    _tasks = []

    @classmethod
    async def start_scheduler(cls):
        cls._tasks.append(asyncio.create_task(cls.checker_scheduler(), name="checker_scheduler"))
        cls._tasks.append(asyncio.create_task(cls.collector_scheduler(), name="collector_scheduler"))

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
                logger.error(f"❌ Ошибка планировщика (Checker): {e}")
            
            # Интервал проверки (10 минут)
            await asyncio.sleep(600) 

    @staticmethod
    async def collector_scheduler():
        while True:
            try:
                run_collector_task.delay()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"❌ Ошибка планировщика (Collector): {e}")
            
            # Интервал сбора (1 час)
            await asyncio.sleep(3600)

    @staticmethod
    async def dispatch_checks():
        subs = await SubRepo.get_all_subscriptions_for_check()
        if not subs: 
            return

        BATCH_SIZE = 50
        sub_ids = [sub.id for sub in subs]
        
        batches = [sub_ids[i:i + BATCH_SIZE] for i in range(0, len(sub_ids), BATCH_SIZE)]
        
        for batch in batches:
            check_subs_batch_task.delay(batch)
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
            
            # Проверка базы каждые 5 минут
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
            
            # Сбор новых каждые 20 минут
            await asyncio.sleep(1200)

    @staticmethod
    async def cleanup_scheduler():
        """
        Запускает задачу жесткой очистки лимитов.
        Исправляет последствия Race Condition, когда добавляется больше 100 серверов.
        """
        while True:
            try:
                # Запускаем в high_priority, так как это важно для чистоты базы
                # (По умолчанию задачи идут в low, но check_subs и эта - могли бы в high. 
                #  В celery_app.py мы не прописали роут для cleanup_database_task, значит она пойдет в default=low.
                #  Это нормально, главное чтобы выполнялась).
                tasks.cleanup_database_task.delay()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"❌ Cleanup Scheduler Error: {e}")
            
            # Чистим каждые 3 минуты
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
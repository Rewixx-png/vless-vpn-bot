import asyncio
import logging
from database.repo import SubRepo
from tasks import check_subs_batch_task, run_collector_task

logger = logging.getLogger(__name__)

class BackgroundTasks:
    _tasks = []

    @classmethod
    async def start_scheduler(cls):
        logger.info("⏳ Background scheduler started (Manager Mode).")
        # Теперь планировщик только ОТПРАВЛЯЕТ задачи в Celery, а не выполняет их сам
        cls._tasks.append(asyncio.create_task(cls.checker_scheduler(), name="checker_scheduler"))
        cls._tasks.append(asyncio.create_task(cls.collector_scheduler(), name="collector_scheduler"))

    @classmethod
    async def stop(cls):
        logger.info("🛑 Stopping scheduler...")
        for task in cls._tasks:
            if not task.done():
                task.cancel()
        logger.info("✅ Scheduler stopped.")

    @staticmethod
    async def checker_scheduler():
        """Каждые 10 минут отправляет задачи на проверку в Celery"""
        while True:
            try:
                logger.info("📨 Dispatching check tasks to Celery...")
                await BackgroundTasks.dispatch_checks()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"❌ Scheduler error: {e}")
            
            await asyncio.sleep(600) # 10 минут

    @staticmethod
    async def collector_scheduler():
        """Каждый час отправляет задачу сбора прокси в Celery"""
        while True:
            try:
                logger.info("📨 Dispatching collector task to Celery...")
                run_collector_task.delay() # Отправляем задачу в очередь
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"❌ Collector scheduler error: {e}")
            
            await asyncio.sleep(3600) # 1 час

    @staticmethod
    async def dispatch_checks():
        # Получаем все подписки
        subs = await SubRepo.get_all_subscriptions_for_check()
        if not subs: return

        # Разбиваем на пакеты по 50 штук
        BATCH_SIZE = 50
        sub_ids = [sub.id for sub in subs]
        
        batches = [sub_ids[i:i + BATCH_SIZE] for i in range(0, len(sub_ids), BATCH_SIZE)]
        
        logger.info(f"📦 Sending {len(batches)} batches to Celery queue...")
        
        for batch in batches:
            # .delay() отправляет задачу в Redis
            check_subs_batch_task.delay(batch)
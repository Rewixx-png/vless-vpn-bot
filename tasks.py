import asyncio
import logging
from celery_app import app
from database.repo import SubRepo
from utils.vless_checker import VlessChecker
from utils.collector import SubscriptionCollector

logger = logging.getLogger("CeleryTasks")

# Вспомогательная функция для запуска асинхронного кода внутри синхронного Celery
def run_async(coro):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()

@app.task
def check_subs_batch_task(sub_ids: list[int]):
    """
    Задача: Проверка пакета подписок (например, 50 штук).
    Выполняется в отдельном процессе Celery.
    """
    logger.info(f"🔄 Celery: Checking batch of {len(sub_ids)} subs...")
    
    async def _process():
        # Получаем подписки по ID
        checked_count = 0
        died_count = 0
        revived_count = 0
        
        for sub_id in sub_ids:
            sub = await SubRepo.get_sub_by_id(sub_id)
            if not sub: continue
            
            # Проверяем через VlessChecker
            try:
                is_alive, region, latency, ai_available, err = await VlessChecker.process_subscription(sub.vless_key)
                
                should_update = False
                # Логика обновления статуса
                if sub.is_active and not is_alive:
                    died_count += 1
                    should_update = True
                elif not sub.is_active and is_alive:
                    revived_count += 1
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
                    # Если регион определился точнее
                    if is_alive and region and "Unknown" not in region and sub.region != region:
                        await SubRepo.update_sub_region(sub.id, region)
                        
            except Exception as e:
                logger.error(f"Error checking sub {sub_id}: {e}")
            
            checked_count += 1
            
        logger.info(f"✅ Batch finished: {checked_count} checked | {revived_count} revived | {died_count} died")
        return checked_count

    return run_async(_process())

@app.task
def run_collector_task():
    """
    Задача: Сбор новых прокси из публичных источников.
    """
    logger.info("🚀 Celery: Starting Subscription Collector...")
    run_async(SubscriptionCollector.run_collection())
    logger.info("✅ Celery: Collector finished.")
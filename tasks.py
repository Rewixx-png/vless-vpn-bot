import asyncio
import logging
from celery_app import app
from database.repo import SubRepo
from utils.checker import VlessChecker
from utils.collector import SubscriptionCollector

# Используем имя логгера, который мы настроили (корневой или специфичный)
logger = logging.getLogger("Worker")

def run_async(coro):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()

@app.task
def check_subs_batch_task(sub_ids: list[int]):
    async def _process():
        if not sub_ids:
            return 0

        checked_count = 0
        died_count = 0
        revived_count = 0
        updated_latency = 0
        
        for sub_id in sub_ids:
            sub = await SubRepo.get_sub_by_id(sub_id)
            if not sub: continue
            
            try:
                is_alive, region, latency, ai_available, err = await VlessChecker.process_subscription(sub.vless_key)
                
                should_update = False
                
                if sub.is_active and not is_alive:
                    died_count += 1
                    should_update = True
                elif not sub.is_active and is_alive:
                    revived_count += 1
                    should_update = True
                elif is_alive and abs(sub.latency_ms - latency) > 50:
                    updated_latency += 1
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
                        
            except Exception as e:
                pass 
            
            checked_count += 1
            
        return checked_count

    return run_async(_process())

@app.task
def run_collector_task():
    # Запускаем сборщик без лишнего шума в логах
    run_async(SubscriptionCollector.run_collection())
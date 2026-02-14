"""
Celery tasks with optimized async support and batch processing.
"""
import asyncio
import logging
from typing import List, Dict, Any

from celery_app import app
from utils.async_celery import AsyncTask, AsyncWorkerPool
from utils.batch_processor import SmartBatchProcessor, batch_process
from database.repo import SubRepo
from utils.checker import VlessChecker
from utils.collector import SubscriptionCollector

logger = logging.getLogger("Worker")


class OptimizedTask(AsyncTask):
    """Base task with proper async handling"""
    pass


@app.task(base=OptimizedTask, bind=True, max_retries=3)
async def check_subs_batch_task(self, sub_ids: List[int]) -> Dict[str, Any]:
    """
    Optimized batch check with parallel processing and batch updates.
    Reduces DB calls from N queries to 1 fetch + batch update.
    """
    if not sub_ids:
        return {"checked": 0, "updated": 0, "duration": 0}
    
    start_time = asyncio.get_event_loop().time()
    
    # Fetch all subscriptions in one query
    subs = await SubRepo.get_subs_by_ids(sub_ids)
    if not subs:
        return {"checked": 0, "updated": 0, "duration": 0}
    
    updates_needed = []
    region_updates = []
    checked_count = 0
    
    async def check_one(sub):
        """Check single subscription"""
        nonlocal checked_count
        try:
            is_alive, region, latency, ai_available, err = await VlessChecker.process_subscription(sub.vless_key)
            
            should_update = False
            if sub.is_active != is_alive:
                should_update = True
            elif is_alive and abs(sub.latency_ms - latency) > 50:
                should_update = True
            elif sub.ai_available != ai_available:
                should_update = True
            
            result = {
                "id": sub.id,
                "should_update": should_update,
                "is_active": is_alive,
                "latency": latency if is_alive else 9999,
                "ai_available": ai_available,
                "region": region if is_alive and region and "Unknown" not in region else None
            }
            checked_count += 1
            return result
            
        except Exception as e:
            logger.error(f"Check failed for sub {sub.id}: {e}")
            checked_count += 1
            return None
    
    # Process with limited concurrency
    processor = AsyncWorkerPool(worker_count=20)
    results = await processor.process_batch(subs, check_one)
    
    # Collect updates
    for result in results:
        if not result:
            continue
        
        if result["should_update"]:
            updates_needed.append({
                "id": result["id"],
                "is_active": result["is_active"],
                "latency_ms": result["latency"],
                "ai_available": result["ai_available"]
            })
        
        if result["region"]:
            region_updates.append({
                "id": result["id"],
                "region": result["region"]
            })
    
    # Batch updates - reduces DB calls significantly
    if updates_needed:
        await SubRepo.batch_update_status(updates_needed)
    
    if region_updates:
        await SubRepo.batch_update_regions(region_updates)
    
    duration = asyncio.get_event_loop().time() - start_time
    
    logger.info(f"Batch check completed: {checked_count} checked, {len(updates_needed)} updated in {duration:.2f}s")
    
    return {
        "checked": checked_count,
        "updated": len(updates_needed),
        "duration": duration
    }


@app.task(base=OptimizedTask)
async def run_collector_task() -> Dict[str, Any]:
    """Optimized collector with progress tracking"""
    start_time = asyncio.get_event_loop().time()
    
    try:
        result = await SubscriptionCollector.run_collection()
        duration = asyncio.get_event_loop().time() - start_time
        
        logger.info(f"Collection completed in {duration:.2f}s")
        return {
            "success": True,
            "duration": duration,
            "result": result
        }
    except Exception as e:
        logger.error(f"Collection failed: {e}")
        raise


@app.task(base=OptimizedTask)
async def cleanup_database_task() -> Dict[str, Any]:
    """Database cleanup with limits enforcement"""
    start_time = asyncio.get_event_loop().time()
    
    try:
        await SubRepo.enforce_limits()
        duration = asyncio.get_event_loop().time() - start_time
        
        logger.info(f"Cleanup completed in {duration:.2f}s")
        return {
            "success": True,
            "duration": duration
        }
    except Exception as e:
        logger.error(f"Cleanup failed: {e}")
        raise


# Legacy wrapper for compatibility (to be removed after migration)
def run_async_legacy(coro):
    """Legacy wrapper - deprecated, use async tasks directly"""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()

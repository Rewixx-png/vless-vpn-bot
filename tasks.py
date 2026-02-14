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
    Batch check with detailed logging. Only marks as inactive, NEVER deletes.
    """
    logger.info(f"[CHECKER] Starting batch check for {len(sub_ids)} subscriptions")
    
    if not sub_ids:
        return {"checked": 0, "updated": 0, "duration": 0}
    
    start_time = asyncio.get_event_loop().time()
    
    # Fetch all subscriptions in one query
    subs = await SubRepo.get_subs_by_ids(sub_ids)
    if not subs:
        logger.warning("[CHECKER] No subscriptions found for check")
        return {"checked": 0, "updated": 0, "duration": 0}
    
    updates_needed = []
    region_updates = []
    checked_count = 0
    alive_count = 0
    died_count = 0
    revived_count = 0
    
    async def check_one(sub):
        """Check single subscription with detailed logging"""
        nonlocal checked_count, alive_count, died_count, revived_count
        try:
            logger.debug(f"[CHECKER] Checking sub {sub.id} - Current status: {'ALIVE' if sub.is_active else 'DEAD'}")
            is_alive, region, latency, ai_available, err = await VlessChecker.process_subscription(sub.vless_key)
            
            should_update = False
            status_changed = False
            
            current_death_count = sub.death_count or 0
            
            if sub.is_active != is_alive:
                should_update = True
                status_changed = True
                if is_alive:
                    revived_count += 1
                    logger.info(f"[CHECKER] REVIVED - Sub {sub.id} is now ALIVE ({region}, {latency}ms)")
                    current_death_count = 0
                else:
                    current_death_count += 1
                    if current_death_count >= 2:
                        died_count += 1
                        logger.info(f"[CHECKER] DIED - Sub {sub.id} is now DEAD (Error: {err})")
                    else:
                        logger.info(f"[CHECKER] WARNING - Sub {sub.id} failed check ({current_death_count}/2) - keeping alive")
            elif is_alive and abs(sub.latency_ms - latency) > 50:
                should_update = True
                logger.debug(f"[CHECKER] LATENCY CHANGE - Sub {sub.id}: {sub.latency_ms}ms -> {latency}ms")
            elif sub.ai_available != ai_available:
                should_update = True
                logger.debug(f"[CHECKER] AI STATUS CHANGE - Sub {sub.id}: AI={ai_available}")
            
            if is_alive:
                alive_count += 1
            
            result = {
                "id": sub.id,
                "should_update": should_update,
                "is_active": is_alive,
                "latency": latency if is_alive else 9999,
                "ai_available": ai_available,
                "region": region if is_alive and region and "Unknown" not in region else None,
                "status_changed": status_changed,
                "death_count": current_death_count
            }
            checked_count += 1
            return result
            
        except Exception as e:
            logger.error(f"[CHECKER] ERROR checking sub {sub.id}: {e}")
            checked_count += 1
            return None
    
    # Process with limited concurrency
    processor = AsyncWorkerPool(worker_count=10)
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
                "ai_available": result["ai_available"],
                "death_count": result.get("death_count", 0)
            })
        
        if result["region"]:
            region_updates.append({
                "id": result["id"],
                "region": result["region"]
            })
    
    # Batch updates - reduces DB calls significantly
    if updates_needed:
        logger.warning(f"[CHECKER] Updating {len(updates_needed)} subs")
        await SubRepo.batch_update_status(updates_needed)
    
    if region_updates:
        logger.warning(f"[CHECKER] Updating regions for {len(region_updates)} subs")
        await SubRepo.batch_update_regions(region_updates)
    
    duration = asyncio.get_event_loop().time() - start_time
    
    logger.warning(f"✅ Check done: {alive_count} alive, {died_count} died, {revived_count} revived ({duration:.1f}s)")
    
    return {
        "checked": checked_count,
        "updated": len(updates_needed),
        "alive": alive_count,
        "died": died_count,
        "revived": revived_count,
        "duration": duration
    }


@app.task(base=OptimizedTask)
async def run_collector_task() -> Dict[str, Any]:
    """Collector task"""
    logger.warning("🔄 Starting collection...")
    start_time = asyncio.get_event_loop().time()
    
    try:
        result = await SubscriptionCollector.run_collection()
        duration = asyncio.get_event_loop().time() - start_time
        
        logger.warning(f"✅ Collection done in {duration:.1f}s: +{result.get('added', 0)} added")
        logger.info("=" * 60)
        logger.info(f"Duration: {duration:.2f}s")
        logger.info(f"Links processed: {result.get('processed', 0)}")
        logger.info(f"Configs added: {result.get('added', 0)}")
        logger.info(f"Dead configs: {result.get('dead', 0)}")
        logger.info(f"Rejected: {result.get('rejected', 0)}")
        logger.info("=" * 60)
        
        return {
            "success": True,
            "duration": duration,
            "result": result
        }
    except Exception as e:
        logger.error(f"[COLLECTOR TASK] Collection failed: {e}")
        raise


@app.task(base=OptimizedTask)
async def cleanup_database_task() -> Dict[str, Any]:
    """Database cleanup - SAFE MODE"""
    start_time = asyncio.get_event_loop().time()
    
    try:
        await SubRepo.enforce_limits()
        duration = asyncio.get_event_loop().time() - start_time
        
        return {
            "success": True,
            "duration": duration,
            "deleted": 0,
            "mode": "safe"
        }
    except Exception as e:
        logger.error(f"[CLEANUP] Error: {e}")
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

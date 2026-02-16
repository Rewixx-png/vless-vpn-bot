"""
Celery tasks for collector.
"""
import asyncio
import logging
from typing import Dict, Any

from celery_app import app
from utils.async_celery import AsyncTask
from utils.collector import SubscriptionCollector

logger = logging.getLogger("Worker")


class OptimizedTask(AsyncTask):
    """Base task with proper async handling"""
    pass


@app.task(base=OptimizedTask, bind=True, max_retries=3)
async def check_subs_batch_task(self, sub_ids: list) -> Dict[str, Any]:
    """DEPRECATED - checker is disabled"""
    logger.warning("[CHECKER] Checker is disabled")
    return {"checked": 0, "updated": 0, "status": "disabled"}


@app.task(base=OptimizedTask)
async def run_collector_task() -> Dict[str, Any]:
    """Collector task - runs 24/7"""
    logger.warning("🔄 Starting collection...")
    start_time = asyncio.get_event_loop().time()
    
    try:
        result = await SubscriptionCollector.run_collection()
        duration = asyncio.get_event_loop().time() - start_time
        
        added = result.get('added', 0) if isinstance(result, dict) else 0
        logger.warning(f"✅ Collection done in {duration:.1f}s: +{added} added")
        
        return {
            "success": True,
            "duration": duration,
            "result": result
        }
    except Exception as e:
        logger.error(f"[COLLECTOR TASK] Collection failed: {e}")
        raise

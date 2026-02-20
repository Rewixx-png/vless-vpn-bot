import asyncio
import logging
from typing import Dict, Any

from celery_app import app
from utils.async_celery import AsyncTask
from utils.collector import SubscriptionCollector
from database.repo import SubRepo, SystemRepo
from utils.checker import VlessChecker
from utils.batch_processor import SmartBatchProcessor
from utils.state import BotState

logger = logging.getLogger("Worker")


class OptimizedTask(AsyncTask):
    pass


@app.task(base=OptimizedTask, bind=True, max_retries=3)
async def check_subs_batch_task(self, sub_ids: list) -> Dict[str, Any]:
    logger.warning("[CHECKER] Checker is disabled")
    return {"status": "disabled"}


@app.task(base=OptimizedTask)
async def run_collector_task() -> Dict[str, Any]:
    if BotState.is_maintenance():
        logger.warning("⏸️ Collector aborted: Maintenance Mode is Active")
        return {"status": "skipped", "reason": "maintenance"}

    enabled_str = await SystemRepo.get_config("collector_enabled")
    if enabled_str == "false":
        logger.warning("⏸️ Collector aborted: Disabled by Admin")
        return {"status": "skipped", "reason": "admin_disabled"}

    logger.warning("🔄 Starting collection...")
    start_time = asyncio.get_event_loop().time()
    
    try:
        result = await SubscriptionCollector.run_collection()
        cleaned = await SubRepo.cleanup_dead_subs(max_deaths=3)
        logger.warning(f"🧹 Cleaned up {cleaned} dead subscriptions.")
        duration = asyncio.get_event_loop().time() - start_time
        return {"success": True, "duration": duration, "result": result, "cleaned": cleaned}
    except Exception as e:
        logger.error(f"[COLLECTOR TASK] Collection failed: {e}")
        raise

@app.task(base=OptimizedTask)
async def check_stability_task() -> Dict[str, Any]:
    if BotState.is_maintenance():
        logger.warning("⏸️ Stability Check aborted: Maintenance Mode is Active")
        return {"status": "skipped", "reason": "maintenance"}

    logger.warning("🛡 Starting Stability Check...")
    
    subs = await SubRepo.get_candidates_for_stability()
    if not subs:
        logger.warning("🛡 No candidates for stability check.")
        return {"checked": 0}

    logger.warning(f"🛡 Checking {len(subs)} candidates for stability...")

    processor = SmartBatchProcessor(worker_count=50)
    
    results_buffer = []
    
    async def check_one(sub):
        try:
            is_alive, _, latency, speed_mbps, _, _ = await VlessChecker.process_subscription(sub.vless_key)
            return (True, {"id": sub.id, "is_alive": is_alive, "latency": latency, "speed_mbps": speed_mbps})
        except:
            return (True, {"id": sub.id, "is_alive": False, "latency": 9999, "speed_mbps": 0.0})

    batch_res = await processor.process(
        items=subs,
        process_func=check_one
    )
    
    updates = [item["result"] for item in batch_res.items if item["success"]]
    
    if updates:
        await SubRepo.batch_update_stability(updates)
        status_updates = [
            {
                "id": u["id"], 
                "is_active": u["is_alive"], 
                "latency_ms": u["latency"],
                "speed_mbps": u["speed_mbps"],
                "ai_available": False
            } 
            for u in updates
        ]
        await SubRepo.batch_update_status(status_updates)
        
        cleaned = await SubRepo.cleanup_dead_subs(max_deaths=3)
        logger.warning(f"🧹 Cleaned up {cleaned} dead subscriptions after stability check.")

    logger.warning(f"✅ Stability Check Done. Checked: {len(updates)}")
    return {"checked": len(updates)}

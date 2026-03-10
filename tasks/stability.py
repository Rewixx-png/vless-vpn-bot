import asyncio
from typing import Dict, Any

from celery_app import app
from tasks.base import (
    OptimizedTask,
    setup_log_rotation,
    _setup_loop_exception_handler,
    logger,
)
from database.repo import SubRepo, StatsRepo
from utils.checker import VlessChecker
from utils.batch_processor import SmartBatchProcessor
from utils.state import BotState
from utils.smart_alerts import SmartAlerts
from config import config


@app.task(
    name="tasks.check_stability_task",
    base=OptimizedTask,
    time_limit=3600,
    soft_time_limit=3540,
)
async def check_stability_task() -> Dict[str, Any]:
    setup_log_rotation()
    _setup_loop_exception_handler()

    is_maint = await BotState.is_maintenance()
    if is_maint:
        return {"status": "skipped", "reason": "maintenance"}

    subs = await SubRepo.get_candidates_for_stability()
    if not subs:
        return {"checked": 0}

    worker_count = min(config.MAX_WORKERS, max(config.MIN_WORKERS, len(subs) // 10))
    processor = SmartBatchProcessor(worker_count=worker_count)

    old_counts = await StatsRepo.get_regions_counts()

    def check_one(sub):
        async def _check():
            try:
                (
                    is_alive,
                    _,
                    latency,
                    speed_mbps,
                    ai_avail,
                    no_ads,
                    err,
                    _,
                ) = await VlessChecker.process_subscription(sub.vless_key)

                is_standard_err = err and any(
                    f"Factor {i}" in str(err) for i in range(1, 7)
                )
                if not is_alive and not is_standard_err:
                    return (True, None)

                return (
                    True,
                    {
                        "id": sub.id,
                        "is_alive": is_alive,
                        "latency": latency,
                        "speed_mbps": speed_mbps,
                        "ai": ai_avail,
                        "no_ads": no_ads,
                    },
                )
            except asyncio.CancelledError:
                raise
            except Exception:
                return (True, None)

        return _check()

    try:
        batch_res = await processor.process(
            items=subs, process_func=check_one, collect_results=True
        )

        updates = [
            item["result"]
            for item in batch_res.items
            if item["success"] and item["result"] is not None
        ]

        if updates:
            await SubRepo.batch_update_stability(updates)
            status_updates = [
                {
                    "id": u["id"],
                    "is_active": u["is_alive"],
                    "was_active": True,
                    "latency_ms": u["latency"],
                    "speed_mbps": u["speed_mbps"],
                    "ai_available": u["ai"],
                    "no_ads": u["no_ads"],
                }
                for u in updates
            ]
            await SubRepo.batch_update_status(status_updates)
            await SubRepo.cleanup_dead_subs(max_deaths=10)

        new_counts = await StatsRepo.get_regions_counts()
        await SmartAlerts.process_changes(old_counts, new_counts)

        return {"checked": len(updates)}
    except Exception as e:
        if "SoftTimeLimitExceeded" in type(e).__name__:
            logger.warning("Stability check hit SoftTimeLimitExceeded.")
            return {"status": "timeout_graceful"}
        raise

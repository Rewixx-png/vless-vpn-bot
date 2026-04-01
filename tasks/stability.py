import asyncio
import uuid
from typing import Dict, Any

from aiogram import Bot
from aiogram.client.session.aiohttp import AiohttpSession
import redis.asyncio as redis

from celery_app import app
from tasks.base import (
    OptimizedTask,
    setup_log_rotation,
    _setup_loop_exception_handler,
    logger,
)
from database.repo import SubRepo, StatsRepo, SystemRepo
from utils.checker import VlessChecker
from utils.batch_processor import SmartBatchProcessor
from utils.state import BotState
from utils.smart_alerts import SmartAlerts
from utils.reporter import Reporter
from config import config


STABILITY_LOCK_KEY = "lock:tasks:check_stability"
STABILITY_LOCK_TTL_SEC = 3900
STABILITY_CANDIDATES_LIMIT = 80
STABILITY_MIN_WORKERS = 3
STABILITY_MAX_WORKERS = 8
STABILITY_SOFT_FAIL_FACTORS = ("Factor 3", "Factor 4", "Factor 5")
STABILITY_RETRY_DELAY_SEC = 0.35


def _is_soft_failure(err: str) -> bool:
    err_text = str(err or "")
    return any(marker in err_text for marker in STABILITY_SOFT_FAIL_FACTORS)


async def _acquire_stability_lock() -> tuple[redis.Redis | None, str | None]:
    client = None
    try:
        client = redis.from_url(config.REDIS_URL, decode_responses=True)
        token = uuid.uuid4().hex
        acquired = await client.set(
            STABILITY_LOCK_KEY,
            token,
            ex=STABILITY_LOCK_TTL_SEC,
            nx=True,
        )
        if acquired:
            return client, token
    except Exception:
        pass

    if client is not None:
        try:
            await client.close()
        except Exception:
            pass
    return None, None


async def _release_stability_lock(client: redis.Redis | None, token: str | None) -> None:
    if client is None or token is None:
        return

    try:
        await client.eval(
            "if redis.call('get', KEYS[1]) == ARGV[1] then "
            "return redis.call('del', KEYS[1]) else return 0 end",
            1,
            STABILITY_LOCK_KEY,
            token,
        )
    except Exception:
        pass
    finally:
        try:
            await client.close()
        except Exception:
            pass


@app.task(
    name="tasks.check_stability_task",
    base=OptimizedTask,
    time_limit=3600,
    soft_time_limit=3540,
)
async def check_stability_task() -> Dict[str, Any]:
    setup_log_rotation()
    _setup_loop_exception_handler()

    bot = Bot(token=config.BOT_TOKEN.get_secret_value(), session=AiohttpSession())
    lock_client = None
    lock_token = None

    is_maint = await BotState.is_maintenance()
    if is_maint:
        await Reporter.send_stability_log(
            bot,
            "Stability check skipped: maintenance mode is enabled",
        )
        await bot.session.close()
        return {"status": "skipped", "reason": "maintenance"}

    stability_enabled = await SystemRepo.get_config("stability_enabled")
    if stability_enabled == "false":
        await Reporter.send_stability_log(
            bot,
            "Stability check skipped: disabled by admin flag (stability_enabled=false)",
        )
        await bot.session.close()
        return {"status": "skipped", "reason": "admin_disabled"}

    lock_client, lock_token = await _acquire_stability_lock()
    if lock_client is None:
        await Reporter.send_stability_log(
            bot,
            "Stability check skipped: previous run is still active",
        )
        await bot.session.close()
        return {"status": "skipped", "reason": "already_running"}

    subs = await SubRepo.get_candidates_for_stability(limit=STABILITY_CANDIDATES_LIMIT)
    if not subs:
        await Reporter.send_stability_log(bot, "Stability check skipped: no candidates")
        await _release_stability_lock(lock_client, lock_token)
        await bot.session.close()
        return {"checked": 0}

    worker_cap = min(config.MAX_WORKERS, STABILITY_MAX_WORKERS)
    worker_floor = min(worker_cap, max(1, STABILITY_MIN_WORKERS))
    auto_workers = max(1, len(subs) // 25)
    worker_count = max(worker_floor, min(worker_cap, auto_workers))
    processor = SmartBatchProcessor(worker_count=worker_count)

    old_counts = await StatsRepo.get_regions_counts()

    await Reporter.send_stability_log(
        bot,
        f"Stability check started: candidates={len(subs)}, workers={worker_count}",
    )

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

                if not is_alive and _is_soft_failure(err):
                    await asyncio.sleep(STABILITY_RETRY_DELAY_SEC)
                    (
                        retry_alive,
                        _,
                        retry_latency,
                        retry_speed,
                        retry_ai,
                        retry_no_ads,
                        retry_err,
                        _,
                    ) = await VlessChecker.process_subscription(sub.vless_key)

                    retry_standard_err = retry_err and any(
                        f"Factor {i}" in str(retry_err) for i in range(1, 7)
                    )

                    if not retry_alive and _is_soft_failure(retry_err):
                        return (True, None)

                    if not retry_alive and not retry_standard_err:
                        return (True, None)

                    is_alive = retry_alive
                    latency = retry_latency
                    speed_mbps = retry_speed
                    ai_avail = retry_ai
                    no_ads = retry_no_ads

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
            await SubRepo.cleanup_dead_subs(max_deaths=20)

        new_counts = await StatsRepo.get_regions_counts()
        await SmartAlerts.process_changes(old_counts, new_counts)

        await Reporter.send_stability_log(
            bot,
            f"Stability check finished: candidates={len(subs)}, checked={len(updates)}",
        )

        return {"checked": len(updates)}
    except Exception as e:
        if "SoftTimeLimitExceeded" in type(e).__name__:
            logger.warning("Stability check hit SoftTimeLimitExceeded.")
            await Reporter.send_stability_log(
                bot,
                "Stability check hit soft time limit and exited gracefully",
            )
            return {"status": "timeout_graceful"}
        await Reporter.send_error(bot, f"Stability task failed: {e}")
        await Reporter.send_stability_log(bot, f"Stability task failed: {e}")
        raise
    finally:
        await _release_stability_lock(lock_client, lock_token)
        try:
            await bot.session.close()
        except Exception:
            pass

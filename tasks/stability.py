import asyncio
import uuid
from typing import Dict, Any, cast

import redis.asyncio as redis

from celery_app import app
from tasks.base import (
    OptimizedTask,
    setup_log_rotation,
    setup_loop_exception_handler_async,
    logger,
)
from database.repo import SubRepo, StatsRepo, SystemRepo
from utils.checker import VlessChecker
from utils.batch_processor import SmartBatchProcessor
from utils.state import BotState
from utils.smart_alerts import SmartAlerts
from utils.reporter import Reporter
from config import config, make_bot


STABILITY_LOCK_KEY = "lock:tasks:check_stability"
STABILITY_LOCK_TTL_SEC = 3900
COLLECTOR_LOCK_KEY = "lock:tasks:collector"
COLLECTOR_WAIT_MAX_SEC = 300
STABILITY_MIN_WORKERS = 10
STABILITY_MAX_WORKERS = 50
STABILITY_MAX_JITTER_MS = 80
STABILITY_MIN_SPEED_MBPS = 2.0


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
    except Exception as e:
        logger.warning(f"_acquire_stability_lock error: {e}")

    if client is not None:
        try:
            await client.close()
        except Exception as e:
            logger.warning(f"_acquire_stability_lock close error: {e}")
    return None, None


async def _release_stability_lock(client: redis.Redis | None, token: str | None) -> None:
    if client is None or token is None:
        return

    try:
        await cast(Any, client).eval(
            "if redis.call('get', KEYS[1]) == ARGV[1] then "
            "return redis.call('del', KEYS[1]) else return 0 end",
            1,
            STABILITY_LOCK_KEY,
            token,
        )
    except Exception as e:
        logger.warning(f"_release_stability_lock error: {e}")
    finally:
        try:
            await client.close()
        except Exception as e:
            logger.warning(f"_release_stability_lock close error: {e}")


async def _is_collector_running() -> bool:
    client = None
    try:
        client = redis.from_url(config.REDIS_URL, decode_responses=True)
        value = await client.get(COLLECTOR_LOCK_KEY)
        return bool(value)
    except Exception:
        return False
    finally:
        if client is not None:
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
    await setup_loop_exception_handler_async()

    lock_client = None
    lock_token = None
    bot = make_bot()
    try:
        is_maint = await BotState.is_maintenance()
        if is_maint:
            await Reporter.send_stability_log(
                bot,
                "Stability check skipped: maintenance mode is enabled",
            )
            return {"status": "skipped", "reason": "maintenance"}

        stability_enabled = await SystemRepo.get_config("stability_enabled")
        if stability_enabled == "false":
            await Reporter.send_stability_log(
                bot,
                "Stability check skipped: disabled by admin flag (stability_enabled=false)",
            )
            return {"status": "skipped", "reason": "admin_disabled"}

        lock_client, lock_token = await _acquire_stability_lock()
        if lock_client is None:
            await Reporter.send_stability_log(
                bot,
                "Stability check skipped: previous run is still active",
            )
            return {"status": "skipped", "reason": "already_running"}

        if await _is_collector_running():
            await Reporter.send_stability_log(
                bot,
                "Stability full recheck is waiting for collector run to finish",
            )
            waited = 0
            while waited < COLLECTOR_WAIT_MAX_SEC and await _is_collector_running():
                await asyncio.sleep(10)
                waited += 10

            if await _is_collector_running():
                await Reporter.send_stability_log(
                    bot,
                    "Collector is still running; stability full recheck proceeds in parallel",
                )

        subs = await SubRepo.get_all_subscriptions_for_check()
        if not subs:
            await Reporter.send_stability_log(bot, "Stability check skipped: no candidates")
            return {"checked": 0}

        worker_cap = min(config.MAX_WORKERS, STABILITY_MAX_WORKERS)
        worker_floor = min(worker_cap, max(1, STABILITY_MIN_WORKERS))
        auto_workers = max(1, len(subs) // 25)
        worker_count = max(worker_floor, min(worker_cap, auto_workers))
        processor = SmartBatchProcessor(worker_count=worker_count)

        old_counts = await StatsRepo.get_regions_counts()

        await Reporter.send_stability_log(
            bot,
            f"Stability full recheck started: total={len(subs)}, workers={worker_count}",
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
                    ) = await VlessChecker.process_subscription(
                        sub.vless_key,
                        strict_speed=False,
                        skip_speed=sub.vless_key.split("://", 1)[0].lower() not in ("hy2", "hysteria2"),
                    )

                    err_text = str(err or "")
                    is_standard_err = any(
                        f"Factor {i}" in err_text for i in range(0, 7)
                    )

                    if not is_alive and (
                        err_text.startswith("SYS_ERR") or not is_standard_err
                    ):
                        return (
                            True,
                            {
                                "id": sub.id,
                                "check_status": "sys_err",
                            },
                        )

                    if is_alive:
                        parsed = VlessChecker.parse_config(sub.vless_key)
                        if not parsed:
                            return (
                                True,
                                {
                                    "id": sub.id,
                                    "check_status": "dead",
                                },
                            )

                        jitter_host = str(parsed.get("server", "") or "").strip()
                        jitter_port = int(parsed.get("port", 0) or 0)
                        if not jitter_host or jitter_port < 1 or jitter_port > 65535:
                            return (
                                True,
                                {
                                    "id": sub.id,
                                    "check_status": "dead",
                                },
                            )

                        jitter_ok, jitter_ms, jitter_err = await VlessChecker.measure_tcp_jitter(
                            host=jitter_host,
                            port=jitter_port,
                        )

                        if not jitter_ok:
                            if str(jitter_err or "").startswith("Factor 1"):
                                return (
                                    True,
                                    {
                                        "id": sub.id,
                                        "check_status": "dead",
                                    },
                                )
                            return (
                                True,
                                {
                                    "id": sub.id,
                                    "check_status": "sys_err",
                                },
                            )

                        if int(jitter_ms) > STABILITY_MAX_JITTER_MS:
                            return (
                                True,
                                {
                                    "id": sub.id,
                                    "check_status": "dead",
                                },
                            )

                        measured_speed = float(speed_mbps or 0.0)
                        if measured_speed <= 1.05:
                            measured_speed = 30.0

                        if measured_speed < STABILITY_MIN_SPEED_MBPS:
                            return (
                                True,
                                {
                                    "id": sub.id,
                                    "check_status": "dead",
                                },
                            )

                        return (
                            True,
                            {
                                "id": sub.id,
                                "check_status": "alive",
                                "is_alive": True,
                                "latency": int(latency)
                                if isinstance(latency, int)
                                else 9999,
                                "speed_mbps": measured_speed,
                                "ai": bool(ai_avail),
                                "no_ads": bool(no_ads),
                            },
                        )

                    return (
                        True,
                        {
                            "id": sub.id,
                            "check_status": "dead",
                        },
                    )
                except asyncio.CancelledError:
                    raise
                except Exception:
                    return (
                        True,
                        {
                            "id": sub.id,
                            "check_status": "sys_err",
                        },
                    )

            return _check()

        try:
            batch_res = await processor.process(
                items=subs, process_func=cast(Any, check_one), collect_results=True
            )

            updates = [
                item["result"]
                for item in batch_res.items
                if item["success"] and item["result"] is not None
            ]

            removed_dead = 0
            sys_err_count = 0

            if updates:
                alive_updates = [u for u in updates if u.get("check_status") == "alive"]
                dead_ids = [
                    int(u["id"])
                    for u in updates
                    if u.get("check_status") == "dead" and int(u.get("id", 0) or 0) > 0
                ]
                sys_err_count = len(
                    [u for u in updates if u.get("check_status") == "sys_err"]
                )

                if alive_updates:
                    await SubRepo.batch_update_stability(alive_updates)

                status_updates = [
                    {
                        "id": u["id"],
                        "check_status": str(u.get("check_status", "dead")),
                        "is_active": bool(u.get("is_alive", False)),
                        "latency_ms": int(u.get("latency", 9999)),
                        "speed_mbps": float(u.get("speed_mbps", 0.0) or 0.0),
                        "ai_available": bool(u.get("ai", False)),
                        "no_ads": bool(u.get("no_ads", False)),
                    }
                    for u in updates
                    if u.get("check_status") in {"alive", "sys_err"}
                ]

                if status_updates:
                    await SubRepo.batch_update_status(status_updates)

                if dead_ids:
                    removed_dead = await SubRepo.delete_subs_by_ids(dead_ids)

                await SubRepo.cleanup_dead_subs(max_deaths=10)

            new_counts = await StatsRepo.get_regions_counts()
            await SmartAlerts.process_changes(old_counts, new_counts)

            await Reporter.send_stability_log(
                bot,
                "Stability full recheck finished: "
                f"total={len(subs)}, checked={len(updates)}, "
                f"alive={len([u for u in updates if u.get('check_status') == 'alive'])}, "
                f"removed_dead={removed_dead}, sys_err={sys_err_count}",
            )

            return {
                "checked": len(updates),
                "removed_dead": removed_dead,
                "sys_err": sys_err_count,
            }
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

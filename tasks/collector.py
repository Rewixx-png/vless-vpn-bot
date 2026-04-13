import asyncio
import json
from typing import Dict, Any
import uuid

import redis.asyncio as redis

from celery_app import app
from tasks.base import (
    OptimizedTask,
    setup_log_rotation,
    _setup_loop_exception_handler,
    logger,
)
from utils.collector import SubscriptionCollector, FIXED_SOURCE_URLS
from database.repo import SubRepo, SystemRepo, StatsRepo
from utils.state import BotState
from utils.smart_alerts import SmartAlerts
from utils.reporter import Reporter
from config import config

from aiogram import Bot
from aiogram.client.session.aiohttp import AiohttpSession


COLLECTOR_LOCK_KEY = "lock:tasks:collector"
COLLECTOR_LOCK_TTL_SEC = 3900
STABILITY_LOCK_KEY = "lock:tasks:check_stability"


async def _get_active_collector_task_ids() -> tuple[bool, set[str]]:
    loop = asyncio.get_running_loop()

    def _inspect() -> tuple[bool, set[str]]:
        try:
            inspector = app.control.inspect(timeout=1)
            active_data = inspector.active() or {}
        except Exception:
            return False, set()

        ids: set[str] = set()
        for tasks in active_data.values():
            if not isinstance(tasks, list):
                continue
            for task in tasks:
                if not isinstance(task, dict):
                    continue
                if task.get("name") != "tasks.run_collector_task":
                    continue
                task_id = str(task.get("id", "") or "").strip()
                if task_id:
                    ids.add(task_id)
        return True, ids

    return await loop.run_in_executor(None, _inspect)


async def _acquire_collector_lock(
    current_task_id: str | None,
) -> tuple[redis.Redis | None, str | None]:
    client = None
    try:
        client = redis.from_url(config.REDIS_URL, decode_responses=True)
        token = str(current_task_id or "").strip() or uuid.uuid4().hex
        acquired = await client.set(
            COLLECTOR_LOCK_KEY,
            token,
            ex=COLLECTOR_LOCK_TTL_SEC,
            nx=True,
        )
        if acquired:
            return client, token

        inspect_ok, active_ids = await _get_active_collector_task_ids()
        if inspect_ok:
            current_id = str(current_task_id or "").strip()
            other_active = {
                task_id for task_id in active_ids if task_id and task_id != current_id
            }

            if not other_active:
                await client.delete(COLLECTOR_LOCK_KEY)
                acquired = await client.set(
                    COLLECTOR_LOCK_KEY,
                    token,
                    ex=COLLECTOR_LOCK_TTL_SEC,
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


async def _release_collector_lock(client: redis.Redis | None, token: str | None) -> None:
    if client is None or token is None:
        return

    try:
        await client.eval(
            "if redis.call('get', KEYS[1]) == ARGV[1] then "
            "return redis.call('del', KEYS[1]) else return 0 end",
            1,
            COLLECTOR_LOCK_KEY,
            token,
        )
    except Exception:
        pass
    finally:
        try:
            await client.close()
        except Exception:
            pass


async def _is_stability_running() -> bool:
    client = None
    try:
        client = redis.from_url(config.REDIS_URL, decode_responses=True)
        value = await client.get(STABILITY_LOCK_KEY)
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
    name="tasks.run_collector_task",
    base=OptimizedTask,
    time_limit=3600,
    soft_time_limit=3540,
)
async def run_collector_task() -> Dict[str, Any]:
    setup_log_rotation()
    _setup_loop_exception_handler()

    bot_instance = Bot(
        token=config.BOT_TOKEN.get_secret_value(),
        session=AiohttpSession(),
    )

    is_maint = await BotState.is_maintenance()
    if is_maint:
        await Reporter.send_collector_log(
            bot_instance,
            "Collector skipped: maintenance mode is enabled",
        )
        await bot_instance.session.close()
        return {"status": "skipped", "reason": "maintenance"}

    enabled_str = await SystemRepo.get_config("collector_enabled")
    if enabled_str == "false":
        await Reporter.send_collector_log(
            bot_instance,
            "Collector skipped: disabled by admin flag (collector_enabled=false)",
        )
        await bot_instance.session.close()
        return {"status": "skipped", "reason": "admin_disabled"}

    start_time = asyncio.get_event_loop().time()
    result = {}
    lock_client = None
    lock_token = None
    current_task_id = str(getattr(run_collector_task.request, "id", "") or "").strip()

    lock_client, lock_token = await _acquire_collector_lock(current_task_id=current_task_id)
    if lock_client is None:
        await Reporter.send_collector_log(
            bot_instance,
            "Collector skipped: previous run is still active",
        )
        await bot_instance.session.close()
        return {"status": "skipped", "reason": "already_running"}

    if await _is_stability_running():
        await Reporter.send_collector_log(
            bot_instance,
            "Collector skipped: stability full recheck is running",
        )
        await bot_instance.session.close()
        await _release_collector_lock(lock_client, lock_token)
        return {"status": "skipped", "reason": "stability_running"}

    try:
        await Reporter.send_collector_log(
            bot_instance,
            "Collector run started",
        )
        await Reporter.send_info(
            bot_instance,
            (
                "🟢 Стартовал плановый сборщик: инкрементальная догрузка новых конфигов "
                f"({len(FIXED_SOURCE_URLS)} фиксированных источников)."
            ),
        )

        old_counts = await StatsRepo.get_regions_counts()
        result = await SubscriptionCollector.run_collection()
        cleaned = await SubRepo.cleanup_dead_subs(max_deaths=10)
        new_counts = await StatsRepo.get_regions_counts()

        await SystemRepo.set_config(
            "collector_last_run",
            json.dumps(
                {
                    "added": result.get("added", 0),
                    "rejected": result.get("rejected", 0),
                    "processed": result.get("processed", 0),
                    "cleaned": cleaned,
                    "discovered": result.get("discovered", 0),
                    "already_known": result.get("already_known", 0),
                    "japan_priority_candidates": result.get("japan_priority_candidates", 0),
                    "sources_used": result.get("sources_used", 0),
                    "custom_sources_used": result.get("custom_sources_used", 0),
                    "fixed_sources_total": result.get("fixed_sources_total", 0),
                    "custom_sources_enabled": result.get("custom_sources_enabled", 0),
                    "custom_sources_accepted": result.get("custom_sources_accepted", 0),
                    "custom_sources_ignored": result.get("custom_sources_ignored", 0),
                },
                ensure_ascii=False,
            ),
        )

        await SmartAlerts.process_changes(old_counts, new_counts)
        duration = asyncio.get_event_loop().time() - start_time

        try:
            await Reporter.send_new_configs(
                bot_instance,
                result.get("added", 0),
                result.get("region_stats", {}),
                meta={
                    "processed": result.get("processed", 0),
                    "rejected": result.get("rejected", 0),
                    "sources_used": result.get("sources_used", 0),
                    "custom_sources_used": result.get("custom_sources_used", 0),
                    "fixed_sources_total": result.get("fixed_sources_total", 0),
                    "custom_sources_enabled": result.get("custom_sources_enabled", 0),
                    "custom_sources_accepted": result.get("custom_sources_accepted", 0),
                    "custom_sources_ignored": result.get("custom_sources_ignored", 0),
                    "japan_priority_candidates": result.get("japan_priority_candidates", 0),
                    "duration": duration,
                },
            )
            await Reporter.send_not_configs(
                bot_instance,
                result.get("rejected", 0),
                result.get("rejected_reasons", {}),
                meta={"processed": result.get("processed", 0)},
            )
            await Reporter.send_collector_log(
                bot_instance,
                "Collector run finished: "
                f"discovered={result.get('discovered', 0)}, "
                f"known={result.get('already_known', 0)}, "
                f"jp_priority={result.get('japan_priority_candidates', 0)}, "
                f"processed={result.get('processed', 0)}, "
                f"fixed={result.get('fixed_sources_total', 0)}, "
                f"custom_enabled={result.get('custom_sources_enabled', 0)}, "
                f"custom_accepted={result.get('custom_sources_accepted', 0)}, "
                f"custom_ignored={result.get('custom_sources_ignored', 0)}, "
                f"added={result.get('added', 0)}, "
                f"rejected={result.get('rejected', 0)}, "
                f"cleaned={cleaned}, duration={duration:.1f}s",
            )
        except asyncio.CancelledError:
            raise
        except Exception as e:
            if "SoftTimeLimitExceeded" not in type(e).__name__:
                logger.error(f"Failed to send reports: {e}")

        return {
            "success": True,
            "duration": duration,
            "result": result,
            "cleaned": cleaned,
        }

    except asyncio.CancelledError:
        raise
    except Exception as e:
        if "SoftTimeLimitExceeded" in type(e).__name__:
            logger.warning(
                "Collector task hit SoftTimeLimitExceeded, completing gracefully."
            )
            try:
                if bot_instance is None:
                    bot_instance = Bot(
                        token=config.BOT_TOKEN.get_secret_value(),
                        session=AiohttpSession(),
                    )
                if result:
                    await Reporter.send_new_configs(
                        bot_instance,
                        result.get("added", 0),
                        result.get("region_stats", {}),
                    )
                    await Reporter.send_not_configs(
                        bot_instance,
                        result.get("rejected", 0),
                        result.get("rejected_reasons", {}),
                    )
                await Reporter.send_info(
                    bot_instance,
                    "⚠️ Сборщик прерван по таймауту (достигнут лимит времени).",
                )
                await Reporter.send_collector_log(
                    bot_instance,
                    "Collector hit soft time limit and exited gracefully",
                )
            except Exception:
                pass
            return {"status": "timeout_graceful"}

        try:
            if bot_instance is None:
                bot_instance = Bot(
                    token=config.BOT_TOKEN.get_secret_value(), session=AiohttpSession()
                )
            await Reporter.send_error(bot_instance, f"Collector failed: {str(e)}")
            await Reporter.send_collector_log(
                bot_instance,
                f"Collector failed with exception: {e}",
            )
        except Exception:
            pass
        raise
    finally:
        if bot_instance is not None:
            try:
                await bot_instance.session.close()
            except Exception:
                pass
        await _release_collector_lock(lock_client, lock_token)

import asyncio
import json
from typing import Dict, Any

from celery_app import app
from tasks.base import (
    OptimizedTask,
    setup_log_rotation,
    _setup_loop_exception_handler,
    logger,
)
from utils.collector import SubscriptionCollector
from database.repo import SubRepo, SystemRepo, StatsRepo
from utils.state import BotState
from utils.smart_alerts import SmartAlerts
from utils.reporter import Reporter
from config import config

from aiogram import Bot
from aiogram.client.session.aiohttp import AiohttpSession


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

    try:
        await Reporter.send_collector_log(
            bot_instance,
            "Collector run started",
        )
        await Reporter.send_info(
            bot_instance,
            "🟢 Стартовал плановый сборщик конфигов (2 базовых источника).",
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
                    "sources_used": result.get("sources_used", 0),
                    "custom_sources_used": result.get("custom_sources_used", 0),
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
                f"processed={result.get('processed', 0)}, "
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

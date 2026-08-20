import asyncio
import html
import logging
from typing import Dict, Any, cast
import uuid

import redis.asyncio as redis


from celery_app import app
from config import config, make_bot
from tasks.base import OptimizedTask, setup_log_rotation, setup_loop_exception_handler_async
from utils.reporter import Reporter
from utils.tg_proxy import TelegramProxyService

logger = logging.getLogger(__name__)


TG_PROXY_LOCK_KEY = "lock:tasks:tg_proxy_update"
TG_PROXY_LOCK_TTL_SEC = 1200


async def _acquire_tg_proxy_lock() -> tuple[redis.Redis | None, str | None]:
    client = None
    try:
        client = redis.from_url(config.REDIS_URL, decode_responses=True)
        token = uuid.uuid4().hex
        acquired = await client.set(
            TG_PROXY_LOCK_KEY,
            token,
            ex=TG_PROXY_LOCK_TTL_SEC,
            nx=True,
        )
        if acquired:
            return client, token
    except Exception as e:
        logger.warning(f"_acquire_tg_proxy_lock error: {e}")

    if client is not None:
        try:
            await client.close()
        except Exception as e:
            logger.warning(f"_acquire_tg_proxy_lock close error: {e}")
    return None, None


async def _release_tg_proxy_lock(client: redis.Redis | None, token: str | None) -> None:
    if client is None or token is None:
        return

    try:
        await cast(Any, client).eval(
            "if redis.call('get', KEYS[1]) == ARGV[1] then "
            "return redis.call('del', KEYS[1]) else return 0 end",
            1,
            TG_PROXY_LOCK_KEY,
            token,
        )
    except Exception as e:
        logger.warning(f"_release_tg_proxy_lock error: {e}")
    finally:
        try:
            await client.close()
        except Exception as e:
            logger.warning(f"_release_tg_proxy_lock close error: {e}")


@app.task(
    name="tasks.update_tg_proxy_task",
    base=OptimizedTask,
    time_limit=1800,
    soft_time_limit=1740,
)
async def update_tg_proxy_task() -> Dict[str, Any]:
    setup_log_rotation()
    await setup_loop_exception_handler_async()

    lock_client = None
    lock_token: str | None = None
    bot = make_bot()
    try:
        lock_client, lock_token = await _acquire_tg_proxy_lock()
        if lock_client is None:
            await Reporter.send_system_log(
                bot,
                "TG Proxy update skipped: previous run is still active",
            )
            return {"status": "skipped", "reason": "already_running"}
        result = await TelegramProxyService.refresh_cache()

        parsed_unique = int(result.get("parsed", 0) or 0)
        parsed_total = int(result.get("parsed_total", parsed_unique) or 0)
        alive_total = int(result.get("alive", 0) or 0)
        alive_shown = int(result.get("alive_shown", alive_total) or alive_total)
        output_limit = int(result.get("output_limit", 0) or 0)

        lines = [
            "🧩 <b>TG Proxy Update</b>",
            (
                "Статистика: "
                f"raw={int(result.get('total_lines', 0) or 0)}, "
                f"parsed={parsed_unique}, "
                f"parsed_total={parsed_total}, "
                f"checked={int(result.get('checked', 0) or 0)}, "
                f"alive_total={alive_total}, "
                f"alive_shown={alive_shown}"
            ),
        ]

        if output_limit > 0:
            lines.append(f"Лимит выдачи в UI: {output_limit}")

        sources = result.get("sources", [])
        if isinstance(sources, list) and sources:
            lines.append("<b>Источники:</b>")
            for idx, source in enumerate(sources, start=1):
                lines.append(f"{idx}. <code>{html.escape(str(source))}</code>")
        else:
            lines.append(f"Источник: <code>{html.escape(str(result.get('source', '')))}</code>")

        source_stats = result.get("source_stats", [])
        if isinstance(source_stats, list) and source_stats:
            lines.append("\n<b>По источникам:</b>")
            for stat in source_stats[:10]:
                source = html.escape(str(stat.get("source", "")))
                raw = int(stat.get("raw", 0) or 0)
                parsed = int(stat.get("parsed", 0) or 0)
                unique = int(stat.get("unique", 0) or 0)
                lines.append(
                    f"• raw={raw}, parsed={parsed}, unique={unique} | <code>{html.escape(source)}</code>"
                )

        proxies = result.get("proxies", [])
        if proxies:
            lines.append("\n<b>Рабочие прокси:</b>")
            for idx, link in enumerate(proxies[:40], start=1):
                lines.append(f"{idx}. <code>{html.escape(link)}</code>")
            hidden = len(proxies) - min(len(proxies), 40)
            if hidden > 0:
                lines.append(f"... и еще {hidden} прокси")
        else:
            lines.append("\nНет рабочих прокси после проверки.")

        await Reporter.send_system_log(bot, "\n".join(lines))
        return result
    except asyncio.CancelledError:
        raise
    except Exception as e:
        await Reporter.send_error(bot, f"TG proxy update failed: {e}")
        raise
    finally:
        try:
            await bot.session.close()
        except Exception:
            pass
        await _release_tg_proxy_lock(lock_client, lock_token)

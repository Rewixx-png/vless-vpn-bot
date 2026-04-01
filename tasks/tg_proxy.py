import asyncio
import html
from typing import Dict, Any

from aiogram import Bot
from aiogram.client.session.aiohttp import AiohttpSession

from celery_app import app
from config import config
from tasks.base import OptimizedTask, setup_log_rotation, _setup_loop_exception_handler
from utils.reporter import Reporter
from utils.tg_proxy import TelegramProxyService


@app.task(
    name="tasks.update_tg_proxy_task",
    base=OptimizedTask,
    time_limit=1800,
    soft_time_limit=1740,
)
async def update_tg_proxy_task() -> Dict[str, Any]:
    setup_log_rotation()
    _setup_loop_exception_handler()

    bot = Bot(token=config.BOT_TOKEN.get_secret_value(), session=AiohttpSession())
    try:
        result = await TelegramProxyService.refresh_cache()

        parsed_unique = int(result.get("parsed", 0) or 0)
        parsed_total = int(result.get("parsed_total", parsed_unique) or 0)

        lines = [
            "🧩 <b>TG Proxy Update</b>",
            (
                "Статистика: "
                f"raw={int(result.get('total_lines', 0) or 0)}, "
                f"parsed={parsed_unique}, "
                f"parsed_total={parsed_total}, "
                f"checked={int(result.get('checked', 0) or 0)}, "
                f"alive={int(result.get('alive', 0) or 0)}"
            ),
        ]

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
                    f"• raw={raw}, parsed={parsed}, unique={unique} | <code>{source}</code>"
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

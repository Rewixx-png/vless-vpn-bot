"""
Optimized fix handlers with batch processing and batch updates.
"""
import asyncio
import aiohttp
from aiogram import Router, F
from aiogram.types import CallbackQuery, Message

from database.repo import SubRepo
from utils.checker import VlessChecker
from keyboards.admin import back_to_admin
from utils.batch_processor import SmartBatchProcessor

router = Router()


async def safe_edit_text(message: Message, text: str, reply_markup=None, parse_mode="HTML"):
    try:
        await message.edit_text(text, reply_markup=reply_markup, parse_mode=parse_mode)
    except Exception:
        pass


@router.callback_query(F.data == "admin_fix_regions")
async def fix_unknown_regions(callback: CallbackQuery):
    msg = await callback.message.edit_text(
        "<blockquote>🚀 <b>Запуск GeoIP Batch Mode...</b>\n\n"
        "ℹ️ <i>Используем пакетную проверку IP с batch update.</i></blockquote>",
        parse_mode="HTML"
    )

    subs = await SubRepo.get_unknown_regions_subs()
    if not subs:
        await msg.edit_text(
            "<blockquote>✅ Unknown регионов не найдено.</blockquote>",
            reply_markup=back_to_admin(),
            parse_mode="HTML"
        )
        return

    # Group subs by host
    host_to_subs = {}
    for sub in subs:
        parsed = VlessChecker.parse_config(sub.vless_key)
        if parsed and parsed.get("host"):
            host = parsed["host"]
            if host not in host_to_subs:
                host_to_subs[host] = []
            host_to_subs[host].append(sub)

    unique_hosts = list(host_to_subs.keys())
    total_hosts = len(unique_hosts)

    # Progress message
    await safe_edit_text(
        msg,
        f"<blockquote>🚀 <b>GeoIP Update: 0%</b>\n"
        f"📡 Проверено хостов: 0/{total_hosts}</blockquote>"
    )

    # Process with batch API
    async with aiohttp.ClientSession() as session:
        results = await VlessChecker.get_regions_batch(unique_hosts, session)

    # Collect updates
    updates = []
    fixed_count = 0

    for host, region in results.items():
        if "Unknown" not in region and host in host_to_subs:
            for sub in host_to_subs[host]:
                updates.append({"id": sub.id, "region": region})
                fixed_count += 1

    # Batch update all at once
    if updates:
        await SubRepo.batch_update_regions(updates)

    await safe_edit_text(
        msg,
        f"<blockquote>🏁 <b>Обновление регионов завершено!</b>\n\n"
        f"📡 Проверено хостов: <b>{total_hosts}</b>\n"
        f"✅ Обновлено ключей: <b>{fixed_count}</b></blockquote>",
        reply_markup=back_to_admin()
    )


@router.callback_query(F.data == "admin_recheck")
async def recheck_all_subs(callback: CallbackQuery):
    msg = await callback.message.edit_text(
        "<blockquote>🚀 <b>Xray Core Recheck</b>\n"
        "<i>Запускаю проверку через реальное ядро Xray...</i>\n"
        "Это может занять время.</blockquote>",
        parse_mode="HTML"
    )

    subs = await SubRepo.get_all_subscriptions_for_check()
    if not subs:
        await msg.edit_text(
            "<blockquote>⚠️ База пуста.</blockquote>",
            reply_markup=back_to_admin(),
            parse_mode="HTML"
        )
        return

    total = len(subs)

    # Use SmartBatchProcessor
    processor = SmartBatchProcessor(
        worker_count=10,
        progress_interval=3.0
    )

    status_updates = []
    region_updates = []

    async def process_sub(sub):
        """Process single subscription"""
        try:
            success, region, latency, ai_avail, err = await VlessChecker.process_subscription(sub.vless_key)

            if success:
                status_updates.append({
                    "id": sub.id,
                    "is_active": True,
                    "latency_ms": latency,
                    "ai_available": ai_avail
                })
                if region and "Unknown" not in region:
                    region_updates.append({"id": sub.id, "region": region})
                return {"status": "active", "was_dead": not sub.is_active}
            else:
                if sub.is_active:
                    status_updates.append({
                        "id": sub.id,
                        "is_active": False,
                        "latency_ms": 9999,
                        "ai_available": False
                    })
                return {"status": "dead", "was_active": sub.is_active}

        except Exception:
            return {"status": "error"}

    # Progress tracking
    stats = {"active": 0, "died": 0, "revived": 0}

    async def on_progress(completed: int, total: int, success: int, failed: int):
        percent = int((completed / total) * 100)
        await safe_edit_text(
            msg,
            f"<blockquote>🔄 <b>Xray Check: {percent}%</b>\n"
            f"📡 Проверено: {completed}/{total}\n\n"
            f"🟢 <b>Живых: {stats['active']}</b>\n"
            f"💀 Умерло: {stats['died']}\n"
            f"🆙 Воскресло: {stats['revived']}</blockquote>"
        )

    # Process with progress
    result = await processor.process(
        items=subs,
        process_func=process_sub,
        on_progress=on_progress
    )

    # Count stats
    for item in result.items:
        res = item.get("result", {})
        if res.get("status") == "active":
            stats["active"] += 1
            if res.get("was_dead"):
                stats["revived"] += 1
        elif res.get("status") == "dead" and res.get("was_active"):
            stats["died"] += 1

    # Batch update all changes at once
    if status_updates:
        await SubRepo.batch_update_status(status_updates)
    if region_updates:
        await SubRepo.batch_update_regions(region_updates)

    await safe_edit_text(
        msg,
        f"<blockquote>🏁 <b>Xray Recheck завершен!</b>\n\n"
        f"Всего ключей: <b>{total}</b>\n"
        f"🟢 <b>Активных: {stats['active']}</b>\n"
        f"💀 Мертвых: <b>{stats['died']}</b>\n"
        f"🆙 Воскресло: <b>{stats['revived']}</b></blockquote>",
        reply_markup=back_to_admin()
    )

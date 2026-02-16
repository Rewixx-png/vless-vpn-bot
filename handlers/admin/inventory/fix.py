"""
Optimized fix handlers with batch processing and batch updates.
"""
import asyncio
import aiohttp
from aiogram import Router, F
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.context import FSMContext

from database.repo import SubRepo
from utils.checker import VlessChecker
from keyboards.admin import back_to_admin
from utils.batch_processor import SmartBatchProcessor
from handlers.admin.utils import admin_edit_or_answer, safe_edit_message

router = Router()


@router.callback_query(F.data == "admin_fix_regions")
async def fix_unknown_regions(callback: CallbackQuery, state: FSMContext):
    await admin_edit_or_answer(
        callback,
        state,
        "<blockquote>🌍 <b>Обновление геолокации серверов</b>\n\n"
        "📡 Определяю регионы по IP-адресам серверов\n"
        "⚡ Используется пакетная проверка\n"
        "⏳ Загружаю данные...</blockquote>"
    )

    subs = await SubRepo.get_unknown_regions_subs()
    if not subs:
        await admin_edit_or_answer(
            callback,
            state,
            "<blockquote>✅ <b>Все серверы имеют регион!</b>\n\n"
            "ℹ️ Нет серверов с неизвестным регионом.</blockquote>",
            reply_markup=back_to_admin()
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
    await safe_edit_message(
        callback.message,
        f"<blockquote>🌍 <b>Обновление геолокации</b>\n\n"
        f"📡 Определено уникальных хостов: <b>{total_hosts}</b>\n"
        f"⏳ Загружаю данные GeoIP...</blockquote>"
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

    await admin_edit_or_answer(
        callback,
        state,
        f"<blockquote>✅ <b>Геолокация обновлена!</b>\n\n"
        f"📊 <b>Итоговый отчёт:</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"📡 Всего хостов: <b>{total_hosts}</b>\n"
        f"✅ Обновлено регионов: <b>{fixed_count}</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"ℹ️ <i>Серверы с Unknown регионом оставлены без изменений.</i></blockquote>",
        reply_markup=back_to_admin()
    )


@router.callback_query(F.data == "admin_recheck")
async def recheck_all_subs(callback: CallbackQuery, state: FSMContext):
    await admin_edit_or_answer(
        callback,
        state,
        "<blockquote>🔍 <b>Запуск полной проверки серверов</b>\n\n"
        "⚡ Используется реальное ядро Xray\n"
        "🌐 Проверяется каждый сервер на работоспособность\n"
        "⏱️ Это может занять несколько минут...</blockquote>"
    )

    subs = await SubRepo.get_all_subscriptions_for_check()
    if not subs:
        await admin_edit_or_answer(
            callback,
            state,
            "<blockquote>⚠️ <b>База данных пуста!</b>\n\n"
            "Сначала добавьте серверы через меню инвентаря.</blockquote>",
            reply_markup=back_to_admin()
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
            is_alive, region, latency, ai_avail, err = await VlessChecker.process_subscription(sub.vless_key)

            if is_alive:
                status_updates.append({
                    "id": sub.id,
                    "is_active": True,
                    "latency_ms": latency,
                    "ai_available": ai_avail
                })
                if region and "Unknown" not in region:
                    region_updates.append({"id": sub.id, "region": region})
                return (True, {"status": "active", "was_dead": not sub.is_active})
            else:
                if sub.is_active:
                    status_updates.append({
                        "id": sub.id,
                        "is_active": False,
                        "latency_ms": 9999,
                        "ai_available": False
                    })
                return (False, {"status": "dead", "was_active": sub.is_active})

        except Exception:
            return (False, {"status": "error"})

    # Progress tracking
    stats = {"active": 0, "died": 0, "revived": 0}
    start_time = asyncio.get_event_loop().time()

    async def on_progress(completed: int, total: int, success: int, failed: int):
        elapsed = asyncio.get_event_loop().time() - start_time
        percent = int((completed / total) * 100)
        speed = int(completed / elapsed * 60) if elapsed > 0 else 0
        remaining = int((total - completed) / (completed / elapsed)) if completed > 0 else 0
        
        await safe_edit_message(
            callback.message,
            f"<blockquote>⚡ <b>Проверка серверов: {percent}%</b>\n\n"
            f"📊 <b>{completed} / {total}</b>\n"
            f"⏱️ Осталось: ~{remaining}сек | ⚡ {speed}серв/мин\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"🟢 Рабочих: <b>{stats['active']}</b>\n"
            f"💀 Нерабочих: <b>{stats['died']}</b>\n"
            f"🆙 Восстановлено: <b>{stats['revived']}</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"🔄 Проверяю...</blockquote>"
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

    await admin_edit_or_answer(
        callback,
        state,
        f"<blockquote>✅ <b>Проверка серверов завершена!</b>\n\n"
        f"📊 <b>Итоговый отчёт:</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"📋 Всего проверено: <b>{total}</b>\n"
        f"🟢 Рабочих серверов: <b>{stats['active']}</b>\n"
        f"💀 Нерабочих серверов: <b>{stats['died']}</b>\n"
        f"🆙 Восстановлено: <b>{stats['revived']}</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"ℹ️ <i>Нерабочие серверы отмечены как неактивные.</i></blockquote>",
        reply_markup=back_to_admin()
    )

import asyncio
import aiohttp
import psutil
from aiogram import Router, F
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.context import FSMContext

from database.repo import SubRepo
from utils.checker import VlessChecker
from keyboards.admin import back_to_admin
from utils.batch_processor import SmartBatchProcessor, CpuAdaptiveProcessor
from handlers.admin.utils import admin_edit_or_answer, safe_edit_message
from utils.state import BotState

router = Router()


@router.callback_query(F.data == "admin_fix_regions")
async def fix_unknown_regions(callback: CallbackQuery, state: FSMContext):
    # Explicitly answer first to prevent timeout
    try:
        await callback.answer()
    except:
        pass

    await admin_edit_or_answer(
        callback,
        state,
        "<blockquote>🌍 <b>Нормализация геолокации</b>\n\n"
        "📡 Перевожу названия стран в формат (De, Us...)\n"
        "⚡ Проверяю ВСЕ серверы в базе\n"
        "🔄 Использую мульти-провайдеры (Robust Mode)\n"
        "⏳ Анализирую хосты...</blockquote>"
    )

    subs = await SubRepo.get_all_subscriptions_for_check()
    if not subs:
        await safe_edit_message(
            callback.message,
            "<blockquote>✅ <b>База пуста!</b>\n\n"
            "ℹ️ Нет серверов для обновления.</blockquote>",
            reply_markup=back_to_admin()
        )
        return

    host_to_subs = {}
    for sub in subs:
        parsed = VlessChecker.parse_config(sub.vless_key)
        if parsed and parsed.get("host"):
            host = parsed["host"]
            if host in ["127.0.0.1", "localhost"]:
                continue
            if host not in host_to_subs:
                host_to_subs[host] = []
            host_to_subs[host].append(sub)

    unique_hosts = list(host_to_subs.keys())
    total_hosts = len(unique_hosts)

    if total_hosts == 0:
        await safe_edit_message(
            callback.message,
            "<blockquote>⚠️ <b>Не найдено валидных хостов.</b></blockquote>",
            reply_markup=back_to_admin()
        )
        return

    await safe_edit_message(
        callback.message,
        f"<blockquote>🌍 <b>Нормализация геолокации</b>\n\n"
        f"📡 Уникальных IP/Доменов: <b>{total_hosts}</b>\n"
        f"🔄 Опрашиваю GeoIP базы (это займет время)...\n"
        f"⚡ 20 потоков...</blockquote>"
    )

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }

    async with aiohttp.ClientSession(headers=headers) as session:
        results = await VlessChecker.get_regions_batch(unique_hosts, session)

    updates = []
    fixed_count = 0
    failed_hosts = 0

    for host in unique_hosts:
        region = results.get(host)
        
        if region and "Unk" not in region:
            if host in host_to_subs:
                for sub in host_to_subs[host]:
                    if sub.region != region:
                        updates.append({"id": sub.id, "region": region})
                        fixed_count += 1
        else:
            failed_hosts += 1

    if updates:
        chunk_size = 500
        for i in range(0, len(updates), chunk_size):
            chunk = updates[i:i + chunk_size]
            await SubRepo.batch_update_regions(chunk)

    # Use safe_edit_message here instead of admin_edit_or_answer to avoid "query is too old"
    await safe_edit_message(
        callback.message,
        f"<blockquote>✅ <b>Геолокация обновлена!</b>\n\n"
        f"📊 <b>Отчёт:</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"📡 IP проверено: <b>{total_hosts}</b>\n"
        f"✅ Обновлено записей: <b>{fixed_count}</b>\n"
        f"⚠️ Не определилось: <b>{failed_hosts}</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"ℹ️ <i>Теперь названия стран в формате (De, Us).</i></blockquote>",
        reply_markup=back_to_admin()
    )


@router.callback_query(F.data == "admin_recheck")
async def recheck_all_subs(callback: CallbackQuery, state: FSMContext):
    try: await callback.answer()
    except: pass
    
    BotState.set_maintenance(True)
    
    msg = await callback.message.answer(
        "<blockquote>⛔️ <b>MAINTENANCE MODE ACTIVE</b>\n\n"
        "🔍 <b>Запуск ПРИОРИТЕТНОЙ проверки (ВСЕ)</b>\n"
        "✋ Фоновые задачи (Collector) остановлены\n"
        "⚙️ Адаптивная нагрузка на CPU (&lt;85%)\n"
        "🚀 <b>Turbo Mode:</b> Limit 1000 threads\n"
        "⏱️ Это может занять время...</blockquote>",
        parse_mode="HTML"
    )

    subs = await SubRepo.get_all_subscriptions_for_check()
    await _run_recheck_process(subs, msg)


@router.callback_query(F.data == "admin_recheck_active")
async def recheck_active_subs(callback: CallbackQuery, state: FSMContext):
    try: await callback.answer()
    except: pass

    BotState.set_maintenance(True)
    
    msg = await callback.message.answer(
        "<blockquote>⛔️ <b>MAINTENANCE MODE ACTIVE</b>\n\n"
        "🔍 <b>Запуск ПРИОРИТЕТНОЙ проверки (ТОЛЬКО ACTIVE)</b>\n"
        "✋ Фоновые задачи (Collector) остановлены\n"
        "⚙️ Адаптивная нагрузка на CPU (&lt;85%)\n"
        "🚀 <b>Turbo Mode:</b> Limit 1000 threads\n"
        "⏱️ Это может занять время...</blockquote>",
        parse_mode="HTML"
    )

    subs = await SubRepo.get_active_subscriptions_for_check()
    await _run_recheck_process(subs, msg)


async def _run_recheck_process(subs: list, msg: Message):
    """Common logic for recheck process"""
    if not subs:
        BotState.set_maintenance(False)
        await msg.edit_text(
            "<blockquote>⚠️ <b>Нет серверов для проверки!</b></blockquote>",
            reply_markup=back_to_admin(),
            parse_mode="HTML"
        )
        return

    total = len(subs)
    
    processor = CpuAdaptiveProcessor(
        initial_workers=100,
        min_workers=50,
        max_workers=1000,
        target_cpu=85.0
    )

    update_lock = asyncio.Lock()
    status_buffer = []
    region_buffer = []
    BATCH_SIZE = 50

    stats = {"active": 0, "died": 0, "revived": 0, "saved": 0}
    start_time = asyncio.get_event_loop().time()

    async def flush_buffers():
        async with update_lock:
            to_save_status = list(status_buffer)
            to_save_region = list(region_buffer)
            status_buffer.clear()
            region_buffer.clear()

        if to_save_status:
            await SubRepo.batch_update_status(to_save_status)
            stats["saved"] += len(to_save_status)
        
        if to_save_region:
            await SubRepo.batch_update_regions(to_save_region)

    async def process_sub(sub):
        try:
            is_alive, region, latency, ai_avail, err = await VlessChecker.process_subscription(sub.vless_key)
            
            status_upd = None
            region_upd = None

            if is_alive:
                stats["active"] += 1
                if not sub.is_active:
                    stats["revived"] += 1

                status_upd = {
                    "id": sub.id,
                    "is_active": True,
                    "latency_ms": latency,
                    "ai_available": ai_avail
                }
                
                if region and "Unk" not in region:
                    region_upd = {"id": sub.id, "region": region}
                
                result_status = "active"
            else:
                if sub.is_active:
                    stats["died"] += 1
                
                status_upd = {
                    "id": sub.id,
                    "is_active": False,
                    "latency_ms": 9999,
                    "ai_available": False
                }
                result_status = "dead"

            should_flush = False
            async with update_lock:
                if status_upd:
                    status_buffer.append(status_upd)
                if region_upd:
                    region_buffer.append(region_upd)
                
                if len(status_buffer) >= BATCH_SIZE:
                    should_flush = True
            
            if should_flush:
                await flush_buffers()

            return (True, {"status": result_status})

        except Exception:
            return (False, {"status": "error"})

    async def on_progress(completed: int, total: int, success: int, failed: int, workers: int):
        elapsed = asyncio.get_event_loop().time() - start_time
        percent = int((completed / total) * 100) if total > 0 else 0
        speed = int(completed / elapsed * 60) if elapsed > 0 else 0
        remaining = int((total - completed) / (completed / elapsed)) if completed > 0 else 0
        cpu = psutil.cpu_percent()
        
        try:
            await msg.edit_text(
                f"<blockquote>⚡ <b>ПРИОРИТЕТНАЯ ПРОВЕРКА: {percent}%</b>\n\n"
                f"📊 <b>{completed} / {total}</b>\n"
                f"💻 <b>CPU:</b> {cpu}% | 🏗 <b>Workers:</b> {workers}\n"
                f"⏱️ Осталось: ~{remaining}сек | ⚡ {speed}серв/мин\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"🟢 Рабочих: <b>{stats['active']}</b>\n"
                f"💀 Нерабочих: <b>{stats['died']}</b>\n"
                f"🆙 Восстановлено: <b>{stats['revived']}</b>\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"🔄 Система оптимизирует нагрузку...</blockquote>",
                parse_mode="HTML"
            )
        except Exception:
            pass

    try:
        await processor.process(
            items=subs,
            process_func=process_sub,
            on_progress=on_progress
        )
        await flush_buffers()
        
    finally:
        BotState.set_maintenance(False)

    await msg.edit_text(
        f"<blockquote>✅ <b>Проверка завершена!</b>\n\n"
        f"🟢 <b>MAINTENANCE MODE DISABLED</b>\n"
        f"Фоновые задачи возобновлены.\n\n"
        f"📊 <b>Итоговый отчёт:</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"📋 Всего проверено: <b>{total}</b>\n"
        f"🟢 Рабочих серверов: <b>{stats['active']}</b>\n"
        f"💀 Нерабочих серверов: <b>{stats['died']}</b>\n"
        f"🆙 Восстановлено: <b>{stats['revived']}</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"ℹ️ <i>База данных обновлена.</i></blockquote>",
        reply_markup=back_to_admin(),
        parse_mode="HTML"
    )

import asyncio
import psutil
from aiogram import Router, F
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.context import FSMContext

from database.repo import SubRepo
from utils.checker import VlessChecker
from keyboards.admin import back_to_admin, recheck_menu_kb
from utils.batch_processor import CpuAdaptiveProcessor
from handlers.admin.utils import admin_edit_or_answer
from utils.state import BotState

router = Router()

@router.callback_query(F.data == "admin_recheck_menu")
async def show_recheck_menu(callback: CallbackQuery, state: FSMContext):
    await admin_edit_or_answer(
        callback,
        state,
        "<blockquote>📡 <b>Menu Recheck</b>\n\n"
        "Выберите тип проверки:\n"
        "♻️ <b>Full:</b> Проверить ВСЕ ключи в базе.\n"
        "⚡ <b>Active:</b> Проверить только ЖИВЫЕ ключи.\n"
        "💀 <b>Dead:</b> Проверить только МЕРТВЫЕ (для воскрешения).</blockquote>",
        reply_markup=recheck_menu_kb()
    )

@router.callback_query(F.data.startswith("admin_recheck_run_"))
async def run_recheck(callback: CallbackQuery, state: FSMContext):
    try: await callback.answer()
    except: pass
    
    mode = callback.data.split("admin_recheck_run_")[1]
    
    BotState.set_maintenance(True)
    
    mode_text = {
        "all": "ВСЕ",
        "active": "ЖИВЫЕ",
        "dead": "МЕРТВЫЕ"
    }.get(mode, "Unknown")
    
    msg = await callback.message.answer(
        f"<blockquote>⛔️ <b>MAINTENANCE MODE ACTIVE</b>\n\n"
        f"🔍 <b>Запуск ПРИОРИТЕТНОЙ проверки ({mode_text})</b>\n"
        "✋ Фоновые задачи (Collector) остановлены\n"
        "⚙️ Адаптивная нагрузка на CPU\n"
        "🚀 <b>Turbo Mode</b>\n"
        "⏱️ Это может занять время...</blockquote>",
        parse_mode="HTML"
    )

    subs = []
    if mode == "all":
        subs = await SubRepo.get_all_subscriptions_for_check()
    elif mode == "active":
        subs = await SubRepo.get_active_subscriptions_for_check()
    elif mode == "dead":
        subs = await SubRepo.get_dead_subscriptions_for_check()
        
    await _run_recheck_process(subs, msg)

async def _run_recheck_process(subs: list, msg: Message):
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
        initial_workers=20,
        min_workers=10,
        max_workers=50,
        target_cpu=80.0
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
            is_alive, region, latency, speed_mbps, ai_avail, err = await VlessChecker.process_subscription(sub.vless_key)
            
            if not is_alive and err and "SYS_ERR" in str(err):
                return (False, {"status": "error"})

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
                    "speed_mbps": speed_mbps,
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
                    "speed_mbps": 0.0,
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
        await SubRepo.cleanup_dead_subs(max_deaths=3)
        
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
        reply_markup=recheck_menu_kb(),
        parse_mode="HTML"
    )
import asyncio
import logging
import psutil
import gc
from aiogram import Router, F
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.context import FSMContext
from aiogram.exceptions import TelegramRetryAfter

from database.repo import SubRepo
from utils.checker import VlessChecker
from keyboards.admin import back_to_admin, recheck_menu_kb
from utils.batch_processor import CpuAdaptiveProcessor
from handlers.admin.utils import admin_edit_or_answer, safe_edit_message
from utils.state import BotState

router = Router()
logger = logging.getLogger("AdminRecheck")

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
    try:
        await callback.answer()
    except Exception:
        pass

    mode = callback.data.replace("admin_recheck_run_", "", 1) if callback.data else ""
    mode_text = {
        "all": "ВСЕ",
        "active": "ЖИВЫЕ",
        "dead": "МЕРТВЫЕ"
    }.get(mode, "Unknown")

    msg = None
    BotState.set_maintenance(True)

    try:
        msg = await callback.message.answer(
            f"<blockquote>⛔️ <b>MAINTENANCE MODE ACTIVE</b>\n\n"
            f"🔍 <b>Запуск ПРИОРИТЕТНОЙ проверки ({mode_text})</b>\n"
            "✋ Фоновые задачи (Collector) остановлены\n"
            "🛡 <b>3-Factor Check:</b> TCP ➔ SSL ➔ Xray\n"
            "⚙️ Адаптивная нагрузка на CPU\n"
            "🚀 <b>Max Stability Mode (8 Workers)</b>\n"
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
    except Exception as e:
        logger.error(f"Recheck failed in mode='{mode}': {e}", exc_info=True)
        BotState.set_maintenance(False)
        error_text = (
            "<blockquote>❌ <b>Recheck завершился ошибкой.</b>\n"
            "Проверка остановлена, maintenance mode отключен.</blockquote>"
        )
        if msg:
            await safe_edit_message(msg, error_text, reply_markup=recheck_menu_kb())
        else:
            try:
                await callback.message.answer(
                    error_text,
                    reply_markup=recheck_menu_kb(),
                    parse_mode="HTML"
                )
            except Exception:
                pass

async def _run_recheck_process(subs: list, msg: Message):
    if not subs:
        BotState.set_maintenance(False)
        await safe_edit_message(
            msg,
            "<blockquote>⚠️ <b>Нет серверов для проверки!</b></blockquote>",
            reply_markup=back_to_admin()
        )
        return

    total = len(subs)
    
    # ЕЩЕ БОЛЬШЕЕ СНИЖЕНИЕ. 8 воркеров - это очень безопасно.
    processor = CpuAdaptiveProcessor(
        initial_workers=4,
        min_workers=2,
        max_workers=8, 
        target_cpu=65.0,
        target_ram=75.0
    )

    update_lock = asyncio.Lock()
    status_buffer = []
    region_buffer = []
    BATCH_SIZE = 50

    stats = {
        "completed": 0,
        "active": 0, 
        "died": 0, 
        "revived": 0, 
        "saved": 0, 
        "f1_dead": 0, 
        "f2_dead": 0, 
        "f3_dead": 0
    }
    
    start_time = asyncio.get_event_loop().time()
    is_running = True

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
            
        # GC чаще
        if stats["saved"] % 200 == 0:
            gc.collect()

    # UI Loop
    async def ui_loop():
        while is_running:
            try:
                await asyncio.sleep(5.0)

                completed = stats["completed"]
                if completed == 0:
                    continue

                elapsed = asyncio.get_event_loop().time() - start_time
                percent = int((completed / total) * 100) if total > 0 else 0
                speed = int(completed / elapsed * 60) if elapsed > 0 else 0
                remaining = int((total - completed) / (completed / elapsed)) if completed > 0 else 0
                cpu = psutil.cpu_percent()
                ram = psutil.virtual_memory().percent

                await msg.edit_text(
                    f"<blockquote>⚡ <b>3-FACTOR CHECK: {percent}%</b>\n\n"
                    f"📊 <b>{completed} / {total}</b>\n"
                    f"💻 <b>CPU:</b> {cpu}% | 🧠 <b>RAM:</b> {ram}%\n"
                    f"⚡ Скорость: {speed} серв/мин\n"
                    f"⏱️ Осталось: ~{remaining}сек\n"
                    f"━━━━━━━━━━━━━━━━━━\n"
                    f"🟢 Рабочих: <b>{stats['active']}</b>\n"
                    f"💀 Потеряно: <b>{stats['died']}</b>\n"
                    f"├── 🚫 TCP Fail: <b>{stats['f1_dead']}</b>\n"
                    f"├── 🔐 SSL Fail: <b>{stats['f2_dead']}</b>\n"
                    f"└── 🤖 Xray Fail: <b>{stats['f3_dead']}</b>\n"
                    f"🆙 Восстановлено: <b>{stats['revived']}</b></blockquote>",
                    parse_mode="HTML"
                )
            except TelegramRetryAfter:
                await asyncio.sleep(5)
            except Exception:
                pass

    ui_task = asyncio.create_task(ui_loop())

    async def process_sub(sub):
        # Даем дышать Event Loop между задачами
        await asyncio.sleep(0.01)
        
        try:
            is_alive, region, latency, speed_mbps, ai_avail, err = await VlessChecker.process_subscription(sub.vless_key)
            
            if not is_alive and err and "SYS_ERR" in str(err):
                stats["completed"] += 1
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
                err_str = str(err)
                if "Factor 1" in err_str:
                    stats["f1_dead"] += 1
                elif "Factor 2" in err_str:
                    stats["f2_dead"] += 1
                else:
                    stats["f3_dead"] += 1

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

            stats["completed"] += 1
            return (True, {"status": result_status})

        except Exception:
            stats["completed"] += 1
            return (False, {"status": "error"})

    try:
        await processor.process(
            items=subs,
            process_func=process_sub,
            on_progress=None,
            collect_results=False
        )
        await flush_buffers()
        await SubRepo.cleanup_dead_subs(max_deaths=3)
        
    finally:
        is_running = False
        ui_task.cancel()
        try:
            await ui_task
        except asyncio.CancelledError:
            pass
        except Exception:
            pass
        BotState.set_maintenance(False)

    await safe_edit_message(
        msg,
        f"<blockquote>✅ <b>Проверка завершена!</b>\n\n"
        f"🟢 <b>MAINTENANCE MODE DISABLED</b>\n"
        f"Фоновые задачи возобновлены.\n\n"
        f"📊 <b>Итоговый отчёт (3-Factor):</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"📋 Всего проверено: <b>{total}</b>\n"
        f"🟢 Рабочих серверов: <b>{stats['active']}</b>\n"
        f"💀 Потеряно (Active->Dead): <b>{stats['died']}</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"📊 <b>Статистика отказов:</b>\n"
        f"├── 🚫 1. TCP Ping: <b>{stats['f1_dead']}</b>\n"
        f"├── 🔐 2. SSL Handshake: <b>{stats['f2_dead']}</b>\n"
        f"└── 🤖 3. Xray Core: <b>{stats['f3_dead']}</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"🆙 Восстановлено: <b>{stats['revived']}</b>\n"
        f"ℹ️ <i>База данных обновлена.</i></blockquote>",
        reply_markup=recheck_menu_kb()
    )

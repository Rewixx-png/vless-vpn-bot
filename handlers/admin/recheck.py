import asyncio
import logging
from aiogram import Router, F
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.context import FSMContext
from aiogram.exceptions import TelegramBadRequest

from keyboards.admin import back_to_admin, recheck_menu_kb
from handlers.admin.utils import admin_edit_or_answer
from utils.state import BotState
from utils.reporter import Reporter
from database.repo import SubRepo
from celery_app import app as celery_app

logger = logging.getLogger(__name__)
router = Router()


def _get_recheck_runtime_status() -> tuple[bool, list[str], list[str]]:
    active_ids: list[str] = []
    reserved_ids: list[str] = []

    try:
        inspector = celery_app.control.inspect(timeout=1)
        active_data = inspector.active() or {}
        reserved_data = inspector.reserved() or {}

        for tasks in active_data.values():
            for task in tasks:
                if task.get("name") == "tasks.run_admin_recheck_task":
                    active_ids.append(task.get("id", "unknown"))

        for tasks in reserved_data.values():
            for task in tasks:
                if task.get("name") == "tasks.run_admin_recheck_task":
                    reserved_ids.append(task.get("id", "unknown"))
    except Exception:
        pass

    is_running = bool(active_ids or reserved_ids)
    return is_running, active_ids, reserved_ids

@router.callback_query(F.data == "admin_recheck_menu")
async def show_recheck_menu(callback: CallbackQuery, state: FSMContext):
    try:
        total_count = await SubRepo.get_total_count()
        active_count = await SubRepo.get_active_count()
        dead_count = await SubRepo.get_dead_count()
        unknown_region = await SubRepo.get_unknown_region_count()
        maint_mode = await BotState.is_maintenance()
        is_running, active_ids, reserved_ids = _get_recheck_runtime_status()
        runtime_id = active_ids[0] if active_ids else (reserved_ids[0] if reserved_ids else "—")

        text = f"""<blockquote>📡 <b>Панель управления проверкой</b>

📊 <b>Текущая статистика:</b>
━━━━━━━━━━━━━━━━━━
📦 Всего в базе: <b>{total_count}</b>
🟢 Рабочих: <b>{active_count}</b>
🔴 Мёртвых: <b>{dead_count}</b>
🌍 Без региона: <b>{unknown_region}</b>
🧷 Maintenance: <b>{'ON' if maint_mode else 'OFF'}</b>
⚙️ Recheck runtime: <b>{'running' if is_running else 'idle'}</b>
🆔 Task: <code>{runtime_id}</code>
━━━━━━━━━━━━━━━━━━

<b>Типы проверки:</b>
♻️ <b>Full</b> - Проверить ВСЕ конфиги
⚡ <b>Active</b> - Только рабочие (с фильтром)
💀 <b>Dead</b> - Попытка воскрешения мёртвых
🌍 <b>Regions</b> - Обновить геолокацию

<b>Многопроходная проверка:</b>
Чем больше проходов - тем точнее результат,
но дольше проверка.</blockquote>"""

        await admin_edit_or_answer(
            callback, state, text,
            reply_markup=recheck_menu_kb()
        )

    except Exception as e:
        logger.error(f"Error showing recheck menu: {e}")
        await callback.answer("❌ Ошибка загрузки меню", show_alert=True)

@router.callback_query(F.data.startswith("admin_recheck_run_"))
async def run_recheck(callback: CallbackQuery, state: FSMContext):
    try:
        await callback.answer("⏳ Запуск проверки...", show_alert=False)
    except Exception:
        pass

    data_parts = callback.data.split("_")

    if len(data_parts) < 5:
        await callback.answer("❌ Ошибка: неверный формат данных", show_alert=True)
        return

    mode = data_parts[3]
    try:
        passes = int(data_parts[4]) if len(data_parts) > 4 else 1
    except ValueError:
        passes = 1

    mode_info = {
        "all": ("♻️ Full", "проверка ВСЕХ конфигов"),
        "active": ("⚡ Active", "проверка рабочих конфигов"),
        "dead": ("💀 Dead", "попытка воскрешения"),
    }.get(mode, ("❓ Unknown", "неизвестный режим"))

    mode_text, mode_desc = mode_info

    if await BotState.is_maintenance():
        is_running, active_ids, reserved_ids = _get_recheck_runtime_status()
        if not is_running:
            await BotState.set_maintenance(False)
            await Reporter.send_admin_action(
                callback.bot,
                f"Stale maintenance mode auto-reset by admin {callback.from_user.id} before recheck start",
            )
        else:
            active_hint = active_ids[0] if active_ids else (reserved_ids[0] if reserved_ids else "unknown")
            await Reporter.send_admin_action(
                callback.bot,
                f"Recheck start blocked for admin {callback.from_user.id}: active task {active_hint}",
            )
            await callback.answer("⚠️ Проверка уже запущена! Дождитесь окончания.", show_alert=True)
            return

    try:
        await BotState.set_maintenance(True)
        logger.info(f"Starting recheck: mode={mode}, passes={passes}")

        try:
            if mode == "all":
                subs_count = await SubRepo.get_total_count()
            elif mode == "active":
                subs_count = await SubRepo.get_active_count()
            elif mode == "dead":
                subs_count = await SubRepo.get_dead_count()
            else:
                subs_count = 0
        except Exception as e:
            logger.error(f"Error getting subs count: {e}")
            subs_count = "?"

        start_text = f"""<blockquote>⛔️ <b>MAINTENANCE MODE ACTIVE</b>

🚀 <b>Запускается проверка...</b>

📋 <b>Параметры:</b>
• Режим: {mode_text}
• Проходов: {passes}
• Конфигов: ~{subs_count}

⏳ Инициализация...
━━━━━━━━━━━━━━━━━━
⚠️ Бот временно недоступен для пользователей
Во время проверки подписки не выдаются</blockquote>"""

        msg_obj = callback.message
        try:
            res = await callback.message.edit_text(
                text=start_text,
                reply_markup=None,
                parse_mode="HTML"
            )
            if isinstance(res, Message):
                msg_obj = res
        except TelegramBadRequest:
            msg_obj = await callback.message.answer(
                text=start_text,
                parse_mode="HTML"
            )

        from tasks import run_admin_recheck_task

        task = run_admin_recheck_task.delay(
            mode=mode,
            total_passes=passes,
            chat_id=msg_obj.chat.id,
            message_id=msg_obj.message_id
        )

        await Reporter.send_admin_action(
            callback.bot,
            f"Recheck queued by admin {callback.from_user.id}: task_id={task.id}, mode={mode}, passes={passes}, approx_subs={subs_count}",
        )

        logger.info(f"Recheck task started: task_id={task.id}")

        await callback.answer(
            f"✅ Задача #{task.id[:8]} запущена!\nСледите за обновлениями выше.",
            show_alert=True
        )

    except Exception as e:
        logger.error(f"Error starting recheck: {e}", exc_info=True)
        await BotState.set_maintenance(False)
        await Reporter.send_admin_action(
            callback.bot,
            f"Recheck start failed for admin {callback.from_user.id}: {e}",
        )

        error_text = f"""<blockquote>❌ <b>Ошибка запуска проверки</b>

💬 {str(e)[:200]}

🔧 Попробуйте:
• Подождать 30 сек и повторить
• Проверить логи: <code>pm2 logs VPN_Worker</code>
• Обратиться к администратору</blockquote>"""

        try:
            await callback.message.answer(
                error_text,
                reply_markup=recheck_menu_kb(),
                parse_mode="HTML"
            )
        except Exception:
            await callback.answer("❌ Критическая ошибка!", show_alert=True)

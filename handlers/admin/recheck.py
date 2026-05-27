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
        stats = await SubRepo.get_recheck_stats()
        total_count = stats["total"]
        active_count = stats["active"]
        dead_count = stats["dead"]
        unknown_region = stats["unknown_region"]
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

<b>Режим проверки:</b>
Сейчас используется только 1 проход
для каждого конфига.</blockquote>"""

        await admin_edit_or_answer(
            callback, state, text,
            reply_markup=recheck_menu_kb()
        )

    except Exception as e:
        logger.error(f"Error showing recheck menu: {e}")
        await callback.answer("❌ Ошибка загрузки меню", show_alert=True)


@router.callback_query(F.data == "admin_recheck_stop_active")
async def stop_active_recheck(callback: CallbackQuery, state: FSMContext):
    if not callback.bot or not callback.from_user:
        return
    try:
        is_running, active_ids, reserved_ids = _get_recheck_runtime_status()
        if not is_running:
            await BotState.set_maintenance(False)
            await callback.answer("ℹ️ Активных recheck-задач нет", show_alert=True)
            await show_recheck_menu(callback, state)
            return

        task_ids = sorted(
            {
                task_id
                for task_id in (active_ids + reserved_ids)
                if task_id and task_id != "unknown"
            }
        )

        revoked_count = 0
        for task_id in task_ids:
            try:
                celery_app.control.revoke(task_id, terminate=True, signal="SIGTERM")
                revoked_count += 1
            except Exception:
                pass

        await BotState.set_maintenance(False)
        await Reporter.send_admin_action(
            callback.bot,
            f"Recheck stop requested by admin {callback.from_user.id}: revoked={revoked_count}, active_ids={active_ids}, reserved_ids={reserved_ids}",
        )

        await callback.answer(
            f"🛑 Остановил задач: {revoked_count}",
            show_alert=True,
        )
        await asyncio.sleep(0.3)
        await show_recheck_menu(callback, state)
    except Exception as e:
        logger.error(f"Error stopping recheck task: {e}", exc_info=True)
        await callback.answer("❌ Не удалось завершить активную задачу", show_alert=True)


@router.callback_query(F.data.startswith("admin_recheck_run_"))
async def run_recheck(callback: CallbackQuery, state: FSMContext):
    if not callback.bot or not callback.data or not callback.from_user or not isinstance(callback.message, Message):
        return
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
            stats = await SubRepo.get_recheck_stats()
            if mode == "all":
                subs_count = stats["total"]
            elif mode == "active":
                subs_count = stats["active"]
            elif mode == "dead":
                subs_count = stats["dead"]
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

        task = getattr(run_admin_recheck_task, "delay")(
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

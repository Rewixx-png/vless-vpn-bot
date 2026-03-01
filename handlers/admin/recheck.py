import asyncio
from aiogram import Router, F
from aiogram.types import CallbackQuery
from aiogram.fsm.context import FSMContext

from keyboards.admin import back_to_admin, recheck_menu_kb
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
        "⚡ <b>Active:</b> Проверить только ЖИВЫЕ ключи (можно выбрать кол-во проходов).\n"
        "💀 <b>Dead:</b> Проверить только МЕРТВЫЕ (для воскрешения).</blockquote>",
        reply_markup=recheck_menu_kb()
    )

@router.callback_query(F.data.startswith("admin_recheck_run_"))
async def run_recheck(callback: CallbackQuery, state: FSMContext):
    try:
        await callback.answer()
    except Exception:
        pass

    data_parts = callback.data.split("_")
    mode = data_parts[3] if len(data_parts) > 3 else ""
    passes = 1
    if len(data_parts) > 4:
        passes = int(data_parts[4])

    mode_text = {
        "all": "ВСЕ",
        "active": "ЖИВЫЕ",
        "dead": "МЕРТВЫЕ"
    }.get(mode, "Unknown")

    BotState.set_maintenance(True)

    try:
        msg = await callback.message.answer(
            f"<blockquote>⛔️ <b>MAINTENANCE MODE ACTIVE</b>\n\n"
            f"🔍 <b>Подготовка задачи ({mode_text}, Проходов: {passes})</b>\n"
            "🚀 Задача передается в Celery Worker...\n"
            "⏳ Пожалуйста, подождите. UI скоро обновится.</blockquote>",
            parse_mode="HTML"
        )

        from tasks import run_admin_recheck_task
        run_admin_recheck_task.delay(mode, passes, msg.chat.id, msg.message_id)
        
    except Exception as e:
        BotState.set_maintenance(False)
        try:
            await callback.message.answer(
                "❌ Ошибка при запуске задачи в Celery.",
                reply_markup=recheck_menu_kb(),
                parse_mode="HTML"
            )
        except Exception:
            pass

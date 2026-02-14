from aiogram import Router, F
from aiogram.types import CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.exceptions import TelegramBadRequest
from config import config
from keyboards.admin import main_admin_kb

router = Router()

@router.callback_query(F.data == "admin_home")
async def admin_dashboard(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id not in config.ADMIN_IDS:
        return
    
    await state.clear()
    
    # Оборачиваем текст в blockquote
    text = (
        "<blockquote>"
        "🛠 <b>Control Panel</b>\n"
        "Управление ботом и серверами."
        "</blockquote>"
    )
    
    try:
        await callback.message.delete()
    except TelegramBadRequest:
        pass
    except Exception:
        pass
    
    await callback.message.answer(
        text,
        parse_mode="HTML",
        reply_markup=main_admin_kb()
    )
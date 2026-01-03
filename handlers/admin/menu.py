from aiogram import Router, F
from aiogram.types import CallbackQuery
from aiogram.fsm.context import FSMContext
from config import config
from keyboards.admin import main_admin_kb

router = Router()

@router.callback_query(F.data == "admin_home")
async def admin_dashboard(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id not in config.ADMIN_IDS:
        return
    await state.clear()
    await callback.message.edit_text(
        "🛠 <b>Control Panel</b>\n"
        "Управление ботом и серверами.",
        parse_mode="HTML",
        reply_markup=main_admin_kb()
    )
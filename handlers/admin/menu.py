from aiogram import Router, F
from aiogram.types import CallbackQuery
from aiogram.fsm.context import FSMContext
from config import config
from handlers.admin.utils import admin_edit_or_answer

router = Router()

@router.callback_query(F.data == "admin_home")
async def admin_dashboard(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id not in config.ADMIN_IDS:
        return
    
    text = (
        "🛠 <b>Control Panel</b>\n"
        "Управление ботом и серверами."
    )
    
    await admin_edit_or_answer(callback, state, text)

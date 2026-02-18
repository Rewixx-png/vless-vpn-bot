from aiogram import Router, F
from aiogram.types import CallbackQuery
from aiogram.fsm.context import FSMContext
from config import config
from database.repo import SystemRepo
from keyboards.admin import main_admin_kb
from handlers.admin.utils import admin_edit_or_answer

router = Router()

@router.callback_query(F.data == "admin_home")
async def admin_dashboard(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id not in config.ADMIN_IDS:
        return
    
    # Check collector status
    enabled_str = await SystemRepo.get_config("collector_enabled")
    collector_active = enabled_str != "false"
    
    text = (
        "🛠 <b>Control Panel</b>\n"
        "Управление ботом и серверами."
    )
    
    await admin_edit_or_answer(callback, state, text, reply_markup=main_admin_kb(collector_active))

@router.callback_query(F.data == "toggle_collector")
async def toggle_collector(callback: CallbackQuery, state: FSMContext):
    enabled_str = await SystemRepo.get_config("collector_enabled")
    is_enabled = enabled_str != "false"
    
    new_state = not is_enabled
    await SystemRepo.set_config("collector_enabled", "true" if new_state else "false")
    
    status_text = "🟢 ВКЛЮЧЕН" if new_state else "🔴 ВЫКЛЮЧЕН"
    await callback.answer(f"Collector {status_text}")
    
    # Refresh menu
    await admin_dashboard(callback, state)

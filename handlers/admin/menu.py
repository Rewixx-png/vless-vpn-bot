from aiogram import Router, F
from aiogram.types import CallbackQuery
from aiogram.fsm.context import FSMContext
from config import config
from database.repo import SystemRepo
from keyboards.admin import main_admin_kb
from handlers.admin.utils import admin_edit_or_answer
from tasks import run_collector_task

router = Router()

@router.callback_query(F.data == "admin_home")
async def admin_dashboard(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id not in config.ADMIN_IDS:
        return
    
    enabled_str = await SystemRepo.get_config("collector_enabled")
    collector_active = enabled_str != "false"
    
    text = (
        "🛠 <b>Control Panel</b>\n"
        "Управление ботом и серверами.\n\n"
        "<i>💡 Кнопка «Коллектор: ON/OFF» позволяет включать и отключать фоновый сборщик серверов.</i>"
    )
    
    await admin_edit_or_answer(callback, state, text, reply_markup=main_admin_kb(collector_active))

@router.callback_query(F.data == "toggle_collector")
async def toggle_collector(callback: CallbackQuery, state: FSMContext):
    enabled_str = await SystemRepo.get_config("collector_enabled")
    is_enabled = enabled_str != "false"
    
    new_state = not is_enabled
    await SystemRepo.set_config("collector_enabled", "true" if new_state else "false")
    
    status_text = "🟢 ВКЛЮЧЕН" if new_state else "🔴 ВЫКЛЮЧЕН"
    await callback.answer(f"Сборщик серверов {status_text}", show_alert=True)
    
    if new_state:
        # ПРИНУДИТЕЛЬНЫЙ ЗАПУСК КОЛЛЕКТОРА
        run_collector_task.delay()
        await callback.message.answer("🚀 <b>Коллектор запущен принудительно!</b>\nРезультаты появятся в логах.", parse_mode="HTML")
    
    await admin_dashboard(callback, state)

from aiogram import Router, F
from aiogram.types import CallbackQuery
from aiogram.fsm.context import FSMContext
from database.repo import StatsRepo
from keyboards.user import back_to_home
from handlers.user.start import edit_or_answer

router = Router()

@router.callback_query(F.data == "public_stats")
async def show_public_network_stats(callback: CallbackQuery, state: FSMContext):
    """Network Statistics Dashboard"""
    stats = await StatsRepo.get_network_stats()
    
    text = (
        "<b>📊 NETWORK STATUS | СОСТОЯНИЕ</b>\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        f"<b>🌐 Глобальная статистика:</b>\n"
        f"▪️ <b>Серверов онлайн:</b> <code>{stats['active']}</code>\n"
        f"▪️ <b>Доступных стран:</b> <code>{stats['regions_count']}</code>\n"
        f"▪️ <b>Состояние системы:</b> 🟢 Stable\n\n"
        "<b>🗺 Карта покрытия:</b>\n"
        f"<pre>{stats['regions_list']}</pre>\n\n"
        "<i>⚡ Обновление данных происходит в реальном времени.</i>"
    )
    
    await edit_or_answer(callback.message, text, back_to_home(), state, media_url="video")
from aiogram import Router, F
from aiogram.types import CallbackQuery
from database.repo import StatsRepo
from keyboards.user import back_to_home

router = Router()

@router.callback_query(F.data == "public_stats")
async def show_public_network_stats(callback: CallbackQuery):
    """Отображение подробной статистики для пользователей"""
    stats = await StatsRepo.get_network_stats()
    
    text = (
        f"📊 <b>Статус сети VLESS VPN</b>\n\n"
        f"🟢 Всего онлайн: <b>{stats['active']}</b> серверов\n"
        f"🌍 Доступно стран: <b>{stats['regions_count']}</b>\n\n"
        f"<b>Детальная статистика по странам:</b>\n"
        f"<pre>{stats['regions_list']}</pre>\n"
        f"<i>Эти серверы доступны прямо сейчас в вашей подписке.</i>"
    )
    
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=back_to_home())
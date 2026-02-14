from aiogram import Router, F
from aiogram.types import CallbackQuery
from database.repo import StatsRepo
from keyboards.admin import back_to_admin
from handlers.admin.utils import safe_edit_message

router = Router()

@router.callback_query(F.data == "admin_stats")
async def show_stats(callback: CallbackQuery):
    stats = await StatsRepo.get_full_stats()
    # Оборачиваем в blockquote
    text = (
        "<blockquote>"
        f"📊 <b>Detailed Statistics</b>\n\n"
        f"👤 Всего юзеров: <b>{stats['users']}</b>\n"
        f"🔑 Всего ключей в базе: <b>{stats['total_subs']}</b>\n"
        f"🟢 Рабочих ключей: <b>{stats['active_subs']}</b>\n\n"
        f"<b>🌍 Распределение по странам:</b>\n<pre>{stats['regions']}</pre>"
        "</blockquote>"
    )
    await safe_edit_message(callback.message, text, reply_markup=back_to_admin(), parse_mode="HTML")

from aiogram import Router, F
from aiogram.types import CallbackQuery
from aiogram.fsm.context import FSMContext
from database.repo import StatsRepo
from keyboards.admin import back_to_admin
from handlers.admin.utils import admin_edit_or_answer

router = Router()

@router.callback_query(F.data == "admin_stats")
async def show_stats(callback: CallbackQuery, state: FSMContext):
    stats = await StatsRepo.get_full_stats()
    text = (
        "<blockquote>"
        f"📊 <b>Detailed Statistics</b>\n\n"
        f"👤 Всего юзеров: <b>{stats['users']}</b>\n"
        f"🔑 Всего ключей в базе: <b>{stats['total_subs']}</b>\n"
        f"🟢 Рабочих ключей: <b>{stats['active_subs']}</b>\n\n"
        f"<b>🌍 Распределение по странам:</b>\n<pre>{stats['regions']}</pre>"
        "</blockquote>"
    )
    await admin_edit_or_answer(callback, state, text, reply_markup=back_to_admin())

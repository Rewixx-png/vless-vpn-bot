import io
import datetime
import logging
from aiogram import Router, F
from aiogram.types import CallbackQuery, BufferedInputFile
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder

from database.repo import StatsRepo
from database.repo.blacklist import BlacklistRepo
from keyboards.admin import back_to_admin, stats_kb
from handlers.admin.utils import admin_edit_or_answer

router = Router()
logger = logging.getLogger("AdminStats")

@router.callback_query(F.data == "admin_stats")
async def show_stats(callback: CallbackQuery, state: FSMContext):
    try:
        stats = await StatsRepo.get_full_stats()
        
        users = stats.get('users', 0)
        total = stats.get('total_subs', 0)
        active = stats.get('active_subs', 0)
        blacklist = stats.get('blacklist', 0)
        regions = stats.get('regions', 'N/A')
        
        if len(regions) > 3000:
            regions = regions[:3000] + "\n... (список обрезан)"

        text = (
            "<blockquote>"
            f"📊 <b>System Statistics</b>\n\n"
            f"👤 Всего юзеров: <b>{users}</b>\n"
            f"🔑 Ключей в базе: <b>{total}</b>\n"
            f"🟢 Рабочих: <b>{active}</b>\n"
            f"🚫 В черном списке: <b>{blacklist}</b>\n\n"
            f"<b>🌍 Распределение (Code):</b>\n<pre>{regions}</pre>"
            "</blockquote>"
        )
        await admin_edit_or_answer(callback, state, text, reply_markup=stats_kb())
    except Exception as e:
        logger.error(f"Error in stats: {e}", exc_info=True)
        await callback.answer(f"Ошибка статистики: {str(e)}", show_alert=True)

@router.callback_query(F.data == "admin_clear_blacklist_confirm")
async def clear_blacklist_action(callback: CallbackQuery, state: FSMContext):
    try:
        count = await BlacklistRepo.get_count()
        if count == 0:
            await callback.answer("Черный список уже пуст!", show_alert=True)
            return

        await BlacklistRepo.clear_all()
        await callback.answer(f"✅ Удалено {count} записей из ЧС", show_alert=True)
        
        await show_stats(callback, state)
    except Exception as e:
        await callback.answer(f"Ошибка: {e}", show_alert=True)

@router.callback_query(F.data == "admin_dl_users")
async def download_users_list(callback: CallbackQuery):
    try:
        users = await StatsRepo.get_all_users_detailed()
        
        if not users:
            await callback.answer("Юзеров нет", show_alert=True)
            return
            
        lines = ["ID | Username | Registration Date | Limit"]
        lines.append("-" * 50)
        
        for u in users:
            date_str = u.created_at.strftime("%Y-%m-%d") if u.created_at else "N/A"
            username = f"@{u.username}" if u.username else "None"
            limit = u.subscription_limit if u.subscription_limit > 0 else "Unlim"
            lines.append(f"{u.id} | {username} | {date_str} | {limit}")
        
        file_content = "\n".join(lines).encode('utf-8')
        input_file = BufferedInputFile(file_content, filename=f"users_{datetime.date.today()}.txt")
        
        await callback.message.answer_document(
            document=input_file,
            caption="📂 <b>Полный список пользователей бота</b>",
            parse_mode="HTML"
        )
        await callback.answer()
    except Exception as e:
        logger.error(f"Error downloading users: {e}")
        await callback.answer(f"Ошибка выгрузки: {e}", show_alert=True)

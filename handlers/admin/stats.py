import io
import datetime
import logging
from aiogram import Router, F
from aiogram.types import CallbackQuery, BufferedInputFile
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder

from database.repo import StatsRepo
from keyboards.admin import back_to_admin
from handlers.admin.utils import admin_edit_or_answer

router = Router()
logger = logging.getLogger("AdminStats")

def stats_kb():
    kb = InlineKeyboardBuilder()
    kb.button(text="📥 Список Юзеров (.txt)", callback_data="admin_dl_users")
    kb.button(text="🔄 Обновить", callback_data="admin_stats")
    kb.button(text="🔙 Назад", callback_data="admin_home")
    kb.adjust(1)
    return kb.as_markup()

@router.callback_query(F.data == "admin_stats")
async def show_stats(callback: CallbackQuery, state: FSMContext):
    try:
        stats = await StatsRepo.get_full_stats()
        
        # Safe get in case keys are missing during migration
        users = stats.get('users', 0)
        total = stats.get('total_subs', 0)
        active = stats.get('active_subs', 0)
        blacklist = stats.get('blacklist', 0)
        regions = stats.get('regions', 'N/A')
        
        # Truncate if too long to prevent errors
        if len(regions) > 3000:
            regions = regions[:3000] + "\n... (список обрезан)"

        text = (
            "<blockquote>"
            f"📊 <b>System Statistics</b>\n\n"
            f"👤 Всего юзеров: <b>{users}</b>\n"
            f"🔑 Ключей в базе: <b>{total}</b>\n"
            f"🟢 Рабочих: <b>{active}</b>\n"
            f"🚫 В черном списке: <b>{blacklist}</b>\n\n"
            f"<b>🌍 Распределение по странам:</b>\n<pre>{regions}</pre>"
            "</blockquote>"
        )
        await admin_edit_or_answer(callback, state, text, reply_markup=stats_kb())
    except Exception as e:
        logger.error(f"Error in stats: {e}", exc_info=True)
        await callback.answer(f"Ошибка статистики: {str(e)}", show_alert=True)

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

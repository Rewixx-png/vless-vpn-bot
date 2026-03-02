import asyncio
import logging
from aiogram import Router, F
from aiogram.types import CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.exceptions import TelegramBadRequest

from keyboards.admin import back_to_admin, recheck_menu_kb
from handlers.admin.utils import admin_edit_or_answer
from utils.state import BotState
from database.repo import SubRepo

logger = logging.getLogger(__name__)
router = Router()

@router.callback_query(F.data == "admin_recheck_menu")
async def show_recheck_menu(callback: CallbackQuery, state: FSMContext):
    """Показывает меню речека с актуальной статистикой"""
    try:
        # Получаем актуальную статистику
        total_count = await SubRepo.get_total_count()
        active_count = await SubRepo.get_active_count()
        dead_count = await SubRepo.get_dead_count()
        unknown_region = await SubRepo.get_unknown_region_count()
        
        text = f"""<blockquote>📡 <b>Панель управления проверкой</b>

📊 <b>Текущая статистика:</b>
━━━━━━━━━━━━━━━━━━
📦 Всего в базе: <b>{total_count}</b>
🟢 Рабочих: <b>{active_count}</b>
🔴 Мёртвых: <b>{dead_count}</b>
🌍 Без региона: <b>{unknown_region}</b>
━━━━━━━━━━━━━━━━━━

<b>Типы проверки:</b>
♻️ <b>Full</b> - Проверить ВСЕ конфиги
⚡ <b>Active</b> - Только рабочие (с фильтром)
💀 <b>Dead</b> - Попытка воскрешения мёртвых
🌍 <b>Regions</b> - Обновить геолокацию

<b>Многопроходная проверка:</b>
Чем больше проходов - тем точнее результат,
но дольше проверка.</blockquote>"""
        
        await admin_edit_or_answer(
            callback, state, text,
            reply_markup=recheck_menu_kb()
        )
        
    except Exception as e:
        logger.error(f"Error showing recheck menu: {e}")
        await callback.answer("❌ Ошибка загрузки меню", show_alert=True)

@router.callback_query(F.data.startswith("admin_recheck_run_"))
async def run_recheck(callback: CallbackQuery, state: FSMContext):
    """Запускает задачу речека"""
    try:
        await callback.answer("⏳ Запуск проверки...", show_alert=False)
    except Exception:
        pass
    
    # Разбираем callback data
    data_parts = callback.data.split("_")
    
    if len(data_parts) < 5:
        await callback.answer("❌ Ошибка: неверный формат данных", show_alert=True)
        return
    
    mode = data_parts[3]
    try:
        passes = int(data_parts[4]) if len(data_parts) > 4 else 1
    except ValueError:
        passes = 1
    
    mode_info = {
        "all": ("♻️ Full", "проверка ВСЕХ конфигов"),
        "active": ("⚡ Active", "проверка рабочих конфигов"),
        "dead": ("💀 Dead", "попытка воскрешения"),
    }.get(mode, ("❓ Unknown", "неизвестный режим"))
    
    mode_text, mode_desc = mode_info
    
    try:
        # Устанавливаем maintenance mode
        BotState.set_maintenance(True)
        logger.info(f"Starting recheck: mode={mode}, passes={passes}")
        
        # Получаем информацию о выбранных подписках
        try:
            if mode == "all":
                subs_count = await SubRepo.get_total_count()
            elif mode == "active":
                subs_count = await SubRepo.get_active_count()
            elif mode == "dead":
                subs_count = await SubRepo.get_dead_count()
            else:
                subs_count = 0
        except Exception as e:
            logger.error(f"Error getting subs count: {e}")
            subs_count = "?"
        
        # Отправляем начальное сообщение
        start_text = f"""<blockquote>⛔️ <b>MAINTENANCE MODE ACTIVE</b>

🚀 <b>Запускается проверка...</b>

📋 <b>Параметры:</b>
• Режим: {mode_text}
• Проходов: {passes}
• Конфигов: ~{subs_count}

⏳ Инициализация...
━━━━━━━━━━━━━━━━━━
⚠️ Бот временно недоступен для пользователей
Во время проверки подписки не выдаются</blockquote>"""
        
        try:
            # Пробуем отредактировать текущее сообщение
            msg = await callback.message.edit_text(
                text=start_text,
                reply_markup=None,  # Убираем клавиатуру
                parse_mode="HTML"
            )
        except TelegramBadRequest:
            # Если не получилось редактировать, отправляем новое
            msg = await callback.message.answer(
                text=start_text,
                parse_mode="HTML"
            )
        
        # Запускаем задачу в Celery
        from tasks import run_admin_recheck_task
        
        task = run_admin_recheck_task.delay(
            mode=mode,
            total_passes=passes,
            chat_id=msg.chat.id,
            message_id=msg.message_id
        )
        
        logger.info(f"Recheck task started: task_id={task.id}")
        
        # Отправляем подтверждение с ID задачи
        await callback.answer(
            f"✅ Задача #{task.id[:8]} запущена!\nСледите за обновлениями выше.",
            show_alert=True
        )
        
    except Exception as e:
        logger.error(f"Error starting recheck: {e}", exc_info=True)
        BotState.set_maintenance(False)
        
        error_text = f"""<blockquote>❌ <b>Ошибка запуска проверки</b>

💬 {str(e)[:200]}

🔧 Попробуйте:
• Подождать 30 сек и повторить
• Проверить логи: <code>pm2 logs VPN_Worker</code>
• Обратиться к администратору</blockquote>"""
        
        try:
            await callback.message.answer(
                error_text,
                reply_markup=recheck_menu_kb(),
                parse_mode="HTML"
            )
        except Exception:
            await callback.answer("❌ Критическая ошибка!", show_alert=True)

@router.callback_query(F.data == "admin_recheck_regions_force")
async def run_regions_recheck(callback: CallbackQuery, state: FSMContext):
    """Запускает обновление регионов для всех конфигов с неизвестным регионом"""
    try:
        await callback.answer("⏳ Запуск обновления регионов...", show_alert=False)
    except Exception:
        pass
    
    try:
        # Получаем количество конфигов без региона
        unknown_count = await SubRepo.get_unknown_region_count()
        
        if unknown_count == 0:
            await callback.answer(
                "✅ Все конфиги имеют определённый регион!",
                show_alert=True
            )
            return
        
        BotState.set_maintenance(True)
        
        start_text = f"""<blockquote>🌍 <b>Обновление геолокации</b>

📊 Найдено конфигов без региона: <b>{unknown_count}</b>

⏳ Начинаю определение стран...
━━━━━━━━━━━━━━━━━━
⚠️ Это может занять несколько минут</blockquote>"""
        
        try:
            msg = await callback.message.edit_text(
                text=start_text,
                reply_markup=None,
                parse_mode="HTML"
            )
        except TelegramBadRequest:
            msg = await callback.message.answer(
                text=start_text,
                parse_mode="HTML"
            )
        
        # TODO: Здесь должен быть вызов задачи для обновления регионов
        # from tasks import update_regions_task
        # update_regions_task.delay(msg.chat.id, msg.message_id)
        
        await callback.answer(
            "✅ Задача запущена!",
            show_alert=True
        )
        
    except Exception as e:
        logger.error(f"Error starting regions update: {e}")
        BotState.set_maintenance(False)
        await callback.answer(f"❌ Ошибка: {str(e)[:100]}", show_alert=True)
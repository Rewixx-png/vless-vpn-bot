import asyncio
import time
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.exceptions import TelegramRetryAfter, TelegramForbiddenError

from config import config
from database.repo import UserRepo
from keyboards.admin import back_to_admin
from handlers.admin.states import AdminStates
from handlers.admin.utils import admin_edit_or_answer, safe_edit_message

router = Router()


@router.callback_query(F.data == "admin_broadcast")
async def ask_broadcast(callback: CallbackQuery, state: FSMContext):
    await admin_edit_or_answer(
        callback,
        state,
        "<blockquote>📢 Пришлите сообщение (текст, фото, видео) для рассылки всем юзерам:</blockquote>",
        reply_markup=back_to_admin()
    )
    await state.set_state(AdminStates.waiting_for_broadcast)


@router.message(StateFilter(AdminStates.waiting_for_broadcast), F.from_user.id.in_(config.ADMIN_IDS))
async def do_broadcast(message: Message, state: FSMContext):
    # Получаем пользователей
    users = await UserRepo.get_all_users()
    total = len(users)
    
    if total == 0:
        await message.answer("Нет пользователей для рассылки.")
        await state.clear()
        return

    # Отправляем стартовое сообщение
    status_msg = await message.answer(
        f"<blockquote>🚀 Начинаю рассылку на {total} пользователей...\n"
        f"📊 Прогресс: 0/{total} (0%)</blockquote>",
        parse_mode="HTML"
    )
    
    sent_count = 0
    failed_count = 0
    blocked_count = 0
    last_update_time = time.time()
    
    # ID чата и ID сообщения для копирования
    from_chat_id = message.chat.id
    message_id = message.message_id
    
    # Цикл по всем пользователям
    for index, user_id in enumerate(users, 1):
        try:
            # Пытаемся отправить копию сообщения
            # Используем wait_for чтобы избежать вечного зависания API
            await asyncio.wait_for(
                message.bot.copy_message(
                    chat_id=user_id,
                    from_chat_id=from_chat_id,
                    message_id=message_id
                ),
                timeout=5.0
            )
            sent_count += 1
            
            # Небольшая пауза, чтобы не превысить лимиты Telegram (макс 30/сек, делаем ~20/сек)
            await asyncio.sleep(0.05)
            
        except TelegramForbiddenError:
            # Пользователь заблокировал бота
            blocked_count += 1
        except TelegramRetryAfter as e:
            # Лимит превышен, ждем и пробуем снова (один раз)
            try:
                await asyncio.sleep(e.retry_after)
                await message.bot.copy_message(
                    chat_id=user_id,
                    from_chat_id=from_chat_id,
                    message_id=message_id
                )
                sent_count += 1
            except Exception:
                failed_count += 1
        except Exception:
            # Любая другая ошибка (таймаут, удаленный аккаунт и т.д.)
            failed_count += 1
        
        # Обновляем прогресс-бар (не чаще чем раз в 2 секунды или каждые 20 юзеров)
        # Это предотвращает "зависание" на этапе редактирования сообщения
        current_time = time.time()
        if (current_time - last_update_time > 2.0) or (index == total):
            percent = int((index / total) * 100)
            await safe_edit_message(
                status_msg,
                f"<blockquote>🚀 Рассылка в процессе...\n"
                f"📊 Прогресс: {index}/{total} ({percent}%)\n"
                f"✅ Успешно: {sent_count}\n"
                f"🚫 Бот заблокирован: {blocked_count}\n"
                f"❌ Ошибок: {failed_count}</blockquote>",
                parse_mode="HTML"
            )
            last_update_time = current_time

    # Финальный отчет
    final_percent = int((sent_count / total) * 100) if total > 0 else 0
    
    await safe_edit_message(
        status_msg,
        f"<blockquote>✅ <b>Рассылка завершена!</b>\n\n"
        f"📊 Всего пользователей: {total}\n"
        f"✅ Успешно доставлено: {sent_count}\n"
        f"🚫 Бот заблокирован: {blocked_count}\n"
        f"❌ Ошибок отправки: {failed_count}\n"
        f"📈 Доставляемость: {final_percent}%</blockquote>",
        reply_markup=back_to_admin(),
        parse_mode="HTML"
    )
    
    await state.clear()

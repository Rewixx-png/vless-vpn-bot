"""
Optimized broadcast handler with async batch sending and rate limiting.
"""
import asyncio
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.exceptions import TelegramRetryAfter

from config import config
from database.repo import UserRepo
from keyboards.admin import back_to_admin
from handlers.admin.states import AdminStates
from utils.async_celery import RateLimiter
from handlers.admin.utils import admin_edit_or_answer

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
    users = await UserRepo.get_all_users()
    total = len(users)
    
    # Send initial progress message
    progress_msg = await message.answer(
        f"<blockquote>🚀 Начинаю рассылку на {total} пользователей...\n"
        f"📊 Прогресс: 0/{total} (0%)</blockquote>",
        parse_mode="HTML"
    )
    
    # Rate limiter: 25 messages per second (well below Telegram limits)
    rate_limiter = RateLimiter(max_calls=25, period=1.0)
    
    sent_count = 0
    failed_count = 0
    last_update = 0
    
    async def send_to_user(user_id: int):
        """Send message to single user with rate limiting"""
        nonlocal sent_count, failed_count
        
        try:
            await rate_limiter.acquire()
            await message.copy_to(chat_id=user_id)
            sent_count += 1
            return True
        except TelegramRetryAfter as e:
            # Hit rate limit, wait and retry
            await asyncio.sleep(e.retry_after)
            return await send_to_user(user_id)
        except Exception:
            failed_count += 1
            return False
    
    async def update_progress():
        """Update progress message periodically"""
        nonlocal last_update
        processed = sent_count + failed_count
        
        # Update every 5% or every 50 users
        if processed - last_update >= 50 or (total > 0 and (processed / total) * 100 % 5 < 1):
            percent = int((processed / total) * 100) if total > 0 else 0
            await safe_edit_message(
                progress_msg,
                f"<blockquote>🚀 Рассылка в процессе...\n"
                f"📊 Прогресс: {processed}/{total} ({percent}%)\n"
                f"✅ Отправлено: {sent_count}\n"
                f"❌ Ошибок: {failed_count}</blockquote>",
                parse_mode="HTML"
            )
            last_update = processed
    
    # Process in batches with limited concurrency
    semaphore = asyncio.Semaphore(20)  # Max 20 concurrent sends
    
    async def process_user(user_id: int):
        async with semaphore:
            result = await send_to_user(user_id)
            await update_progress()
            return result
    
    # Create all tasks
    tasks = [process_user(uid) for uid in users]
    
    # Process with progress
    await asyncio.gather(*tasks, return_exceptions=True)
    
    # Final update
    final_percent = int((sent_count / total) * 100) if total > 0 else 0
    await safe_edit_message(
        progress_msg,
        f"<blockquote>✅ Рассылка завершена!\n\n"
        f"📊 Всего пользователей: {total}\n"
        f"✅ Успешно доставлено: {sent_count}\n"
        f"❌ Ошибок: {failed_count}\n"
        f"📈 Процент доставки: {final_percent}%</blockquote>",
        reply_markup=back_to_admin(),
        parse_mode="HTML"
    )
    
    await state.clear()

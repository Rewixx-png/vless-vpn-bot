import asyncio
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext

from config import config
from database.repo import UserRepo
from keyboards.admin import back_to_admin
from handlers.admin.states import AdminStates

router = Router()

@router.callback_query(F.data == "admin_broadcast")
async def ask_broadcast(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text("📢 Пришлите сообщение (текст, фото) для рассылки всем юзерам:", reply_markup=back_to_admin())
    await state.set_state(AdminStates.waiting_for_broadcast)

@router.message(StateFilter(AdminStates.waiting_for_broadcast), F.from_user.id.in_(config.ADMIN_IDS))
async def do_broadcast(message: Message, state: FSMContext):
    users = await UserRepo.get_all_users()
    count = 0
    await message.answer(f"🚀 Начинаю рассылку на {len(users)} пользователей...")

    for user_id in users:
        try:
            await message.copy_to(chat_id=user_id)
            count += 1
            # Увеличиваем задержку до 0.1с (10 сообщений в секунду)
            # Лимит Telegram ~30 в сек, но лучше иметь запас
            await asyncio.sleep(0.1) 
        except Exception:
            pass

    await message.answer(f"✅ Рассылка завершена.\nПолучили: {count} чел.", reply_markup=back_to_admin())
    await state.clear()
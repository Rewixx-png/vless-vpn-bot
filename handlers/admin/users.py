from aiogram import Router, F
from aiogram.types import CallbackQuery
from aiogram.fsm.context import FSMContext
from database.repo import UserRepo
from keyboards.admin import users_list_kb, user_detail_kb
from handlers.admin.utils import admin_edit_or_answer

router = Router()

@router.callback_query(F.data.startswith("admin_users_list_"))
async def show_users_list(callback: CallbackQuery, state: FSMContext):
    offset = int(callback.data.split("_")[-1])
    limit = 10
    
    total = await UserRepo.get_users_count()
    users = await UserRepo.get_users_paginated(limit, offset)
    
    text = (
        f"👥 <b>Список пользователей</b>\n\n"
        f"Всего: {total}\n"
        f"Страница: {(offset // limit) + 1}"
    )
    
    await admin_edit_or_answer(
        callback,
        state,
        text,
        reply_markup=users_list_kb(users, offset, total)
    )

@router.callback_query(F.data.startswith("admin_user_view_"))
async def show_user_detail(callback: CallbackQuery, state: FSMContext):
    parts = callback.data.split("_")
    user_id = int(parts[3])
    back_offset = int(parts[4])
    
    user = await UserRepo.get_user(user_id)
    if not user:
        await callback.answer("Юзер не найден")
        return

    username = f"@{user.username}" if user.username else "Нет"
    date_str = user.created_at.strftime("%Y-%m-%d %H:%M:%S") if user.created_at else "N/A"
    
    limit_txt = "Безлимит" if user.subscription_limit == 0 else str(user.subscription_limit)
    
    filter_c = user.country_filter if user.country_filter else "Все"
    filter_t = user.tags_filter if user.tags_filter else "Нет"

    text = (
        f"👤 <b>Профиль пользователя</b>\n\n"
        f"🆔 ID: <code>{user.id}</code>\n"
        f"👤 Username: {username}\n"
        f"📅 Регистрация: {date_str}\n\n"
        f"🔢 Лимит подписки: {limit_txt}\n"
        f"🌍 Фильтр стран: {filter_c}\n"
        f"🏷 Фильтр тегов: {filter_t}"
    )
    
    await admin_edit_or_answer(
        callback,
        state,
        text,
        reply_markup=user_detail_kb(user.id, back_offset)
    )
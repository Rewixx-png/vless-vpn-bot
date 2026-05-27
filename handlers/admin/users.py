from aiogram import Router, F
from aiogram.types import CallbackQuery
from aiogram.fsm.context import FSMContext
from database.repo import UserRepo
from keyboards.admin import users_list_kb, user_detail_kb
from handlers.admin.utils import admin_edit_or_answer

router = Router()

@router.callback_query(F.data.startswith("admin_users_list_"))
async def show_users_list(callback: CallbackQuery, state: FSMContext):
    if not callback.data:
        return
    offset = int(callback.data.split("_")[-1])
    limit = 10
    
    total = await UserRepo.get_users_count()
    users = await UserRepo.get_users_paginated(limit, offset)
    
    page_num = (offset // limit) + 1
    total_pages = (total + limit - 1) // limit
    text = (
        "<b>👥 Пользователи</b>\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        f"  Всего: <b>{total}</b>  |  Стр. {page_num}/{total_pages}"
    )
    
    await admin_edit_or_answer(
        callback,
        state,
        text,
        reply_markup=users_list_kb(users, offset, total)
    )

@router.callback_query(F.data.startswith("admin_user_view_"))
async def show_user_detail(callback: CallbackQuery, state: FSMContext):
    if not callback.data:
        return
    parts = callback.data.split("_")
    user_id = int(parts[3])
    back_offset = int(parts[4])
    
    user = await UserRepo.get_user(user_id)
    if not user:
        await callback.answer("Юзер не найден")
        return

    user_username = getattr(user, "username")
    username = f"@{user_username}" if user_username else "Нет"
    user_created_at = getattr(user, "created_at")
    date_str = user_created_at.strftime("%Y-%m-%d %H:%M:%S") if user_created_at else "N/A"
    
    user_subscription_limit = getattr(user, "subscription_limit")
    limit_txt = "Безлимит" if user_subscription_limit == 0 else str(user_subscription_limit)
    
    user_country_filter = getattr(user, "country_filter")
    filter_c = user_country_filter if user_country_filter else "Все"
    user_tags_filter = getattr(user, "tags_filter")
    filter_t = user_tags_filter if user_tags_filter else "Нет"

    text = (
        "<b>👤 Профиль пользователя</b>\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        f"🆔 ID: <code>{user.id}</code>\n"
        f"📛 Username: {username}\n"
        f"📅 Регистрация: {date_str}\n\n"
        f"🔢 Лимит: {limit_txt}\n"
        f"🌍 Страны: {filter_c}\n"
        f"🏷 Теги: {filter_t}"
    )
    
    await admin_edit_or_answer(
        callback,
        state,
        text,
        reply_markup=user_detail_kb(int(getattr(user, "id")), back_offset)
    )
import urllib.parse
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from database.repo import SubRepo, UserRepo, SystemRepo
from keyboards.user import settings_countries_kb, back_to_home, settings_main_kb, settings_limit_kb, sub_action_kb
from handlers.user.states import UserStates
from handlers.user.start import edit_or_answer
from config import config

router = Router()

@router.callback_query(F.data == "my_subscription")
async def give_subscription_menu(callback: CallbackQuery):
    user_id = callback.from_user.id
    
    domain = await SystemRepo.get_config("public_domain")
    
    # Определяем протокол
    protocol = "https" if domain else "http"
    host = domain if domain else f"{config.PUBLIC_IP}:{config.WEB_PORT}"
    
    sub_url = f"{protocol}://{host}/sub?id={user_id}"

    user = await UserRepo.get_user(user_id)
    limit_txt = "Все доступные"
    if user and user.subscription_limit > 0:
        limit_txt = f"{user.subscription_limit} шт."

    # Генерируем Deep Link для FlClash (экспериментально)
    # Формат: clash://install-config?url=<encoded_url>&name=<name>
    encoded_url = urllib.parse.quote(sub_url)
    flclash_deep_link = f"clash://install-config?url={encoded_url}&name=VLESS-VPN"
    
    # Текст сообщения
    text = (
        "📦 <b>Ваша ссылка подписки</b>\n\n"
        f"🔗 <b>URL:</b>\n<code>{sub_url}</code>\n\n"
        "👆 <i>Нажмите на ссылку, чтобы скопировать.</i>\n\n"
        "⚙️ <b>Как добавить в FlClash / v2rayNG:</b>\n"
        "1. Скопируйте ссылку выше.\n"
        "2. Откройте приложение.\n"
        "3. Нажмите кнопку ➕ -> «Импорт из буфера обмена» (Import from Clipboard).\n"
        "4. Обновите подписку.\n\n"
        f"ℹ️ Ключей в подписке: <b>{limit_txt}</b>"
    )

    if not domain:
        text += (
            "\n\n⚠️ <b>Важно:</b> Ссылка использует <b>HTTP</b>.\n"
            "Если приложение выдает ошибку, включите в настройках приложения:\n"
            "<i>Allow Insecure / Разрешить небезопасные соединения</i>"
        )

    await callback.message.edit_text(
        text, 
        parse_mode="HTML", 
        reply_markup=sub_action_kb(sub_url, flclash_deep_link)
    )

@router.callback_query(F.data == "settings_main")
async def open_settings_main(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    user = await UserRepo.get_user(callback.from_user.id)
    limit = user.subscription_limit if user else 0
    
    await callback.message.edit_text(
        "⚙️ <b>Настройки подписки</b>\n\n"
        "Здесь можно настроить фильтры, если приложение не справляется с большим списком серверов.",
        parse_mode="HTML",
        reply_markup=settings_main_kb(limit)
    )

@router.callback_query(F.data == "settings_limit")
async def open_settings_limit(callback: CallbackQuery):
    user = await UserRepo.get_user(callback.from_user.id)
    limit = user.subscription_limit if user else 0
    
    await callback.message.edit_text(
        "🔢 <b>Лимит серверов</b>\n\n"
        "Бот может выдавать только N самых быстрых серверов.\n"
        "0 = Безлимит (все доступные).",
        parse_mode="HTML",
        reply_markup=settings_limit_kb(limit)
    )

@router.callback_query(F.data.startswith("set_limit_"))
async def set_limit_value(callback: CallbackQuery, state: FSMContext):
    val = callback.data.split("set_limit_")[1]
    
    if val == "custom":
        await callback.message.edit_text(
            "✍️ <b>Введите число ключей:</b>\n"
            "(0 для сброса лимита)",
            parse_mode="HTML",
            reply_markup=back_to_home()
        )
        await state.set_state(UserStates.waiting_for_custom_limit)
        return

    limit = int(val)
    await UserRepo.update_subscription_limit(callback.from_user.id, limit)
    await open_settings_main(callback, state)

@router.message(StateFilter(UserStates.waiting_for_custom_limit))
async def process_custom_limit_input(message: Message, state: FSMContext):
    try:
        await message.delete()
    except: pass

    try:
        limit = int(message.text.strip())
        if limit < 0: raise ValueError
        
        await UserRepo.update_subscription_limit(message.from_user.id, limit)
        await state.clear()
        
        await edit_or_answer(
            message, 
            f"✅ Лимит: <b>{limit}</b>",
            settings_main_kb(limit),
            state
        )

    except ValueError:
        await edit_or_answer(message, "⚠️ Введите число.", back_to_home(), state)

@router.callback_query(F.data == "settings_countries")
async def open_settings_countries(callback: CallbackQuery):
    all_regions = await SubRepo.get_regions()
    user_filter = await UserRepo.get_user_filter(callback.from_user.id)

    await callback.message.edit_text(
        "🌍 <b>Фильтр стран</b>\n(✅ = Включено)",
        parse_mode="HTML",
        reply_markup=settings_countries_kb(all_regions, user_filter)
    )

@router.callback_query(F.data.startswith("toggle_country_"))
async def toggle_country(callback: CallbackQuery):
    region = callback.data.split("toggle_country_")[1]
    user_id = callback.from_user.id

    all_regions = await SubRepo.get_regions()
    user_filter = await UserRepo.get_user_filter(user_id)

    if user_filter is None:
        new_filter = [r for r in all_regions if r != region]
    else:
        new_filter = user_filter.copy()
        if region in new_filter:
            new_filter.remove(region)
        else:
            new_filter.append(region)

    if not new_filter or set(new_filter) == set(all_regions):
        new_filter = None

    await UserRepo.update_user_filter(user_id, new_filter)
    await callback.message.edit_reply_markup(reply_markup=settings_countries_kb(all_regions, new_filter))

@router.callback_query(F.data == "set_all_on")
async def set_all_on(callback: CallbackQuery):
    all_regions = await SubRepo.get_regions()
    await UserRepo.update_user_filter(callback.from_user.id, None)
    await callback.message.edit_reply_markup(reply_markup=settings_countries_kb(all_regions, None))

@router.callback_query(F.data == "set_all_off")
async def set_all_off(callback: CallbackQuery):
    all_regions = await SubRepo.get_regions()
    first = [all_regions[0]] if all_regions else None
    await UserRepo.update_user_filter(callback.from_user.id, first)
    await callback.message.edit_reply_markup(reply_markup=settings_countries_kb(all_regions, first))
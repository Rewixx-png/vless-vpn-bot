import urllib.parse
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from database.repo import SubRepo, UserRepo, SystemRepo
from keyboards.user import settings_countries_kb, back_to_home, settings_main_kb, settings_limit_kb, sub_action_kb, settings_tags_kb
from handlers.user.states import UserStates
from handlers.user.start import edit_or_answer
from config import config
from utils.qr import QRGenerator

router = Router()

@router.callback_query(F.data == "my_subscription")
async def give_subscription_menu(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    
    db_domain = await SystemRepo.get_config("public_domain")
    domain = db_domain if db_domain else config.public_domain
    
    if domain:
        protocol = "https"
        host = domain
    else:
        protocol = "http"
        host = f"{config.PUBLIC_IP}:{config.WEB_PORT}"
    
    sub_url = f"{protocol}://{host}/sub?id={user_id}"

    user = await UserRepo.get_user(user_id)
    limit_txt = "Все доступные (∞)"
    if user and user.subscription_limit > 0:
        limit_txt = f"{user.subscription_limit} лучших"

    encoded_url = urllib.parse.quote(sub_url)
    
    warning = ""
    if protocol == "http":
        warning = (
            "\n\n⚠️ <b>Важно (Android):</b>\n"
            "В настройках клиента включите: <i>Allow Insecure / Небезопасные подключения</i>, так как используется HTTP."
        )

    text = (
        "<b>🔑 PERSONAL ACCESS KEY</b>\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        "<b>🔗 Ваша ссылка подписки:</b>\n"
        f"<code>{sub_url}</code>\n"
        "👆 <i>Нажмите на ссылку для копирования</i>\n\n"
        "<b>📋 Информация о ключе:</b>\n"
        f"▪️ <b>Формат:</b> Auto (VLESS / Clash)\n"
        f"▪️ <b>Серверов:</b> {limit_txt}\n"
        f"▪️ <b>Обновление:</b> Автоматически\n"
        f"{warning}\n\n"
        "<i>⚙️ Используйте кнопку ниже для настройки фильтров (страны, AI, скорость).</i>"
    )

    await edit_or_answer(
        callback.message, 
        text, 
        sub_action_kb(sub_url),
        state,
        media_url="video"
    )

@router.callback_query(F.data == "sub_qr_main")
async def show_main_qr(callback: CallbackQuery):
    user_id = callback.from_user.id
    db_domain = await SystemRepo.get_config("public_domain")
    domain = db_domain if db_domain else config.public_domain
    
    if domain:
        protocol = "https"
        host = domain
    else:
        protocol = "http"
        host = f"{config.PUBLIC_IP}:{config.WEB_PORT}"
    
    sub_url = f"{protocol}://{host}/sub?id={user_id}"
    qr_file = QRGenerator.generate(sub_url)
    
    await callback.message.answer_photo(
        photo=qr_file,
        caption="<b>📱 Ваш QR-код для подключения</b>\nОтсканируйте его в приложении (v2rayNG, V2Box, FlClash и др.)",
        parse_mode="HTML"
    )
    await callback.answer()

@router.callback_query(F.data == "settings_main")
async def open_settings_main(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    last_msg_id = data.get("last_msg_id")
    await state.clear()
    if last_msg_id:
        await state.update_data(last_msg_id=last_msg_id)

    user = await UserRepo.get_user(callback.from_user.id)
    limit = user.subscription_limit if user else 0
    use_fragment = user.use_fragment if user else False
    
    text = (
        "<b>⚙️ CONFIGURATION | НАСТРОЙКИ</b>\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        "Здесь вы можете настроить параметры вашей подписки.\n"
        "Изменения применяются мгновенно при следующем обновлении в приложении.\n\n"
        "<b>Доступные опции:</b>\n"
        "🌍 <b>Страны:</b> Выберите конкретные регионы.\n"
        "⚡ <b>Теги:</b> Фильтр для AI, Игр или Reality.\n"
        "🔢 <b>Лимит:</b> Ограничить кол-во серверов (для старых телефонов).\n"
        "🛡 <b>Фрагментация:</b> Обход жесткого DPI (в РФ/Иране)."
    )
    
    await edit_or_answer(
        callback.message,
        text,
        settings_main_kb(limit, use_fragment),
        state,
        media_url="video"
    )

@router.callback_query(F.data == "toggle_fragment")
async def toggle_fragment_action(callback: CallbackQuery, state: FSMContext):
    user = await UserRepo.get_user(callback.from_user.id)
    if user:
        new_state = not user.use_fragment
        await UserRepo.update_fragment_setting(user.id, new_state)
    await open_settings_main(callback, state)

@router.callback_query(F.data == "settings_tags")
async def open_settings_tags(callback: CallbackQuery, state: FSMContext):
    user_tags = await UserRepo.get_user_tags(callback.from_user.id)
    
    text = (
        "<b>⚡ CONNECTION TYPES | ТЕГИ</b>\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        "Выберите типы серверов, которые вам нужны:\n\n"
        "🛡 <b>Stable (Elite):</b> Серверы с аптаймом 24ч+ без единого сбоя.\n"
        "▫️ <b>AI Ready:</b> Разблокирует ChatGPT, Gemini, Claude.\n"
        "▫️ <b>High Speed:</b> Серверы со скоростью &gt; 100 Mbps.\n"
        "▫️ <b>Reality/Vision:</b> Высокая скрытность от блокировок.\n\n"
        "<i>✅ - Включено в подписку\n⬜️ - Обычные серверы</i>"
    )
    
    await edit_or_answer(
        callback.message,
        text,
        settings_tags_kb(user_tags),
        state,
        media_url="video"
    )

@router.callback_query(F.data.startswith("toggle_tag_"))
async def toggle_tag(callback: CallbackQuery):
    tag = callback.data.split("toggle_tag_")[1]
    user_id = callback.from_user.id
    
    current_tags = await UserRepo.get_user_tags(user_id)
    
    if tag in current_tags:
        current_tags.remove(tag)
    else:
        current_tags.append(tag)
        
    await UserRepo.update_user_tags(user_id, current_tags)
    await callback.message.edit_reply_markup(reply_markup=settings_tags_kb(current_tags))

@router.callback_query(F.data == "settings_limit")
async def open_settings_limit(callback: CallbackQuery, state: FSMContext):
    user = await UserRepo.get_user(callback.from_user.id)
    limit = user.subscription_limit if user else 0
    
    text = (
        "<b>🔢 SERVER LIMIT | ЛИМИТЫ</b>\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        "Ограничьте количество серверов в подписке, если ваше приложение тормозит от большого списка.\n\n"
        f"<b>Текущий лимит:</b> {'♾️ Безлимит' if limit == 0 else str(limit)}\n\n"
        "<i>Бот автоматически подберет лучшие серверы по скорости.</i>"
    )
    
    await edit_or_answer(
        callback.message,
        text,
        settings_limit_kb(limit),
        state,
        media_url="video"
    )

@router.callback_query(F.data.startswith("set_limit_"))
async def set_limit_value(callback: CallbackQuery, state: FSMContext):
    val = callback.data.split("set_limit_")[1]
    
    if val == "custom":
        await edit_or_answer(
            callback.message,
            "<b>✍️ ВВОД ЧИСЛА</b>\n━━━━━━━━━━━━━━━━━━\n\nВведите желаемое количество серверов (числом):\n<i>0 - для снятия лимита</i>",
            back_to_home(),
            state,
            media_url="video"
        )
        await state.set_state(UserStates.waiting_for_custom_limit)
        return

    limit = int(val)
    await UserRepo.update_subscription_limit(callback.from_user.id, limit)
    await open_settings_main(callback, state)

@router.message(StateFilter(UserStates.waiting_for_custom_limit))
async def process_custom_limit_input(message: Message, state: FSMContext):
    try: await message.delete()
    except: pass

    try:
        limit = int(message.text.strip())
        if limit < 0: raise ValueError
        
        await UserRepo.update_subscription_limit(message.from_user.id, limit)
        await state.clear()
        
        await edit_or_answer(
            message, 
            f"✅ Лимит установлен: <b>{limit}</b>",
            settings_main_kb(limit, True), # Passing dummy True as user.use_fragment will update on next open
            state,
            media_url="video"
        )

    except ValueError:
        await edit_or_answer(message, "⚠️ Ошибка. Введите целое число.", back_to_home(), state, media_url="video")

@router.callback_query(F.data == "settings_countries")
async def open_settings_countries(callback: CallbackQuery, state: FSMContext):
    all_regions = await SubRepo.get_regions()
    user_filter = await UserRepo.get_user_filter(callback.from_user.id)

    text = (
        "<b>🌍 REGIONS FILTER | СТРАНЫ</b>\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        "Отметьте страны, которые вы хотите видеть в подписке.\n"
        "☑️ - Страна включена\n⬜️ - Страна скрыта\n\n"
        "<i>Изменения сохраняются автоматически.</i>"
    )

    await edit_or_answer(
        callback.message,
        text,
        settings_countries_kb(all_regions, user_filter),
        state,
        media_url="video"
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

    if not new_filter:
        new_filter = ["__EMPTY__"]
    elif set(new_filter) == set(all_regions):
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
    empty_filter = ["__EMPTY__"]
    await UserRepo.update_user_filter(callback.from_user.id, empty_filter)
    await callback.message.edit_reply_markup(reply_markup=settings_countries_kb(all_regions, empty_filter))

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from database.repo import SubRepo, UserRepo
from keyboards.user import settings_countries_kb, back_to_home, settings_main_kb, settings_limit_kb
from handlers.user.states import UserStates
from handlers.user.start import edit_or_answer
from config import config

router = Router()

@router.callback_query(F.data == "my_subscription")
async def give_subscription_link(callback: CallbackQuery):
    """Выдача ссылки-подписки с ID пользователя"""
    user_id = callback.from_user.id
    sub_url = f"http://{config.PUBLIC_IP}:{config.WEB_PORT}/sub?id={user_id}"

    user = await UserRepo.get_user(user_id)
    limit_txt = "Все доступные"
    if user and user.subscription_limit > 0:
        limit_txt = f"{user.subscription_limit} самых быстрых"

    text = (
        "📦 <b>Ваша Персональная Подписка</b>\n\n"
        f"🔗 <b>Ссылка для приложений:</b>\n<code>{sub_url}</code>\n\n"
        f"ℹ️ <b>Настройки:</b>\n"
        f"• Ключей: <b>{limit_txt}</b>\n"
        f"• Регионы: <b>Синхронизировано</b>\n\n"
        "<i>Нажмите на ссылку, чтобы скопировать.</i>"
    )

    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=back_to_home())

# --- HLAVNOE MENU NASTROEK ---
@router.callback_query(F.data == "settings_main")
async def open_settings_main(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    user = await UserRepo.get_user(callback.from_user.id)
    limit = user.subscription_limit if user else 0
    
    await callback.message.edit_text(
        "⚙️ <b>Центр настроек</b>\n\n"
        "Здесь вы можете управлять составом вашей подписки.\n"
        "Изменения применяются мгновенно, перекачивать ссылку не нужно.",
        parse_mode="HTML",
        reply_markup=settings_main_kb(limit)
    )

# --- LIMIT SETTINGS ---
@router.callback_query(F.data == "settings_limit")
async def open_settings_limit(callback: CallbackQuery):
    user = await UserRepo.get_user(callback.from_user.id)
    limit = user.subscription_limit if user else 0
    
    await callback.message.edit_text(
        "🔢 <b>Лимит количества ключей</b>\n\n"
        "Если ваше приложение тормозит из-за большого количества серверов, выберите лимит.\n"
        "Бот автоматически подберет <b>самые быстрые</b> серверы.\n\n"
        "<i>Нажмите «Свой вариант», чтобы ввести точное число.</i>",
        parse_mode="HTML",
        reply_markup=settings_limit_kb(limit)
    )

@router.callback_query(F.data.startswith("set_limit_"))
async def set_limit_value(callback: CallbackQuery, state: FSMContext):
    val = callback.data.split("set_limit_")[1]
    
    if val == "custom":
        await callback.message.edit_text(
            "✍️ <b>Введите желаемое количество ключей:</b>\n\n"
            "Пример: <code>15</code> или <code>500</code>\n"
            "<i>Отправьте 0 для безлимита.</i>",
            parse_mode="HTML",
            reply_markup=back_to_home() # Или кнопка назад к настройкам, но home тоже ок
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
        
        # Подтверждение и возврат в меню
        await edit_or_answer(
            message, 
            f"✅ <b>Лимит установлен: {limit} шт.</b>\nНастройки обновлены.",
            settings_main_kb(limit),
            state
        )

    except ValueError:
        await edit_or_answer(
            message,
            "⚠️ <b>Ошибка!</b> Введите целое положительное число (например: 25).",
            back_to_home(),
            state
        )

# --- COUNTRY SETTINGS ---
@router.callback_query(F.data == "settings_countries")
async def open_settings_countries(callback: CallbackQuery):
    """Открывает меню настройки стран"""
    all_regions = await SubRepo.get_regions()
    user_filter = await UserRepo.get_user_filter(callback.from_user.id)

    await callback.message.edit_text(
        "🌍 <b>Фильтр стран</b>\n\n"
        "Выберите страны, которые будут в подписке.\n"
        "✅ - Включено\n❌ - Выключено",
        parse_mode="HTML",
        reply_markup=settings_countries_kb(all_regions, user_filter)
    )

@router.callback_query(F.data.startswith("toggle_country_"))
async def toggle_country(callback: CallbackQuery):
    """Переключает статус одной страны"""
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

    await callback.message.edit_reply_markup(
        reply_markup=settings_countries_kb(all_regions, new_filter)
    )

@router.callback_query(F.data == "set_all_on")
async def set_all_on(callback: CallbackQuery):
    """Включить все (сбросить фильтр)"""
    all_regions = await SubRepo.get_regions()
    await UserRepo.update_user_filter(callback.from_user.id, None)
    await callback.message.edit_reply_markup(
        reply_markup=settings_countries_kb(all_regions, None)
    )

@router.callback_query(F.data == "set_all_off")
async def set_all_off(callback: CallbackQuery):
    """Выключить все"""
    all_regions = await SubRepo.get_regions()
    first = [all_regions[0]] if all_regions else None
    await UserRepo.update_user_filter(callback.from_user.id, first)

    await callback.message.edit_reply_markup(
        reply_markup=settings_countries_kb(all_regions, first)
    )
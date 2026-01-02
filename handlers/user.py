from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.exceptions import TelegramBadRequest

from database.methods import DB
from config import config
from utils.payment import payment_client
from keyboards.builders import (
    regions_kb, user_main_kb, back_to_home, 
    donate_selection_kb, crypto_amount_kb, pay_link_kb
)

router = Router()

class UserStates(StatesGroup):
    waiting_for_custom_amount = State()

# --- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ---

async def clean_start(message: Message):
    """Пытается удалить сообщение /start, чтобы не мусорить"""
    try:
        await message.delete()
    except Exception:
        pass

async def edit_or_answer(message: Message, text: str, reply_markup=None, state: FSMContext = None):
    """
    Умная отправка:
    1. Пытается отредактировать сообщение, ID которого сохранено в FSM.
    2. Если ID нет или редактирование не удалось — шлет новое и сохраняет ID.
    """
    data = await state.get_data() if state else {}
    last_msg_id = data.get("last_msg_id")
    chat_id = message.chat.id

    if last_msg_id:
        try:
            # Пытаемся отредактировать старое сообщение бота
            await message.bot.edit_message_text(
                text=text,
                chat_id=chat_id,
                message_id=last_msg_id,
                reply_markup=reply_markup,
                parse_mode="HTML"
            )
            return # Успех
        except Exception:
            # Если сообщение слишком старое или удалено, код пойдет дальше
            pass
    
    # Если не вышло отредактировать — шлем новое
    sent_msg = await message.answer(text, reply_markup=reply_markup, parse_mode="HTML")
    
    # Сохраняем ID нового сообщения
    if state:
        await state.update_data(last_msg_id=sent_msg.message_id)

# --- ХЕНДЛЕРЫ ---

@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await clean_start(message) # Удаляем команду /start пользователя
    await state.clear()
    
    await DB.add_user(message.from_user.id, message.from_user.username)
    stats = await DB.get_public_stats()
    
    text = (
        f"👋 <b>Приветствую, {message.from_user.first_name}!</b>\n\n"
        f"🚀 Я — твой надежный проводник в свободный интернет.\n"
        f"В базе собраны самые быстрые VLESS/VMESS конфигурации.\n\n"
        f"📊 <b>Статистика сервиса:</b>\n"
        f"🟢 Активных серверов: <b>{stats['active']} шт.</b>\n"
        f"🌍 Доступных стран: <b>{stats['regions']}</b>\n\n"
        f"👇 <i>Нажми кнопку ниже, чтобы получить доступ:</i>"
    )
    
    is_admin = message.from_user.id in config.ADMIN_IDS
    
    # Используем умную отправку
    await edit_or_answer(message, text, user_main_kb(is_admin), state)

# --- МЕНЮ ДОНАТА (ГЛАВНОЕ) ---
@router.callback_query(F.data == "donate_info")
async def show_donate_info(callback: CallbackQuery, state: FSMContext):
    # При переходе по кнопкам message_id актуален, сохраняем его
    await state.update_data(last_msg_id=callback.message.message_id)
    
    text = (
        "💰 <b>Поддержать разработку</b>\n\n"
        "Бот работает бесплатно. Ваша поддержка помогает оплачивать серверы!\n\n"
        "💳 <b>Т-Банк (РФ):</b>\n<code>+79121836197</code>\n\n"
        "💳 <b>Райффайзенбанк:</b>\n<code>2200300581247390</code>\n\n"
        "👇 <b>Для оплаты криптой (USDT) нажмите кнопку ниже:</b>"
    )
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=donate_selection_kb())

# --- ВЫБОР СУММЫ CRYPTO PAY ---
@router.callback_query(F.data == "crypto_selection")
async def show_crypto_amounts(callback: CallbackQuery, state: FSMContext):
    await state.update_data(last_msg_id=callback.message.message_id)
    await callback.message.edit_text(
        "💎 <b>Crypto Pay</b>\n\n"
        "Выберите сумму поддержки (USDT - TRC20/TON/BEP20):\n"
        "Бот автоматически создаст счет.",
        reply_markup=crypto_amount_kb(),
        parse_mode="HTML"
    )

# --- ВВОД СВОЕЙ СУММЫ ---
@router.callback_query(F.data == "pay_custom")
async def ask_custom_amount(callback: CallbackQuery, state: FSMContext):
    # Запоминаем ID сообщения, которое будем менять
    await state.update_data(last_msg_id=callback.message.message_id)
    
    await callback.message.edit_text(
        "✍️ <b>Введите сумму в USDT:</b>\n"
        "Просто напишите число (минимум 0.1).",
        parse_mode="HTML",
        reply_markup=back_to_home()
    )
    await state.set_state(UserStates.waiting_for_custom_amount)

@router.message(StateFilter(UserStates.waiting_for_custom_amount))
async def process_custom_amount(message: Message, state: FSMContext):
    # 1. Сразу удаляем сообщение пользователя с цифрой, чтобы не мусорить
    try:
        await message.delete()
    except TelegramBadRequest:
        pass # Если нет прав на удаление

    # 2. Валидация
    try:
        amount = float(message.text.replace(",", "."))
        if amount < 0.1:
            await edit_or_answer(message, "⚠️ <b>Ошибка:</b> Минимальная сумма 0.1 USDT.\nПопробуйте еще раз:", back_to_home(), state)
            return
    except ValueError:
        await edit_or_answer(message, "⚠️ <b>Ошибка:</b> Это не число.\nВведите корректную сумму (например 2.5):", back_to_home(), state)
        return

    # 3. Если все ок, генерируем счет, ИЗМЕНЯЯ старое сообщение бота
    await state.set_state(None) # Сбрасываем ожидание ввода
    await generate_and_edit_invoice(message, amount, state)

# --- СОЗДАНИЕ ИНВОЙСА (ФИКСИРОВАННАЯ СУММА) ---
@router.callback_query(F.data.startswith("pay_create_"))
async def create_crypto_invoice(callback: CallbackQuery, state: FSMContext):
    try:
        amount = int(callback.data.split("_")[2])
    except ValueError:
        return
    
    await state.update_data(last_msg_id=callback.message.message_id)
    await generate_and_edit_invoice(callback.message, amount, state)

# --- ЛОГИКА ГЕНЕРАЦИИ (БЕЗ СПАМА) ---
async def generate_and_edit_invoice(message: Message, amount: float, state: FSMContext):
    # Сначала ставим "Загрузку" в то же самое сообщение
    await edit_or_answer(message, f"⏳ Генерирую счет на {amount} USDT...", None, state)
    
    invoice = await payment_client.create_invoice(amount=amount, asset="USDT")
    
    if invoice:
        text = (
            f"🧾 <b>Счет на {amount} USDT создан!</b>\n\n"
            f"Нажмите кнопку ниже, чтобы перейти к оплате через CryptoBot.\n"
            f"<i>Ссылка действительна 15 минут.</i>"
        )
        await edit_or_answer(message, text, pay_link_kb(invoice.bot_invoice_url), state)
    else:
        await edit_or_answer(
            message, 
            "⚠️ Ошибка API CryptoBot. Попробуйте позже.", 
            back_to_home(), 
            state
        )

# --- РЕЖИМ ЮЗЕРА / ДОМОЙ ---
@router.callback_query(F.data == "user_mode")
@router.callback_query(F.data == "home")
async def go_home_user(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    # Обновляем ID последнего сообщения
    await state.update_data(last_msg_id=callback.message.message_id)
    
    stats = await DB.get_public_stats()
    text = (
        f"👋 <b>Главное меню</b>\n\n"
        f"📊 Статистика:\n"
        f"🟢 Активных серверов: <b>{stats['active']}</b>\n"
        f"🌍 Стран: <b>{stats['regions']}</b>"
    )
    
    is_admin = callback.from_user.id in config.ADMIN_IDS
    
    # Просто редактируем текущее сообщение
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=user_main_kb(is_admin))

# --- ВЫБОР РЕГИОНА И ВЫДАЧА ---
@router.callback_query(F.data == "get_sub_menu")
async def show_regions_user(callback: CallbackQuery, state: FSMContext):
    await state.update_data(last_msg_id=callback.message.message_id)
    
    regions = await DB.get_regions()
    if not regions:
        await callback.answer("😔 Сейчас нет активных серверов.", show_alert=True)
        return
    
    await callback.message.edit_text(
        "🌍 <b>Выберите страну:</b>",
        parse_mode="HTML",
        reply_markup=regions_kb(regions, "get_reg")
    )

@router.callback_query(F.data.startswith("get_reg_"))
async def give_best_sub(callback: CallbackQuery, state: FSMContext):
    region = callback.data.split("get_reg_")[1]
    subs = await DB.get_subs_by_region(region)
    active_subs = [s for s in subs if s.is_active]
    
    if not active_subs:
        await callback.answer("Ключи закончились.", show_alert=True)
        return
    
    best_sub = active_subs[0]
    
    await callback.message.edit_text(
        f"✅ <b>Ваш ключ доступа!</b>\n\n"
        f"🏳️ Регион: {best_sub.region}\n"
        f"⚡️ Ping: <b>{best_sub.latency_ms} ms</b>\n\n"
        f"<code>{best_sub.vless_key}</code>\n\n"
        f"👆 <i>Нажмите для копирования.</i>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Другая страна", callback_data="get_sub_menu")],
            [InlineKeyboardButton(text="🏠 Меню", callback_data="home")]
        ])
    )
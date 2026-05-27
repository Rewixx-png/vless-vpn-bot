from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, LabeledPrice, PreCheckoutQuery
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.exceptions import TelegramBadRequest

from config import config
from handlers.user.start import edit_or_answer
from handlers.user.states import UserStates
from keyboards.user import (
    donate_selection_kb,
    crypto_amount_kb,
    stars_amount_kb,
    pay_link_kb,
    back_to_home,
)
from utils.payment import payment_client

router = Router()


@router.callback_query(F.data == "donate_info")
async def show_donate_info(callback: CallbackQuery, state: FSMContext):
    if not isinstance(callback.message, Message):
        return
    text = (
        "<b>🤝 SUPPORT | ПОДДЕРЖКА</b>\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        "Бот работает на платном оборудовании, которое обеспечивает вашу анонимность и свободу.\n\n"
        "Если вам нравится сервис, вы можете поддержать его развитие любой суммой. Это помогает оплачивать мощные серверы.\n\n"
        "<b>Способы поддержки:</b>\n"
        "⭐️ <b>Telegram Stars:</b> Внутренняя валюта Telegram\n"
        "💎 <b>Криптовалюта:</b> USDT, TON, BTC (Crypto Pay)\n"
        f"💳 <b>Карты РФ:</b> <code>{config.PAYMENT_PHONE}</code> (Т-Банк/СБП)\n"
        f"💳 <b>Райффайзен:</b> <code>{config.PAYMENT_CARD_RAIFFEISEN}</code>"
    )
    await edit_or_answer(
        callback.message, text, donate_selection_kb(), state, media_url="video"
    )


@router.callback_query(F.data == "stars_selection")
async def show_stars_amounts(callback: CallbackQuery, state: FSMContext):
    if not isinstance(callback.message, Message):
        return
    text = (
        "<b>⭐️ TELEGRAM STARS DONATION</b>\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        "Выберите количество звезд для доната.\n"
        "Оплата происходит прямо в Telegram, быстро и безопасно."
    )
    await edit_or_answer(
        callback.message, text, stars_amount_kb(), state, media_url="video"
    )


@router.callback_query(F.data.startswith("stars_create_"))
async def create_stars_invoice(callback: CallbackQuery, state: FSMContext):
    if not callback.data:
        return
    if not isinstance(callback.message, Message):
        return
    try:
        amount = int(callback.data.split("_")[2])
    except ValueError:
        return

    try:
        await callback.message.delete()
    except:
        pass
        
    prices = [LabeledPrice(label=f"Донат {amount} Stars", amount=amount)]
    await callback.message.answer_invoice(
        title="Поддержка проекта VLESS VPN",
        description=f"Донат в размере {amount} Telegram Stars на развитие проекта и оплату серверов.",
        payload=f"donate_stars_{amount}",
        provider_token="",
        currency="XTR",
        prices=prices,
    )


@router.pre_checkout_query()
async def process_pre_checkout_query(pre_checkout_query: PreCheckoutQuery):
    await pre_checkout_query.answer(ok=True)


@router.message(F.successful_payment)
async def process_successful_payment(message: Message):
    if message.successful_payment is None:
        return
    amount = message.successful_payment.total_amount
    currency = message.successful_payment.currency
    
    text = (
        "<b>💖 СПАСИБО ЗА ПОДДЕРЖКУ!</b>\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        f"Ваш донат в размере <b>{amount} {currency}</b> успешно получен.\n"
        "Эти средства пойдут на оплату и улучшение серверов бота!"
    )
    await message.answer(text)


@router.callback_query(F.data == "crypto_selection")
async def show_crypto_amounts(callback: CallbackQuery, state: FSMContext):
    if not isinstance(callback.message, Message):
        return
    text = (
        "<b>💎 CRYPTO DONATION</b>\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        "Выберите сумму доната или введите свою.\n"
        "Счет выставляется автоматически через Crypto Pay."
    )
    await edit_or_answer(
        callback.message, text, crypto_amount_kb(), state, media_url="video"
    )


@router.callback_query(F.data == "pay_custom")
async def ask_custom_amount(callback: CallbackQuery, state: FSMContext):
    if not isinstance(callback.message, Message):
        return
    text = (
        "<b>✍️ CUSTOM AMOUNT</b>\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        "Введите сумму доната в <b>USDT</b> (например: 1.5):"
    )
    await edit_or_answer(
        callback.message, text, back_to_home(), state, media_url="video"
    )
    await state.set_state(UserStates.waiting_for_custom_amount)


@router.message(StateFilter(UserStates.waiting_for_custom_amount))
async def process_custom_amount(message: Message, state: FSMContext):
    if not message.text:
        return
    try:
        await message.delete()
    except:
        pass

    try:
        amount = float(message.text.replace(",", "."))
        if amount < 0.1:
            await state.clear()
            await edit_or_answer(
                message, "⚠️ Минимум 0.1 USDT.", back_to_home(), state, media_url="video"
            )
            return
    except ValueError:
        await state.clear()
        await edit_or_answer(
            message, "⚠️ Введите число.", back_to_home(), state, media_url="video"
        )
        return

    await state.set_state(None)
    await generate_and_edit_invoice(message, amount, state)


@router.callback_query(F.data.startswith("pay_create_"))
async def create_crypto_invoice(callback: CallbackQuery, state: FSMContext):
    if not callback.data:
        return
    if not isinstance(callback.message, Message):
        return
    try:
        amount = int(callback.data.split("_")[2])
    except ValueError:
        return

    await generate_and_edit_invoice(callback.message, amount, state)


async def generate_and_edit_invoice(message: Message, amount: float, state: FSMContext):
    await edit_or_answer(
        message,
        f"⏳ Создаю счет на <b>{amount} USDT</b>...",
        None,
        state,
        media_url="video",
    )

    invoice = await payment_client.create_invoice(amount=amount, asset="USDT")

    if invoice:
        text = (
            "<b>🧾 INVOICE CREATED</b>\n"
            "━━━━━━━━━━━━━━━━━━\n\n"
            f"💰 <b>Сумма:</b> {amount} USDT\n"
            f"⏳ <b>Статус:</b> Ожидает оплаты\n\n"
            "Нажмите кнопку ниже для оплаты через CryptoBot."
        )
        await edit_or_answer(
            message,
            text,
            pay_link_kb(invoice.bot_invoice_url),
            state,
            media_url="video",
        )
    else:
        await edit_or_answer(
            message,
            "⚠️ Ошибка создания счета.",
            back_to_home(),
            state,
            media_url="video",
        )

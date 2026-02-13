from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.exceptions import TelegramBadRequest

from handlers.user.start import edit_or_answer
from handlers.user.states import UserStates
from keyboards.user import donate_selection_kb, crypto_amount_kb, pay_link_kb, back_to_home
from utils.payment import payment_client

router = Router()

@router.callback_query(F.data == "donate_info")
async def show_donate_info(callback: CallbackQuery, state: FSMContext):
    text = (
        "🤝 <b>Поддержка проекта</b>\n\n"
        "Серверы оплачиваются из моего кармана. Если бот был полезен, буду рад любой сумме!\n\n"
        "💳 <b>Т-Банк / СБП (по номеру):</b>\n<code>+79121836197</code>\n\n"
        "💳 <b>Райффайзен (номер карты):</b>\n<code>2200300581247390</code>\n\n"
        "💎 <b>Криптовалюта:</b>\nНажмите кнопку ниже для оплаты USDT (TRC20/BEP20) или TON."
    )
    await edit_or_answer(callback.message, text, donate_selection_kb(), state, media_url="video")

@router.callback_query(F.data == "crypto_selection")
async def show_crypto_amounts(callback: CallbackQuery, state: FSMContext):
    await edit_or_answer(
        callback.message,
        "💎 <b>Crypto Pay Donation</b>\n\n"
        "Выберите сумму доната или введите свою.\n"
        "Система автоматически выставит счет.",
        crypto_amount_kb(),
        state,
        media_url="video"
    )

@router.callback_query(F.data == "pay_custom")
async def ask_custom_amount(callback: CallbackQuery, state: FSMContext):
    await edit_or_answer(
        callback.message,
        "✍️ <b>Введите сумму в USDT:</b>\n\n"
        "<i>Пример: 1.5</i>",
        back_to_home(),
        state,
        media_url="video"
    )
    await state.set_state(UserStates.waiting_for_custom_amount)

@router.message(StateFilter(UserStates.waiting_for_custom_amount))
async def process_custom_amount(message: Message, state: FSMContext):
    try:
        await message.delete()
    except TelegramBadRequest:
        pass 

    try:
        amount = float(message.text.replace(",", "."))
        if amount < 0.1:
            await edit_or_answer(message, "⚠️ <b>Минимум 0.1 USDT.</b> Попробуйте еще раз:", back_to_home(), state, media_url="video")
            return
    except ValueError:
        await edit_or_answer(message, "⚠️ <b>Введите число.</b> Пример: 2.5", back_to_home(), state, media_url="video")
        return

    await state.set_state(None)
    await generate_and_edit_invoice(message, amount, state)

@router.callback_query(F.data.startswith("pay_create_"))
async def create_crypto_invoice(callback: CallbackQuery, state: FSMContext):
    try:
        amount = int(callback.data.split("_")[2])
    except ValueError:
        return

    await generate_and_edit_invoice(callback.message, amount, state)

async def generate_and_edit_invoice(message: Message, amount: float, state: FSMContext):
    await edit_or_answer(message, f"⏳ <b>Создаю счет на {amount} USDT...</b>", None, state, media_url="video")

    invoice = await payment_client.create_invoice(amount=amount, asset="USDT")

    if invoice:
        text = (
            f"🧾 <b>Счет создан!</b>\n"
            f"💰 Сумма: <b>{amount} USDT</b>\n\n"
            f"Нажмите кнопку ниже для перехода к оплате.\n"
        )
        await edit_or_answer(message, text, pay_link_kb(invoice.bot_invoice_url), state, media_url="video")
    else:
        await edit_or_answer(message, "⚠️ Ошибка платежного шлюза.", back_to_home(), state, media_url="video")
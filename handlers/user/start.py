from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from config import config
from database.repo import UserRepo, StatsRepo
from keyboards.user import user_main_kb, back_to_home

router = Router()

async def clean_start(message: Message):
    try:
        await message.delete()
    except Exception:
        pass

async def edit_or_answer(message: Message, text: str, reply_markup=None, state: FSMContext = None):
    data = await state.get_data() if state else {}
    last_msg_id = data.get("last_msg_id")
    chat_id = message.chat.id

    if last_msg_id:
        try:
            await message.bot.edit_message_text(
                text=text,
                chat_id=chat_id,
                message_id=last_msg_id,
                reply_markup=reply_markup,
                parse_mode="HTML",
                disable_web_page_preview=True
            )
            return 
        except Exception:
            pass

    sent_msg = await message.answer(text, reply_markup=reply_markup, parse_mode="HTML", disable_web_page_preview=True)

    if state:
        await state.update_data(last_msg_id=sent_msg.message_id)

@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await clean_start(message)
    await state.clear()

    await UserRepo.add_user(message.from_user.id, message.from_user.username)
    stats = await StatsRepo.get_public_stats()

    text = (
        f"👋 <b>Привет, {message.from_user.first_name}!</b>\n\n"
        f"🌐 <b>VLESS VPN Bot</b> — это свободный интернет без ограничений.\n"
        f"Мы используем современные протоколы VLESS/Reality, которые невозможно заблокировать.\n\n"
        f"📊 <b>Статус сети:</b>\n"
        f"├ 🟢 Серверов онлайн: <b>{stats['active']}</b>\n"
        f"└ 🌍 Доступных стран: <b>{stats['regions']}</b>\n\n"
        f"👇 <b>Начни пользоваться прямо сейчас:</b>"
    )

    is_admin = message.from_user.id in config.ADMIN_IDS
    await edit_or_answer(message, text, user_main_kb(is_admin), state)

@router.callback_query(F.data == "user_mode")
@router.callback_query(F.data == "home")
async def go_home_user(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await state.update_data(last_msg_id=callback.message.message_id)

    stats = await StatsRepo.get_public_stats()
    text = (
        f"👋 <b>Главное меню</b>\n\n"
        f"🌐 Доступно серверов: <b>{stats['active']}</b>\n"
        f"🌍 Стран: <b>{stats['regions']}</b>"
    )

    is_admin = callback.from_user.id in config.ADMIN_IDS
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=user_main_kb(is_admin))

@router.callback_query(F.data == "user_instruction")
async def show_instruction(callback: CallbackQuery, state: FSMContext):
    await state.update_data(last_msg_id=callback.message.message_id)
    text = (
        "📚 <b>Быстрый старт</b>\n\n"
        "1️⃣ <b>Скачайте приложение</b> для вашего устройства (кнопка «📱 Приложения»).\n\n"
        "2️⃣ <b>Получите ключ</b> в этом боте (кнопка «Получить VPN»).\n\n"
        "3️⃣ <b>Скопируйте ключ</b> (он начинается на <code>vless://</code>).\n\n"
        "4️⃣ <b>Откройте приложение</b> — оно само предложит добавить ключ из буфера обмена (или нажмите кнопку «+»)."
    )
    await callback.message.edit_text(text, parse_mode="HTML", disable_web_page_preview=True, reply_markup=back_to_home())
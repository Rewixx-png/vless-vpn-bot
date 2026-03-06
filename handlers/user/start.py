from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InputMediaVideo
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.exceptions import TelegramBadRequest
from config import config
from database.repo import UserRepo, StatsRepo
from keyboards.user import user_main_kb, back_to_home
from utils.video import VideoManager

router = Router()

async def clean_start(message: Message):
    try:
        await message.delete()
    except Exception:
        pass

async def edit_or_answer(message: Message, text: str, reply_markup=None, state: FSMContext = None, media_url: str = None):
    data = await state.get_data() if state else {}
    last_msg_id = data.get("last_msg_id")
    chat_id = message.chat.id
    
    clean_text = text.replace("<blockquote>", "").replace("</blockquote>", "").strip()
    formatted_text = f"<blockquote>{clean_text}</blockquote>"

    is_long_caption = len(formatted_text) > 1000

    video_file = VideoManager.get_file()
    
    if is_long_caption:
        video_file = None

    if last_msg_id:
        try:
            if video_file:
                media = InputMediaVideo(
                    media=video_file,
                    caption=formatted_text,
                    parse_mode="HTML"
                )
                try:
                    edited_msg = await message.bot.edit_message_media(
                        chat_id=chat_id,
                        message_id=last_msg_id,
                        media=media,
                        reply_markup=reply_markup
                    )
                    if edited_msg.video and not isinstance(video_file, str):
                        VideoManager.set_file_id(edited_msg.video.file_id)
                    return
                except TelegramBadRequest as e:
                    if "message is not modified" in str(e):
                        return
                    pass
            else:
                try:
                    await message.bot.edit_message_caption(
                        chat_id=chat_id,
                        message_id=last_msg_id,
                        caption=formatted_text,
                        reply_markup=reply_markup,
                        parse_mode="HTML"
                    )
                    return
                except TelegramBadRequest:
                    await message.bot.edit_message_text(
                        chat_id=chat_id,
                        message_id=last_msg_id,
                        text=formatted_text,
                        reply_markup=reply_markup,
                        parse_mode="HTML",
                        disable_web_page_preview=True
                    )
                    return
        except Exception:
            try:
                await message.bot.delete_message(chat_id=chat_id, message_id=last_msg_id)
            except:
                pass

    if video_file:
        sent_msg = await message.answer_video(
            video=video_file,
            caption=formatted_text,
            reply_markup=reply_markup,
            parse_mode="HTML",
            supports_streaming=True
        )
        if sent_msg.video and not isinstance(video_file, str):
            VideoManager.set_file_id(sent_msg.video.file_id)
    else:
        sent_msg = await message.answer(
            formatted_text, 
            reply_markup=reply_markup, 
            parse_mode="HTML", 
            disable_web_page_preview=True
        )

    if state:
        await state.update_data(last_msg_id=sent_msg.message_id)

@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await clean_start(message)
    await state.clear()

    await UserRepo.add_user(message.from_user.id, message.from_user.username or "Anon")
    
    stats = await StatsRepo.get_public_stats()
    user_settings = await UserRepo.get_user(message.from_user.id)
    
    limit_display = "♾️ Безлимит"
    if user_settings and user_settings.subscription_limit > 0:
        limit_display = f"{user_settings.subscription_limit} шт."

    text = (
        f"<b>🚀 VLESS VPN | DASHBOARD</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"👋 Привет, <b>{message.from_user.first_name}</b>!\n\n"
        f"╔ <b>👤 ПРОФИЛЬ</b>\n"
        f"║ 🔹 <b>ID:</b> <code>{message.from_user.id}</code>\n"
        f"║ 🔹 <b>Тариф:</b> Free / {limit_display}\n"
        f"║ 🔹 <b>Статус:</b> ✅ Активен\n\n"
        f"╔ <b>🌍 СЕТЬ</b>\n"
        f"║ ⚡ <b>Онлайн:</b> {stats['active']} серверов\n"
        f"║ 🌍 <b>Стран:</b> {stats['regions']}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"<i>👇 Выберите действие:</i>"
    )

    is_admin = message.from_user.id in config.ADMIN_IDS
    await edit_or_answer(message, text, user_main_kb(is_admin), state)

@router.callback_query(F.data == "user_mode")
@router.callback_query(F.data == "home")
async def go_home_user(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    last_msg_id = data.get("last_msg_id")

    await state.clear()
    
    if last_msg_id:
        await state.update_data(last_msg_id=last_msg_id)
    
    stats = await StatsRepo.get_public_stats()
    user_settings = await UserRepo.get_user(callback.from_user.id)
    
    limit_display = "♾️ Безлимит"
    if user_settings and user_settings.subscription_limit > 0:
        limit_display = f"{user_settings.subscription_limit} шт."
    
    text = (
        f"<b>🚀 VLESS VPN | DASHBOARD</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"👋 С возвращением, <b>{callback.from_user.first_name}</b>!\n\n"
        f"╔ <b>👤 ПРОФИЛЬ</b>\n"
        f"║ 🔹 <b>ID:</b> <code>{callback.from_user.id}</code>\n"
        f"║ 🔹 <b>Лимит:</b> {limit_display}\n\n"
        f"╔ <b>🌍 СЕТЬ</b>\n"
        f"║ ⚡ <b>Серверов:</b> {stats['active']}\n"
        f"║ 🌍 <b>Локаций:</b> {stats['regions']}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"<i>👇 Выберите действие:</i>"
    )

    is_admin = callback.from_user.id in config.ADMIN_IDS
    await edit_or_answer(callback.message, text, user_main_kb(is_admin), state)

@router.callback_query(F.data == "user_instruction")
async def show_instruction(callback: CallbackQuery, state: FSMContext):
    text = (
        "<b>📚 MANUAL | ИНСТРУКЦИЯ</b>\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        "<b>1️⃣ Шаг: Установка</b>\n"
        "Перейдите в раздел <b>«📱 Приложения»</b> и скачайте клиент для вашего устройства:\n"
        "▪️ <b>iOS:</b> V2Box, Streisand\n"
        "▪️ <b>Android:</b> v2rayNG, Hiddify\n"
        "▪️ <b>PC:</b> Hiddify, NekoRay\n\n"
        "<b>2️⃣ Шаг: Подключение</b>\n"
        "1. Нажмите кнопку <b>«🚀 Подключиться»</b>.\n"
        "2. Скопируйте ссылку (нажмите на неё).\n"
        "3. Откройте приложение и выберите <b>«Import from Clipboard»</b>.\n\n"
        "<b>3️⃣ Шаг: Запуск</b>\n"
        "Выберите любой сервер из списка (например, 🇩🇪 De) и нажмите большую кнопку запуска.\n\n"
        "<i>💡 Если возникли проблемы:</i>\n"
        "✉️ <b>Связь с админом:</b> @RewiX_X"
    )
    await edit_or_answer(callback.message, text, back_to_home(), state)
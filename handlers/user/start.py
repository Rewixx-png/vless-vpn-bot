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

    video_file = VideoManager.get_file()

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
                    raise e 

            else:
                await message.bot.edit_message_caption(
                    chat_id=chat_id,
                    message_id=last_msg_id,
                    caption=formatted_text,
                    reply_markup=reply_markup,
                    parse_mode="HTML"
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

    await UserRepo.add_user(message.from_user.id, message.from_user.username)
    stats = await StatsRepo.get_public_stats()

    text = (
        f"👋 <b>Привет, {message.from_user.first_name}!</b>\n\n"
        f"🌐 <b>VLESS VPN Bot</b> — свобода без границ.\n"
        f"🚀 <b>Скорость и Анонимность</b> в один клик.\n\n"
        f"📊 <b>Статус сети:</b>\n"
        f"🟢 Серверов онлайн: <b>{stats['active']}</b>\n"
        f"🌍 Доступных стран: <b>{stats['regions']}</b>\n\n"
        f"👨‍💻 <b>Dev:</b> @RewiX_X"
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
    text = (
        f"👋 <b>Главное меню</b>\n\n"
        f"🌐 Доступно серверов: <b>{stats['active']}</b>\n"
        f"🌍 Стран: <b>{stats['regions']}</b>\n\n"
        f"👇 <i>Выберите действие ниже:</i>\n\n"
        f"👨‍💻 <b>Dev:</b> @RewiX_X"
    )

    is_admin = callback.from_user.id in config.ADMIN_IDS
    await edit_or_answer(callback.message, text, user_main_kb(is_admin), state)

@router.callback_query(F.data == "user_instruction")
async def show_instruction(callback: CallbackQuery, state: FSMContext):
    text = (
        "📚 <b>Как подключиться (Инструкция)</b>\n\n"
        "1️⃣ <b>Скачайте приложение</b>\n"
        "Нажмите кнопку «📱 Приложения» и выберите клиент (HAPP, Hiddify, V2RayTun).\n\n"
        "2️⃣ <b>Получите ссылку</b>\n"
        "Нажмите кнопку «📥 Моя подписка».\n\n"
        "3️⃣ <b>Скопируйте ссылку</b>\n"
        "Она начинается на <code>https://...</code>.\n\n"
        "4️⃣ <b>Вставьте в приложение</b>\n"
        "• Откройте приложение.\n"
        "• Найдите «Subscription Group» или «+».\n"
        "• Вставьте ссылку и нажмите <b>Update Subscription</b>.\n\n"
        "🚀 Выберите сервер и нажмите кнопку подключения!"
    )
    await edit_or_answer(callback.message, text, back_to_home(), state)
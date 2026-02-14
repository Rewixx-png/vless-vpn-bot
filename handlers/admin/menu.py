from aiogram import Router, F
from aiogram.types import CallbackQuery, InputMediaVideo
from aiogram.fsm.context import FSMContext
from aiogram.exceptions import TelegramBadRequest
from config import config
from keyboards.admin import main_admin_kb
from utils.video import VideoManager

router = Router()

@router.callback_query(F.data == "admin_home")
async def admin_dashboard(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id not in config.ADMIN_IDS:
        return
    
    # Get message and chat info
    message = callback.message
    if not message:
        return
    
    chat_id = message.chat.id
    
    # Try to get last_msg_id from state
    data = await state.get_data()
    last_msg_id = data.get("last_msg_id")
    
    text = (
        "🛠 <b>Control Panel</b>\n"
        "Управление ботом и серверами."
    )
    
    clean_text = text.replace("<blockquote>", "").replace("</blockquote>", "").strip()
    formatted_text = f"<blockquote>{clean_text}</blockquote>"
    
    video_file = VideoManager.get_file()
    
    # Try to edit existing message with media
    if last_msg_id:
        try:
            if video_file:
                media = InputMediaVideo(
                    media=video_file,
                    caption=formatted_text,
                    parse_mode="HTML"
                )
                edited = await callback.bot.edit_message_media(
                    chat_id=chat_id,
                    message_id=last_msg_id,
                    media=media,
                    reply_markup=main_admin_kb()
                )
                if hasattr(edited, 'video') and edited.video and not isinstance(video_file, str):
                    VideoManager.set_file_id(edited.video.file_id)
                await callback.answer()
                return
            else:
                await callback.bot.edit_message_caption(
                    chat_id=chat_id,
                    message_id=last_msg_id,
                    caption=formatted_text,
                    reply_markup=main_admin_kb(),
                    parse_mode="HTML"
                )
                await callback.answer()
                return
        except TelegramBadRequest as e:
            if "message is not modified" in str(e):
                await callback.answer()
                return
            # Continue to send new message
            pass
        except Exception:
            pass
    
    # Send new message with video
    try:
        if video_file:
            sent_msg = await callback.bot.send_video(
                chat_id=chat_id,
                video=video_file,
                caption=formatted_text,
                reply_markup=main_admin_kb(),
                parse_mode="HTML",
                supports_streaming=True
            )
            if hasattr(sent_msg, 'video') and sent_msg.video and not isinstance(video_file, str):
                VideoManager.set_file_id(sent_msg.video.file_id)
            # Delete old message
            try:
                await message.delete()
            except:
                pass
            # Store new message id
            await state.update_data(last_msg_id=sent_msg.message_id)
        else:
            sent_msg = await callback.bot.send_message(
                chat_id=chat_id,
                text=formatted_text,
                reply_markup=main_admin_kb(),
                parse_mode="HTML",
                disable_web_page_preview=True
            )
            # Delete old message
            try:
                await message.delete()
            except:
                pass
            # Store new message id
            await state.update_data(last_msg_id=sent_msg.message_id)
    except Exception as e:
        # Fallback: just answer
        await callback.answer(f"Error: {str(e)[:100]}", show_alert=True)
        return
    
    await callback.answer()

from aiogram import Router, F
from aiogram.types import CallbackQuery, InputMediaVideo
from aiogram.fsm.context import FSMContext
from aiogram.exceptions import TelegramBadRequest

from utils.video import VideoManager


async def safe_edit_message(message, text: str, reply_markup=None, parse_mode="HTML"):
    """Safely edit admin message; fallback to caption or new message if needed"""
    if not message:
        return
    try:
        await message.edit_text(text, reply_markup=reply_markup, parse_mode=parse_mode)
        return
    except TelegramBadRequest as e:
        err = str(e)
        if "no text in the message to edit" in err or "message is not modified" in err or "message content type" in err:
            try:
                await message.edit_caption(text, reply_markup=reply_markup, parse_mode=parse_mode)
                return
            except TelegramBadRequest:
                pass
        try:
            await message.answer(text, reply_markup=reply_markup, parse_mode=parse_mode)
        except Exception:
            pass
    except Exception:
        try:
            await message.answer(text, reply_markup=reply_markup, parse_mode=parse_mode)
        except Exception:
            pass


async def admin_edit_or_answer(callback: CallbackQuery, state: FSMContext, text: str, reply_markup=None):
    """Admin version with video support - edits or sends new message with video, deletes old"""
    message = callback.message
    if not message:
        return
    
    data = await state.get_data()
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
                edited_msg = await callback.bot.edit_message_media(
                    chat_id=chat_id,
                    message_id=last_msg_id,
                    media=media,
                    reply_markup=reply_markup
                )
                if hasattr(edited_msg, 'video') and edited_msg.video and not isinstance(video_file, str):
                    VideoManager.set_file_id(edited_msg.video.file_id)
                await callback.answer()
                return
            else:
                await callback.bot.edit_message_caption(
                    chat_id=chat_id,
                    message_id=last_msg_id,
                    caption=formatted_text,
                    reply_markup=reply_markup,
                    parse_mode="HTML"
                )
                await callback.answer()
                return
        except TelegramBadRequest as e:
            if "message is not modified" in str(e):
                await callback.answer()
                return
        except Exception:
            pass
    
    try:
        if video_file:
            sent_msg = await callback.bot.send_video(
                chat_id=chat_id,
                video=video_file,
                caption=formatted_text,
                reply_markup=reply_markup,
                parse_mode="HTML",
                supports_streaming=True
            )
            if hasattr(sent_msg, 'video') and sent_msg.video and not isinstance(video_file, str):
                VideoManager.set_file_id(sent_msg.video.file_id)
        else:
            sent_msg = await callback.bot.send_message(
                chat_id=chat_id,
                text=formatted_text,
                reply_markup=reply_markup,
                parse_mode="HTML",
                disable_web_page_preview=True
            )
        
        try:
            await message.delete()
        except:
            pass
        
        await state.update_data(last_msg_id=sent_msg.message_id)
    except Exception as e:
        pass
    
    await callback.answer()

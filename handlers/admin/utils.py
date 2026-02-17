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
    """
    Admin version with video support. 
    Prioritizes editing the current message (from callback) to avoid jumping UI.
    """
    message = callback.message
    if not message:
        return
    
    try:
        await callback.answer()
    except Exception:
        pass
    
    # Determine which message ID to edit.
    # Priority: The message the user clicked on (callback.message).
    # This fixes the issue where the bot edits an old message from history.
    target_msg_id = message.message_id
    
    chat_id = message.chat.id
    
    clean_text = text.replace("<blockquote>", "").replace("</blockquote>", "").strip()
    formatted_text = f"<blockquote>{clean_text}</blockquote>"
    
    is_long_caption = len(formatted_text) > 1000
    video_file = VideoManager.get_file()
    
    if is_long_caption:
        video_file = None

    if target_msg_id:
        try:
            if video_file:
                media = InputMediaVideo(
                    media=video_file,
                    caption=formatted_text,
                    parse_mode="HTML"
                )
                try:
                    edited_msg = await callback.bot.edit_message_media(
                        chat_id=chat_id,
                        message_id=target_msg_id,
                        media=media,
                        reply_markup=reply_markup
                    )
                    if hasattr(edited_msg, 'video') and edited_msg.video and not isinstance(video_file, str):
                        VideoManager.set_file_id(edited_msg.video.file_id)
                    
                    # Update state with this valid message ID
                    if state:
                        await state.update_data(last_msg_id=target_msg_id)
                    return
                except TelegramBadRequest as e:
                    # If we can't edit media (e.g. invalid type change), fall through to text edit logic
                    # But first, check if it's just "not modified"
                    if "message is not modified" in str(e):
                        return
                    pass

            # Try editing caption first (if message has media)
            try:
                await callback.bot.edit_message_caption(
                    chat_id=chat_id,
                    message_id=target_msg_id,
                    caption=formatted_text,
                    reply_markup=reply_markup,
                    parse_mode="HTML"
                )
                if state:
                    await state.update_data(last_msg_id=target_msg_id)
                return
            except TelegramBadRequest:
                # Fallback to edit text (if message is text only or we are replacing media with text)
                # Note: Telegram doesn't allow editing a Photo message into Text message directly via edit_message_text usually, 
                # but let's try. If it fails, we delete and send new.
                try:
                    await callback.bot.edit_message_text(
                        chat_id=chat_id,
                        message_id=target_msg_id,
                        text=formatted_text,
                        reply_markup=reply_markup,
                        parse_mode="HTML",
                        disable_web_page_preview=True
                    )
                    if state:
                        await state.update_data(last_msg_id=target_msg_id)
                    return
                except TelegramBadRequest:
                    pass
        except Exception:
            pass
    
    # If editing failed (e.g. type mismatch), delete old and send new
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
        
        # Delete the old message to keep chat clean
        try:
            await message.delete()
        except:
            pass
        
        if state:
            await state.update_data(last_msg_id=sent_msg.message_id)
            
    except Exception as e:
        pass

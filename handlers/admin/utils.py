from aiogram.types import CallbackQuery, InputMediaVideo, Message, InlineKeyboardMarkup
from aiogram.fsm.context import FSMContext
from aiogram.exceptions import TelegramBadRequest

from utils.video import VideoManager


async def safe_edit_message(message: Message | None, text: str, reply_markup: InlineKeyboardMarkup | None = None, parse_mode: str = "HTML"):
    if not isinstance(message, Message):
        return
    try:
        await message.edit_text(text, reply_markup=reply_markup, parse_mode=parse_mode)
        return
    except TelegramBadRequest as e:
        err = str(e)
        if "message is not modified" in err:
            return
            
        if "no text in the message to edit" in err or "message content type" in err or "media caption" in err:
            try:
                await message.edit_caption(caption=text, reply_markup=reply_markup, parse_mode=parse_mode)
                return
            except TelegramBadRequest:
                pass
        
        try:
            await message.delete()
        except:
            pass
        
        try:
            if isinstance(message, Message):
                await message.delete()
        except:
            pass
    except Exception:
        pass


async def admin_edit_or_answer(callback: CallbackQuery, state: FSMContext | None, text: str, reply_markup: InlineKeyboardMarkup | None = None):
    if not callback.bot:
        return
    message = callback.message
    if not isinstance(message, Message):
        return
    
    try:
        await callback.answer()
    except Exception:
        pass
    
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
                    if isinstance(edited_msg, Message) and edited_msg.video and not isinstance(video_file, str):
                        VideoManager.set_file_id(edited_msg.video.file_id)
                    
                    if state:
                        await state.update_data(last_msg_id=target_msg_id)
                    return
                except TelegramBadRequest as e:
                    if "message is not modified" in str(e):
                        return
                    pass

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
        
        if state:
            await state.update_data(last_msg_id=sent_msg.message_id)
            
    except Exception as e:
        pass

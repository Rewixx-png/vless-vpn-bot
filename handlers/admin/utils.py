from aiogram.exceptions import TelegramBadRequest


async def safe_edit_message(message, text: str, reply_markup=None, parse_mode="HTML"):
    """Safely edit admin message; fallback to caption or new message if needed"""
    if not message:
        return
    try:
        await message.edit_text(text, reply_markup=reply_markup, parse_mode=parse_mode)
        return
    except TelegramBadRequest as e:
        err = str(e)
        # Try edit caption if original message is media
        if "no text in the message to edit" in err or "message is not modified" in err or "message content type" in err:
            try:
                await message.edit_caption(text, reply_markup=reply_markup, parse_mode=parse_mode)
                return
            except TelegramBadRequest:
                pass
        # Fallback: send new message
        try:
            await message.answer(text, reply_markup=reply_markup, parse_mode=parse_mode)
        except Exception:
            pass
    except Exception:
        try:
            await message.answer(text, reply_markup=reply_markup, parse_mode=parse_mode)
        except Exception:
            pass

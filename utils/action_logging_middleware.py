import asyncio
import html

from aiogram import BaseMiddleware, Bot
from aiogram.types import CallbackQuery, Message, TelegramObject

from config import config
from utils.reporter import Reporter, trim_str


class ActionLoggingMiddleware(BaseMiddleware):
    def __init__(self, bot: Bot):
        super().__init__()
        self.bot = bot



    async def _log_event(self, event: TelegramObject, ok: bool, error: Exception | None) -> None:
        if isinstance(event, Message):
            user = event.from_user
            if not user or user.is_bot:
                return

            text = event.text or event.caption or "<non-text message>"
            action_type = "command" if text.startswith("/") else "message"

            payload = (
                f"status={'OK' if ok else 'ERROR'}\n"
                f"type={action_type}\n"
                f"user_id={user.id}\n"
                f"username=@{user.username or '-'}\n"
                f"chat_id={event.chat.id}\n"
                f"chat_type={event.chat.type}\n"
                f"text=<code>{html.escape(trim_str(text, 700), quote=False)}</code>"
            )
        elif isinstance(event, CallbackQuery):
            user = event.from_user
            if not user or user.is_bot:
                return

            callback_data = event.data or "<empty>"
            chat_id = event.message.chat.id if event.message else "-"
            payload = (
                f"status={'OK' if ok else 'ERROR'}\n"
                f"type=callback\n"
                f"user_id={user.id}\n"
                f"username=@{user.username or '-'}\n"
                f"chat_id={chat_id}\n"
                f"callback=<code>{html.escape(trim_str(callback_data, 700), quote=False)}</code>"
            )
        else:
            return

        if error is not None:
            payload += f"\nerror=<code>{html.escape(trim_str(str(error), 700), quote=False)}</code>"

        if user.id in config.ADMIN_IDS:
            await Reporter.send_admin_action(self.bot, payload)
        else:
            await Reporter.send_user_action(self.bot, payload)

    async def __call__(self, handler, event: TelegramObject, data: dict):
        caught_error: Exception | None = None

        try:
            return await handler(event, data)
        except Exception as error:
            caught_error = error
            raise
        finally:
            try:
                asyncio.create_task(self._log_event(event, caught_error is None, caught_error))
            except Exception:
                pass

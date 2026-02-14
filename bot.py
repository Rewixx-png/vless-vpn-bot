import asyncio
import logging
import sys
from typing import Iterable
from aiogram import Bot, Dispatcher

# 1. Сразу настраиваем базовое логирование на WARNING
logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    force=True 
)

from config import config
from database.core import init_db
from handlers.admin.router import admin_router
from handlers.user.router import user_router
from utils.payment import payment_client
from utils.background import BackgroundTasks
from utils.sub_server import SubscriptionServer
from utils.video import VideoManager

# 2. Жестко глушим "болтливые" логгеры
loggers_to_silence = [
    "aiogram", 
    "aiogram.event", 
    "aiogram.dispatcher", 
    "VideoManager", 
    "Scheduler", 
    "aiohttp",
    "asyncio"
]

for logger_name in loggers_to_silence:
    logging.getLogger(logger_name).setLevel(logging.WARNING)

logger = logging.getLogger(__name__)

class TelegramLogHandler(logging.Handler):
    def __init__(self, bot: Bot, admin_ids: Iterable[int]):
        super().__init__(level=logging.ERROR)
        self.bot = bot
        self.admin_ids = list(admin_ids)

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = self.format(record)
            if len(msg) > 3500:
                msg = msg[:3500] + "..."

            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                return
            for admin_id in self.admin_ids:
                loop.create_task(self.bot.send_message(admin_id, f"❗️ Ошибка:\n{msg}"))
        except Exception:
            pass

async def main():
    await init_db()

    # Подготовка видео (без логов)
    await VideoManager.prepare()

    bot = Bot(token=config.BOT_TOKEN.get_secret_value())
    dp = Dispatcher()

    # Отправка всех ошибок в ЛС владельцу
    tg_handler = TelegramLogHandler(bot, config.ADMIN_IDS)
    tg_handler.setFormatter(logging.Formatter("%(name)s - %(levelname)s - %(message)s"))
    logging.getLogger().addHandler(tg_handler)

    dp.include_router(user_router)
    dp.include_router(admin_router)

    await BackgroundTasks.start_scheduler()
    
    server_task = asyncio.create_task(SubscriptionServer.start())

    await bot.delete_webhook(drop_pending_updates=True)
    
    try:
        await dp.start_polling(bot)
    except Exception as e:
        logger.error(f"Error occurred: {e}")
    finally:
        await BackgroundTasks.stop()
        
        server_task.cancel()
        try:
            await server_task
        except asyncio.CancelledError:
            pass

        await bot.session.close()
        await payment_client.close()

if __name__ == "__main__":
    try:
        if sys.platform == 'win32':
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
            
        asyncio.run(main())
    except KeyboardInterrupt:
        pass

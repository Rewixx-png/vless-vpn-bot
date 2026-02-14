import asyncio
import logging
import sys
from aiogram import Bot, Dispatcher
from config import config
from database.core import init_db
from handlers.admin.router import admin_router
from handlers.user.router import user_router
from utils.payment import payment_client
from utils.background import BackgroundTasks
from utils.sub_server import SubscriptionServer
from utils.video import VideoManager

# Устанавливаем уровень WARNING, чтобы скрыть INFO логи от aiogram и прочих модулей
logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Дополнительно глушим aiogram, если вдруг он переопределит конфиг
logging.getLogger("aiogram").setLevel(logging.WARNING)
logging.getLogger("aiogram.event").setLevel(logging.WARNING)

async def main():
    await init_db()

    # Подготовка видео (скачивание + ffmpeg)
    await VideoManager.prepare()

    bot = Bot(token=config.BOT_TOKEN.get_secret_value())
    dp = Dispatcher()

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
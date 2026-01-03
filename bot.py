import asyncio
import logging
from aiogram import Bot, Dispatcher
from config import config
from database.core import init_db
from handlers.admin.router import admin_router
from handlers.user.router import user_router
from utils.payment import payment_client
from utils.background import BackgroundTasks
from utils.sub_server import SubscriptionServer

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

async def main():
    logger.info("Starting bot initialization...")

    # Инициализация БД
    await init_db()
    logger.info("Database initialized.")

    # Инициализация бота и диспетчера
    bot = Bot(token=config.BOT_TOKEN.get_secret_value())
    dp = Dispatcher()

    # Регистрация агрегированных роутеров
    dp.include_router(user_router)
    dp.include_router(admin_router)

    # Запуск фоновых задач (Планировщик)
    asyncio.create_task(BackgroundTasks.start_scheduler())
    
    # Запуск сервера подписки (HTTP)
    asyncio.create_task(SubscriptionServer.start())

    # Удаление вебхука и запуск пуллинга
    await bot.delete_webhook(drop_pending_updates=True)
    logger.info("Bot started polling.")

    try:
        await dp.start_polling(bot)
    except Exception as e:
        logger.error(f"Error occurred: {e}")
    finally:
        await bot.session.close()
        await payment_client.close()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user.")
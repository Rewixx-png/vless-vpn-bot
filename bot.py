import asyncio
import logging
from aiogram import Bot, Dispatcher
from config import config
from database.core import init_db
from handlers import admin, user
from utils.payment import payment_client

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def main():
    logger.info("Starting bot initialization...")
    
    # Инициализация БД
    await init_db()
    logger.info("Database initialized.")

    # Инициализация бота и диспетчера
    bot = Bot(token=config.BOT_TOKEN.get_secret_value())
    dp = Dispatcher()

    # Регистрация роутеров
    dp.include_router(user.router)
    dp.include_router(admin.router)

    # Удаление вебхука и запуск пуллинга
    await bot.delete_webhook(drop_pending_updates=True)
    logger.info("Bot started polling.")
    
    try:
        await dp.start_polling(bot)
    except Exception as e:
        logger.error(f"Error occurred: {e}")
    finally:
        await bot.session.close()
        await payment_client.close() # Закрываем соединение с CryptoBot

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user.")
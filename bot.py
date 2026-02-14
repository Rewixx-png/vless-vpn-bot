"""
Main bot entry point with optimized startup and error handling.
"""
import asyncio
import logging
import sys
import time
from typing import Iterable
from aiogram import Bot, Dispatcher

# Configure logging early
logging.basicConfig(
    level=logging.INFO,
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
from utils.checker.api import CheckerAPI

# Silence noisy loggers
loggers_to_silence = [
    "aiogram", 
    "aiogram.event", 
    "aiogram.dispatcher", 
    "VideoManager", 
    "Scheduler", 
    "aiohttp.access",
    "asyncio"
]

for logger_name in loggers_to_silence:
    logging.getLogger(logger_name).setLevel(logging.WARNING)

logger = logging.getLogger(__name__)


class TelegramLogHandler(logging.Handler):
    """Send critical errors to admins via Telegram"""
    
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
                try:
                    loop.create_task(
                        self.bot.send_message(admin_id, f"❗️ <b>Ошибка:</b>\n<pre>{msg}</pre>", parse_mode="HTML")
                    )
                except Exception:
                    pass
        except Exception:
            pass


async def notify_admins(bot: Bot, message: str):
    """Send notification to all admins"""
    for admin_id in config.ADMIN_IDS:
        try:
            await bot.send_message(admin_id, message, parse_mode="HTML")
        except Exception as e:
            logger.warning(f"Failed to notify admin {admin_id}: {e}")


async def check_services() -> dict:
    """Check if required services are running"""
    results = {
        "checker": False,
        "database": False,
        "video": False
    }
    
    # Check database
    try:
        from database.repo import StatsRepo
        await StatsRepo.get_public_stats()
        results["database"] = True
    except Exception as e:
        logger.error(f"Database check failed: {e}")
    
    # Check checker service
    try:
        test_result = await CheckerAPI.check("vless://test@localhost:443?security=none")
        # Service is online if we get any response (even failure for test link)
        results["checker"] = test_result[4] != "Checker Service Offline"
    except Exception:
        results["checker"] = False
    
    # Check video
    results["video"] = VideoManager.is_ready()
    
    return results


async def main():
    start_time = time.time()
    
    logger.info("🚀 Starting VLESS VPN Bot...")
    
    # Initialize database
    logger.info("📦 Initializing database...")
    await init_db()
    
    # Start video preparation in background (non-blocking)
    logger.info("🎬 Starting video preparation...")
    await VideoManager.prepare()
    
    # Create bot and dispatcher
    bot = Bot(token=config.BOT_TOKEN.get_secret_value())
    dp = Dispatcher()
    
    # Setup error logging to Telegram
    tg_handler = TelegramLogHandler(bot, config.ADMIN_IDS)
    tg_handler.setFormatter(logging.Formatter("%(name)s: %(message)s"))
    logging.getLogger().addHandler(tg_handler)
    
    # Include routers
    dp.include_router(user_router)
    dp.include_router(admin_router)
    
    # Start background scheduler
    logger.info("⏰ Starting background scheduler...")
    await BackgroundTasks.start_scheduler()
    
    # Start subscription server
    logger.info("🌐 Starting subscription server...")
    server_task = asyncio.create_task(SubscriptionServer.start())
    
    # Wait a bit for services to initialize
    await asyncio.sleep(2)
    
    # Check services
    logger.info("🔍 Checking services...")
    service_status = await check_services()
    
    # Calculate startup time
    startup_duration = time.time() - start_time
    
    # Build startup message
    status_emoji = lambda x: "✅" if x else "❌"
    startup_msg = (
        f"🚀 <b>Бот запущен!</b>\n\n"
        f"⏱️ Время запуска: <code>{startup_duration:.1f}s</code>\n\n"
        f"📊 Статус сервисов:\n"
        f"{status_emoji(service_status['database'])} База данных\n"
        f"{status_emoji(service_status['checker'])} Checker Service\n"
        f"{status_emoji(service_status['video'])} Видео UI\n\n"
    )
    
    if not service_status["checker"]:
        startup_msg += (
            f"⚠️ <b>Внимание!</b>\n"
            f"Checker Service не запущен.\n"
            f"Запустите: <code>python utils/checker/service.py</code>"
        )
    
    # Notify admins
    await notify_admins(bot, startup_msg)
    logger.info(f"✅ Bot started in {startup_duration:.1f}s")
    
    # Clear webhook and start polling
    await bot.delete_webhook(drop_pending_updates=True)
    
    try:
        await dp.start_polling(bot)
    except Exception as e:
        logger.error(f"❌ Polling error: {e}")
        await notify_admins(bot, f"❌ <b>Критическая ошибка:</b>\n<pre>{str(e)[:1000]}</pre>")
    finally:
        logger.info("🛑 Shutting down...")
        
        # Stop background tasks
        await BackgroundTasks.stop()
        
        # Stop server
        server_task.cancel()
        try:
            await server_task
        except asyncio.CancelledError:
            pass
        
        # Close connections
        await bot.session.close()
        await payment_client.close()
        
        logger.info("👋 Bot stopped")


if __name__ == "__main__":
    try:
        if sys.platform == 'win32':
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("👋 Interrupted by user")
    except Exception as e:
        logger.error(f"❌ Fatal error: {e}", exc_info=True)
        sys.exit(1)

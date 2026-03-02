import asyncio
import logging
import sys
import time
import os
import traceback
import subprocess
import signal
import re
import gc
import html
import psutil
from datetime import datetime, timedelta
from typing import Iterable
from aiogram import Bot, Dispatcher

# Memory limit in MB before triggering GC and potential restart
MEMORY_LIMIT_MB = 450
MEMORY_CHECK_INTERVAL = 60  # Check every 60 seconds

async def memory_monitor():
    """Monitor memory usage and trigger GC if needed"""
    process = psutil.Process(os.getpid())
    while True:
        try:
            await asyncio.sleep(MEMORY_CHECK_INTERVAL)
            memory_mb = process.memory_info().rss / 1024 / 1024
            
            if memory_mb > MEMORY_LIMIT_MB:
                logger.warning(f"⚠️ High memory usage: {memory_mb:.0f}MB. Triggering GC...")
                gc.collect()
                
                # Check again after GC
                memory_mb = process.memory_info().rss / 1024 / 1024
                logger.info(f"📊 Memory after GC: {memory_mb:.0f}MB")
                
                if memory_mb > MEMORY_LIMIT_MB + 50:
                    logger.error(f"🚨 Memory still high after GC ({memory_mb:.0f}MB). Consider restarting.")
        except Exception as e:
            logger.error(f"Memory monitor error: {e}")

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

loggers_to_silence =[
    "aiogram", 
    "aiogram.event", 
    "aiogram.dispatcher", 
    "VideoManager", 
    "Scheduler", 
    "aiohttp.access",
    "aiohttp.server",
    "asyncio"
]

for logger_name in loggers_to_silence:
    logging.getLogger(logger_name).setLevel(logging.WARNING)

logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CRASH_FILE = os.path.join(BASE_DIR, "crash_log.txt")
OOM_HISTORY = os.path.join(BASE_DIR, ".oom_history")

class TelegramLogHandler(logging.Handler):
    def __init__(self, bot: Bot, admin_ids: Iterable[int]):
        super().__init__(level=logging.ERROR)
        self.bot = bot
        self.admin_ids = list(admin_ids)

    def emit(self, record: logging.LogRecord) -> None:
        # Skip common non-critical loggers
        if record.name in ["aiohttp.server", "aiogram.dispatcher", "aiogram.event"]:
            return
        if "BadStatusLine" in str(record.msg) or "BadHttpMessage" in str(record.msg):
            return
        
        # Skip Telegram API errors (too spammy)
        msg_str = str(record.msg)
        if any(err in msg_str for err in [
            "TelegramForbiddenError", 
            "TelegramRetryAfter", 
            "user is deactivated",
            "Flood control exceeded",
            "Too Many Requests"
        ]):
            return

        try:
            msg = self.format(record)
            if len(msg) > 3500:
                msg = msg[:3500] + "..."

            # Escape HTML entities in message to prevent parsing errors
            safe_msg = html.escape(msg)

            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                return

            for admin_id in self.admin_ids:
                try:
                    loop.create_task(
                        self.bot.send_message(admin_id, f"❗️ <b>Ошибка:</b>\n<pre>{safe_msg}</pre>", parse_mode="HTML")
                    )
                except Exception:
                    pass
        except Exception:
            pass

async def notify_admins(bot: Bot, message: str):
    for admin_id in config.ADMIN_IDS:
        try:
            await bot.send_message(admin_id, message, parse_mode="HTML")
        except Exception as e:
            logger.warning(f"Failed to notify admin {admin_id}: {e}")

async def check_services() -> dict:
    results = {
        "checker": False,
        "database": False,
        "video": False,
        "db_error": None
    }
    
    try:
        from database.repo import StatsRepo
        await StatsRepo.get_public_stats()
        results["database"] = True
    except Exception as e:
        logger.error(f"Database check failed: {e}")
        results["db_error"] = str(e)
    
    try:
        test_result = await CheckerAPI.check("vless://test@localhost:443?security=none")
        err_msg = str(test_result[5])
        results["checker"] = "Offline" not in err_msg and "SYS_ERR" not in err_msg
    except Exception:
        results["checker"] = False
    
    results["video"] = VideoManager.is_ready()
    
    return results

async def report_crash(bot: Bot) -> bool:
    crash_reported = False
    
    if os.path.exists(CRASH_FILE):
        try:
            with open(CRASH_FILE, "r", encoding="utf-8") as f:
                crash_reason = f.read()
            
            os.remove(CRASH_FILE)
            
            if crash_reason.strip():
                await notify_admins(bot, f"☠️ <b>Бот был перезагружен!</b>\n\n<pre>{crash_reason[:3500]}</pre>")
                crash_reported = True
        except Exception:
            pass

    try:
        cmd = "LC_ALL=C dmesg -T | grep -i -E 'killed process.*(python|node|xray|celery)' | tail -n 20"
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        if result.stdout.strip():
            new_ooms =[]
            history = ""
            if os.path.exists(OOM_HISTORY):
                with open(OOM_HISTORY, "r", encoding="utf-8") as hf:
                    history = hf.read()
            
            lines = result.stdout.strip().split('\n')
            for line in lines:
                if line not in history:
                    new_ooms.append(line)
            
            if new_ooms:
                with open(OOM_HISTORY, "a", encoding="utf-8") as hf:
                    for oom in new_ooms:
                        hf.write(oom + "\n")
                
                oom_text = "\n".join(new_ooms)
                await notify_admins(bot, f"🔪 <b>Процесс убит системой (OOM Killer)!</b>\nВозможно, серверу не хватило памяти.\n\n<pre>{oom_text[:3500]}</pre>")
                crash_reported = True
    except Exception:
        pass
            
    return crash_reported

def handle_sigterm(signum, frame):
    try:
        with open(CRASH_FILE, "w", encoding="utf-8") as f:
            f.write(f"🛑 ВНЕШНИЙ СИГНАЛ (SIGTERM/SIGINT: {signum}):\nБот принудительно остановлен менеджером процессов (PM2 / Systemd).\nВероятная причина: PM2 перезапустил процесс из-за достижения лимита оперативной памяти (--max-memory-restart) или была выполнена команда 'pm2 restart'.")
    except Exception:
        pass
    os._exit(1)

def global_exception_handler(exctype, value, tb):
    if issubclass(exctype, KeyboardInterrupt):
        sys.__excepthook__(exctype, value, tb)
        return
    
    crash_msg = "".join(traceback.format_exception(exctype, value, tb))
    try:
        with open(CRASH_FILE, "w", encoding="utf-8") as f:
            f.write(f"FATAL UNHANDLED EXCEPTION:\n{crash_msg}")
    except Exception:
        pass
    
    sys.__excepthook__(exctype, value, tb)

async def main():
    start_time = time.time()
    
    logger.info("🚀 Starting VLESS VPN Bot...")
    
    logger.info("📦 Initializing database...")
    try:
        await init_db()
    except Exception as e:
        logger.critical(f"🔥 DATABASE INIT FAILED: {e}")
    
    logger.info("🎬 Starting video preparation...")
    await VideoManager.prepare()
    
    bot = Bot(token=config.BOT_TOKEN.get_secret_value())
    dp = Dispatcher()
    
    crashed = await report_crash(bot)
    
    tg_handler = TelegramLogHandler(bot, config.ADMIN_IDS)
    tg_handler.setFormatter(logging.Formatter("%(name)s: %(message)s"))
    logging.getLogger().addHandler(tg_handler)
    
    dp.include_router(user_router)
    dp.include_router(admin_router)
    
    logger.info("⏰ Starting background scheduler...")
    await BackgroundTasks.start_scheduler()
    
    # Start memory monitor
    logger.info("🧠 Starting memory monitor...")
    memory_task = asyncio.create_task(memory_monitor())
    
    logger.info("🌐 Starting subscription server...")
    server_task = asyncio.create_task(SubscriptionServer.start())
    
    await asyncio.sleep(2)
    
    logger.info("🔍 Checking services...")
    service_status = await check_services()
    
    startup_duration = time.time() - start_time
    
    status_emoji = lambda x: "✅" if x else "❌"
    startup_msg = (
        f"🚀 <b>Бот запущен!</b>\n\n"
        f"⏱️ Время запуска: <code>{startup_duration:.1f}s</code>\n\n"
        f"📊 Статус сервисов:\n"
        f"{status_emoji(service_status['database'])} База данных\n"
        f"{status_emoji(service_status['checker'])} Checker Service\n"
        f"{status_emoji(service_status['video'])} Видео UI\n"
    )
    
    if not crashed:
        startup_msg += "\nℹ️ <i>Обычный запуск (без обнаружения критических сбоев). Если рестарт был внезапным — возможно, процесс убит жестким сигналом SIGKILL (-9).</i>"
    
    if not service_status["checker"]:
        startup_msg += (
            f"\n\n⚠️ <b>Внимание!</b>\n"
            f"Checker Service не запущен или недоступен.\n"
            f"Запустите: <code>python utils/checker/service.py</code>"
        )
        
    if not service_status["database"]:
        startup_msg += (
            f"\n\n🛑 <b>Ошибка БД:</b>\n"
            f"<pre>{service_status.get('db_error', 'Unknown Error')}</pre>"
        )
    
    await notify_admins(bot, startup_msg)
    logger.info(f"✅ Bot started in {startup_duration:.1f}s")
    
    await bot.delete_webhook(drop_pending_updates=True)
    
    try:
        await dp.start_polling(bot, handle_signals=False)
    except Exception as e:
        logger.error(f"❌ Polling error: {e}")
        await notify_admins(bot, f"❌ <b>Критическая ошибка (Polling):</b>\n<pre>{str(e)[:1000]}</pre>")
    finally:
        logger.info("🛑 Shutting down...")
        
        # Stop memory monitor
        memory_task.cancel()
        try:
            await memory_task
        except asyncio.CancelledError:
            pass

        await BackgroundTasks.stop()
        server_task.cancel()
        try:
            await server_task
        except asyncio.CancelledError:
            pass

        await bot.session.close()
        await payment_client.close()
        
        # Force garbage collection on shutdown
        gc.collect()

        logger.info("👋 Bot stopped")

def set_process_affinity():
    """Set CPU affinity to use all available cores"""
    try:
        import os
        process = psutil.Process()
        cpu_count = os.cpu_count()
        if cpu_count:
            # Use all CPUs
            process.cpu_affinity(list(range(cpu_count)))
            logger.info(f"✅ CPU affinity set to use all {cpu_count} cores")
    except Exception as e:
        logger.warning(f"⚠️ Could not set CPU affinity: {e}")

if __name__ == "__main__":
    # Set CPU affinity for better multi-core utilization
    set_process_affinity()
    
    sys.excepthook = global_exception_handler

    if sys.platform != 'win32':
        signal.signal(signal.SIGTERM, handle_sigterm)
        signal.signal(signal.SIGINT, handle_sigterm)

    restart_count = 0
    max_restarts = 10
    
    while restart_count < max_restarts:
        try:
            if sys.platform == 'win32':
                asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
            
            asyncio.run(main())
            break
            
        except KeyboardInterrupt:
            logger.info("👋 Interrupted by user")
            break
            
        except Exception as e:
            try:
                with open(CRASH_FILE, "w", encoding="utf-8") as f:
                    f.write(f"MAIN LOOP CRASH:\n{type(e).__name__}: {str(e)}\n{traceback.format_exc()}")
            except Exception:
                pass
                
            restart_count += 1
            logger.error(f"❌ Fatal error (restart {restart_count}/{max_restarts}): {e}", exc_info=True)
            time.sleep(5)

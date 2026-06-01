import asyncio
import logging
from datetime import datetime, time, timedelta
from utils.state import BotState
from config import config

logger = logging.getLogger("Scheduler")


class BackgroundTasks:
    _tasks = []
    _is_running = False

    @classmethod
    async def start_scheduler(cls):
        if cls._is_running:
            return

        cls._is_running = True
        logger.warning("🚀 Starting background scheduler...")

        cls._tasks = [
            asyncio.create_task(
                cls._daily_digest_scheduler(), name="daily_digest_scheduler"
            ),
        ]

    @classmethod
    async def stop(cls):
        logger.warning("🛑 Stopping background scheduler...")
        cls._is_running = False

        for task in cls._tasks:
            if not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

        cls._tasks.clear()

    @classmethod
    async def _daily_digest_scheduler(cls):
        from utils.smart_alerts import SmartAlerts

        await asyncio.sleep(60)

        while cls._is_running:
            try:
                now = datetime.now()
                target_time = time(9, 0)

                if now.time() >= target_time:
                    next_run = datetime.combine(now.date(), target_time) + timedelta(
                        days=1
                    )
                else:
                    next_run = datetime.combine(now.date(), target_time)

                wait_seconds = (next_run - now).total_seconds()
                logger.info(
                    f"⏰ Daily digest scheduled for {next_run.strftime('%Y-%m-%d %H:%M:%S')} UTC (12:00 MSK), waiting {wait_seconds / 3600:.1f} hours"
                )

                await asyncio.sleep(wait_seconds)

                if cls._is_running:
                    logger.info("📬 Sending daily digest...")
                    await SmartAlerts.send_daily_digest()

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"❌ Daily Digest Scheduler Error: {e}")
                await asyncio.sleep(3600)

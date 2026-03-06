import asyncio
import logging
from datetime import datetime, time, timedelta
from utils.state import BotState
from config import config

logger = logging.getLogger("Scheduler")

class BackgroundTasks:
    _tasks = []
    _is_running = False

    COLLECT_INTERVAL = config.COLLECTOR_INTERVAL
    STABILITY_INTERVAL = config.STABILITY_CHECK_INTERVAL
    GEOIP_UPDATE_INTERVAL = config.DNS_CACHE_TTL  # 30 days

    @classmethod
    async def start_scheduler(cls):
        if cls._is_running:
            return

        cls._is_running = True
        logger.warning("🚀 Starting background scheduler...")

        cls._tasks = [
            asyncio.create_task(cls._collector_scheduler(), name="collector_scheduler"),
            asyncio.create_task(cls._stability_scheduler(), name="stability_scheduler"),
            asyncio.create_task(cls._geoip_scheduler(), name="geoip_scheduler"),
            asyncio.create_task(cls._daily_digest_scheduler(), name="daily_digest_scheduler"),
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
    async def _collector_scheduler(cls):
        while cls._is_running:
            try:
                from tasks import run_collector_task
                is_maint = await BotState.is_maintenance()
                if is_maint:
                    logger.warning("⏸️ Collector skipped due to Maintenance Mode")
                else:
                    logger.warning("☀️ Running collection...")
                    run_collector_task.delay()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"❌ Collector Scheduler Error: {e}")

            await asyncio.sleep(cls.COLLECT_INTERVAL)

    @classmethod
    async def _stability_scheduler(cls):
        await asyncio.sleep(30)

        while cls._is_running:
            try:
                from tasks import check_stability_task
                is_maint = await BotState.is_maintenance()
                if is_maint:
                    logger.warning("⏸️ Stability Check skipped due to Maintenance Mode")
                else:
                    logger.warning("🛡 Running stability check...")
                    check_stability_task.delay()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"❌ Stability Scheduler Error: {e}")

            await asyncio.sleep(cls.STABILITY_INTERVAL)

    @classmethod
    async def _geoip_scheduler(cls):
        while cls._is_running:
            try:
                from tasks import update_geoip_task
                update_geoip_task.delay()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"❌ GeoIP Scheduler Error: {e}")

            await asyncio.sleep(cls.GEOIP_UPDATE_INTERVAL)

    @classmethod
    async def _daily_digest_scheduler(cls):
        from utils.smart_alerts import SmartAlerts

        await asyncio.sleep(60)

        while cls._is_running:
            try:
                now = datetime.now()
                target_time = time(9, 0)

                if now.time() >= target_time:
                    next_run = datetime.combine(now.date(), target_time) + timedelta(days=1)
                else:
                    next_run = datetime.combine(now.date(), target_time)

                wait_seconds = (next_run - now).total_seconds()
                logger.info(f"⏰ Daily digest scheduled for {next_run.strftime('%Y-%m-%d %H:%M:%S')} UTC (12:00 MSK), waiting {wait_seconds/3600:.1f} hours")

                await asyncio.sleep(wait_seconds)

                if cls._is_running:
                    logger.info("📬 Sending daily digest...")
                    await SmartAlerts.send_daily_digest()

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"❌ Daily Digest Scheduler Error: {e}")
                await asyncio.sleep(3600)

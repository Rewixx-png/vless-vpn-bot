import asyncio
import logging
from utils.state import BotState

logger = logging.getLogger("Scheduler")

class BackgroundTasks:
    _tasks = []
    _is_running = False
    
    COLLECT_INTERVAL = 1800       # 30 минут для сбора новых прокси (было 10)
    STABILITY_INTERVAL = 1800     # 30 минут для проверки стабильности (было 10)
    GEOIP_UPDATE_INTERVAL = 30 * 24 * 3600 # 30 дней
    
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
                if BotState.is_maintenance():
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
        # Ждем 30 секунд перед первым запуском, чтобы система успела загрузиться
        await asyncio.sleep(30)
        
        while cls._is_running:
            try:
                from tasks import check_stability_task
                if BotState.is_maintenance():
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

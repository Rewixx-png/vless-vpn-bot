import asyncio
import logging
from tasks import run_collector_task
from utils.state import BotState

logger = logging.getLogger("Scheduler")


class BackgroundTasks:
    _tasks = []
    _is_running = False
    
    COLLECT_INTERVAL = 600
    
    @classmethod
    async def start_scheduler(cls):
        if cls._is_running:
            return
        
        cls._is_running = True
        logger.warning("🚀 Starting background scheduler...")
        
        cls._tasks = [
            asyncio.create_task(cls._collector_scheduler(), name="collector_scheduler"),
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

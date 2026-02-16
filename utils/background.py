"""
Background scheduler - only collector 24/7.
"""
import asyncio
import logging
from tasks import run_collector_task

logger = logging.getLogger("Scheduler")


class BackgroundTasks:
    """Background task scheduler - collector only"""
    
    _tasks = []
    _is_running = False
    
    COLLECT_INTERVAL = 600  # 10 minutes
    
    @classmethod
    async def start_scheduler(cls):
        """Start background scheduler"""
        if cls._is_running:
            return
        
        cls._is_running = True
        logger.warning("🚀 Starting background scheduler...")
        
        cls._tasks = [
            asyncio.create_task(cls._collector_scheduler(), name="collector_scheduler"),
        ]
    
    @classmethod
    async def stop(cls):
        """Stop background tasks"""
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
        """Schedule subscription collection - 24/7"""
        while cls._is_running:
            try:
                logger.warning("☀️ Running collection...")
                run_collector_task.delay()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"❌ Collector Scheduler Error: {e}")
            
            await asyncio.sleep(cls.COLLECT_INTERVAL)

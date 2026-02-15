"""
Optimized background scheduler with proper async support.
Time-based scheduling: collection during day, checking at night.
"""
import asyncio
import logging
from datetime import datetime
from database.repo import SubRepo
from tasks import check_subs_batch_task, run_collector_task, cleanup_database_task

logger = logging.getLogger("Scheduler")


class BackgroundTasks:
    """Optimized background task scheduler"""
    
    _tasks = []
    _is_running = False
    
    # Intervals
    CHECK_INTERVAL = 900      # 15 minutes (night - less CPU)
    COLLECT_INTERVAL = 900  # 15 minutes (day)
    CLEANUP_INTERVAL = 3600 # 1 hour
    
    # Time ranges (Moscow timezone UTC+3)
    # Collection: 6:00 - 19:59 (day)
    # Checking: 20:00 - 5:59 (night)
    
    @classmethod
    def is_daytime(cls) -> bool:
        """Check if it's daytime (6:00-19:59 Moscow time)"""
        hour = datetime.now().hour
        return 6 <= hour < 20
    
    @classmethod
    async def start_scheduler(cls):
        """Start all background schedulers"""
        if cls._is_running:
            return
        
        cls._is_running = True
        logger.warning("🚀 Starting background schedulers...")
        
        cls._tasks = [
            asyncio.create_task(cls._checker_scheduler(), name="checker_scheduler"),
            asyncio.create_task(cls._collector_scheduler(), name="collector_scheduler"),
            asyncio.create_task(cls._cleanup_scheduler(), name="cleanup_scheduler"),
        ]
    
    @classmethod
    async def stop(cls):
        """Stop all background tasks"""
        logger.warning("🛑 Stopping background schedulers...")
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
    async def _checker_scheduler(cls):
        """Schedule subscription checks - only at night (20:00-5:59)"""
        while cls._is_running:
            try:
                if not cls.is_daytime():
                    await cls._dispatch_checks()
                else:
                    logger.debug("Checker: sleeping - daytime")
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"❌ Checker Scheduler Error: {e}")
            
            await asyncio.sleep(cls.CHECK_INTERVAL)
    
    @classmethod
    async def _dispatch_checks(cls):
        """Dispatch subscription checks in optimized batches"""
        try:
            subs = await SubRepo.get_all_subscriptions_for_check()
            if not subs:
                return
            
            BATCH_SIZE = 100
            sub_ids = [sub.id for sub in subs]
            batches = [sub_ids[i:i + BATCH_SIZE] for i in range(0, len(sub_ids), BATCH_SIZE)]
            
            logger.warning(f"🔍 Night check: {len(batches)} batches for {len(subs)} subs")
            
            for batch in batches:
                try:
                    check_subs_batch_task.delay(batch)
                except Exception as e:
                    logger.error(f"Failed to dispatch batch: {e}")
                
                await asyncio.sleep(0.5)
                
        except Exception as e:
            logger.error(f"Error dispatching checks: {e}")
    
    @classmethod
    async def _collector_scheduler(cls):
        """Schedule subscription collection - only during day (6:00-19:59)"""
        while cls._is_running:
            try:
                if cls.is_daytime():
                    logger.warning("☀️ Daytime - starting collection...")
                    run_collector_task.delay()
                else:
                    logger.debug("Collector: sleeping - nighttime")
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"❌ Collector Scheduler Error: {e}")
            
            await asyncio.sleep(cls.COLLECT_INTERVAL)
    
    @classmethod
    async def _cleanup_scheduler(cls):
        """Schedule database cleanup - once per hour"""
        while cls._is_running:
            try:
                logger.debug("Running cleanup...")
                cleanup_database_task.delay()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"❌ Cleanup Scheduler Error: {e}")
            
            await asyncio.sleep(cls.CLEANUP_INTERVAL)

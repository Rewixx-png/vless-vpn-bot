"""
Optimized background scheduler with proper async support.
"""
import asyncio
import logging
from database.repo import SubRepo
from tasks import check_subs_batch_task, run_collector_task, cleanup_database_task

logger = logging.getLogger("Scheduler")


class BackgroundTasks:
    """Optimized background task scheduler"""
    
    _tasks = []
    _is_running = False
    
    # Configurable intervals (in seconds)
    CHECK_INTERVAL = 300      # 5 minutes
    COLLECT_INTERVAL = 1800   # 30 minutes (was 20 minutes)
    CLEANUP_INTERVAL = 600    # 10 minutes (was 3 minutes)
    
    @classmethod
    async def start_scheduler(cls):
        """Start all background schedulers"""
        if cls._is_running:
            return
        
        cls._is_running = True
        logger.info("🚀 Starting background schedulers...")
        
        cls._tasks = [
            asyncio.create_task(cls._checker_scheduler(), name="checker_scheduler"),
            asyncio.create_task(cls._collector_scheduler(), name="collector_scheduler"),
            asyncio.create_task(cls._cleanup_scheduler(), name="cleanup_scheduler"),
        ]
    
    @classmethod
    async def stop(cls):
        """Stop all background tasks"""
        logger.info("🛑 Stopping background schedulers...")
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
        """Schedule subscription checks with optimized batching"""
        while cls._is_running:
            try:
                await cls._dispatch_checks()
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
            
            # Larger batch size for efficiency
            BATCH_SIZE = 100
            sub_ids = [sub.id for sub in subs]
            batches = [sub_ids[i:i + BATCH_SIZE] for i in range(0, len(sub_ids), BATCH_SIZE)]
            
            logger.info(f"📋 Dispatching {len(batches)} check batches for {len(subs)} subscriptions")
            
            for batch in batches:
                try:
                    # Use new async task
                    check_subs_batch_task.delay(batch)
                except Exception as e:
                    logger.error(f"Failed to dispatch batch: {e}")
                
                # Small delay between batches to avoid overwhelming the queue
                await asyncio.sleep(0.5)
                
        except Exception as e:
            logger.error(f"Error dispatching checks: {e}")
    
    @classmethod
    async def _collector_scheduler(cls):
        """Schedule subscription collection"""
        while cls._is_running:
            try:
                logger.info("🌐 Starting subscription collection...")
                run_collector_task.delay()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"❌ Collector Scheduler Error: {e}")
            
            await asyncio.sleep(cls.COLLECT_INTERVAL)
    
    @classmethod
    async def _cleanup_scheduler(cls):
        """Schedule database cleanup"""
        while cls._is_running:
            try:
                logger.info("🧹 Starting database cleanup...")
                cleanup_database_task.delay()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"❌ Cleanup Scheduler Error: {e}")
            
            await asyncio.sleep(cls.CLEANUP_INTERVAL)

"""
Universal Batch Processor for handling large operations with progress tracking.
Reusable component for imports, checks, and other batch operations.
"""
import asyncio
import logging
from typing import Callable, List, Any, Optional, Dict
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger("BatchProcessor")


class BatchStatus(Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class BatchResult:
    total: int
    success: int
    failed: int
    items: List[Dict[str, Any]]
    duration: float


class BatchProcessor:
    """High-performance batch processor with concurrency control"""
    
    def __init__(
        self,
        worker_count: int = 20,
        progress_interval: float = 3.0,
        rate_limit: Optional[int] = None
    ):
        self.worker_count = worker_count
        self.progress_interval = progress_interval
        self.rate_limit = rate_limit
        self.semaphore = asyncio.Semaphore(worker_count)
        self._cancelled = False
        
    async def process(
        self,
        items: List[Any],
        process_func: Callable[[Any], tuple[bool, Any]],
        on_progress: Optional[Callable[[int, int, int, int], None]] = None,
        on_complete: Optional[Callable[[BatchResult], None]] = None
    ) -> BatchResult:
        """
        Process items with progress tracking.
        
        Args:
            items: List of items to process
            process_func: Function that takes item and returns (success, result)
            on_progress: Callback(completed, total, success, failed)
            on_complete: Callback(result)
        """
        start_time = asyncio.get_event_loop().time()
        queue = asyncio.Queue()
        
        # Fill queue
        for idx, item in enumerate(items):
            await queue.put((idx, item))
        
        stats = {
            "completed": 0,
            "success": 0,
            "failed": 0,
            "items": []
        }
        
        async def worker():
            while not self._cancelled:
                try:
                    idx, item = queue.get_nowait()
                except asyncio.QueueEmpty:
                    break
                
                try:
                    async with self.semaphore:
                        if self.rate_limit:
                            await asyncio.sleep(1.0 / self.rate_limit)
                        
                        success, result = await process_func(item)
                        
                        stats["completed"] += 1
                        if success:
                            stats["success"] += 1
                        else:
                            stats["failed"] += 1
                        
                        stats["items"].append({
                            "idx": idx,
                            "item": item,
                            "success": success,
                            "result": result
                        })
                        
                except asyncio.CancelledError:
                    queue.task_done()
                    raise
                except Exception as e:
                    stats["completed"] += 1
                    stats["failed"] += 1
                    stats["items"].append({
                        "idx": idx,
                        "item": item,
                        "success": False,
                        "result": str(e)
                    })
                finally:
                    queue.task_done()
        
        # Start progress updater
        progress_task = None
        if on_progress:
            async def progress_updater():
                while not self._cancelled:
                    try:
                        on_progress(
                            stats["completed"], 
                            len(items), 
                            stats["success"], 
                            stats["failed"]
                        )
                        await asyncio.sleep(self.progress_interval)
                    except asyncio.CancelledError:
                        break
            
            progress_task = asyncio.create_task(progress_updater())
        
        # Start workers
        workers = [
            asyncio.create_task(worker()) 
            for _ in range(min(self.worker_count, len(items)))
        ]
        
        try:
            await queue.join()
        finally:
            if progress_task:
                progress_task.cancel()
                try:
                    await progress_task
                except asyncio.CancelledError:
                    pass
            
            for w in workers:
                w.cancel()
            
            await asyncio.gather(*workers, return_exceptions=True)
        
        duration = asyncio.get_event_loop().time() - start_time
        result = BatchResult(
            total=len(items),
            success=stats["success"],
            failed=stats["failed"],
            items=stats["items"],
            duration=duration
        )
        
        if on_complete:
            on_complete(result)
        
        return result
    
    def cancel(self):
        """Cancel processing"""
        self._cancelled = True


class SmartBatchProcessor(BatchProcessor):
    """Batch processor with adaptive concurrency"""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.error_count = 0
        self.max_errors = 50
    
    async def process(
        self,
        items: List[Any],
        process_func: Callable[[Any], tuple[bool, Any]],
        on_progress: Optional[Callable[[int, int, int, int], None]] = None,
        on_complete: Optional[Callable[[BatchResult], None]] = None
    ) -> BatchResult:
        """Process with adaptive rate limiting on errors"""
        
        adaptive_process_func = process_func
        
        if self.rate_limit:
            original_func = process_func
            
            async def adaptive_func(item):
                # Add delay if too many errors
                if self.error_count > self.max_errors // 2:
                    delay = min(2.0, self.error_count / 20)
                    await asyncio.sleep(delay)
                
                try:
                    result = await original_func(item)
                    if not result[0]:
                        self.error_count += 1
                    return result
                except Exception as e:
                    self.error_count += 1
                    raise
            
            adaptive_process_func = adaptive_func
        
        return await super().process(
            items, 
            adaptive_process_func, 
            on_progress, 
            on_complete
        )


# Convenience function for simple batch operations
async def batch_process(
    items: List[Any],
    process_func: Callable[[Any], Any],
    workers: int = 20,
    progress_callback: Optional[Callable[[int, int], None]] = None
) -> List[Any]:
    """Simple batch processing function"""
    processor = BatchProcessor(worker_count=workers)
    
    async def wrapper(item):
        try:
            result = await process_func(item)
            return (True, result)
        except Exception as e:
            return (False, str(e))
    
    result = await processor.process(
        items, 
        wrapper,
        on_progress=lambda c, t, s, f: progress_callback(c, t) if progress_callback else None
    )
    
    return [item["result"] for item in result.items if item["success"]]

import asyncio
import logging
import psutil
from typing import Callable, List, Any, Optional, Dict
from dataclasses import dataclass

logger = logging.getLogger("BatchProcessor")


@dataclass
class BatchResult:
    total: int
    success: int
    failed: int
    items: List[Dict[str, Any]]
    duration: float


class BatchProcessor:
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
        on_progress: Optional[Callable[[int, int, int, int, int], None]] = None,
        on_complete: Optional[Callable[[BatchResult], None]] = None
    ) -> BatchResult:
        start_time = asyncio.get_event_loop().time()
        queue = asyncio.Queue()
        
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
                        
                        try:
                            success, result = await asyncio.wait_for(
                                process_func(item), 
                                timeout=25.0
                            )
                        except asyncio.TimeoutError:
                            success = False
                            result = "WATCHDOG_TIMEOUT"
                        
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
        
        progress_task = None
        if on_progress:
            async def progress_updater():
                while not self._cancelled:
                    try:
                        if asyncio.iscoroutinefunction(on_progress):
                            await on_progress(
                                stats["completed"], 
                                len(items), 
                                stats["success"], 
                                stats["failed"],
                                self.worker_count
                            )
                        else:
                            on_progress(
                                stats["completed"], 
                                len(items), 
                                stats["success"], 
                                stats["failed"],
                                self.worker_count
                            )
                        
                        if stats["completed"] >= len(items):
                            break
                            
                        await asyncio.sleep(self.progress_interval)
                    except asyncio.CancelledError:
                        break
                    except Exception as e:
                        logger.debug(f"Progress callback error: {e}")
            
            progress_task = asyncio.create_task(progress_updater())
        
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
        self._cancelled = True


class SmartBatchProcessor(BatchProcessor):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.error_count = 0
        self.max_errors = 50
    
    async def process(
        self,
        items: List[Any],
        process_func: Callable[[Any], tuple[bool, Any]],
        on_progress: Optional[Callable[[int, int, int, int, int], None]] = None,
        on_complete: Optional[Callable[[BatchResult], None]] = None
    ) -> BatchResult:
        
        adaptive_process_func = process_func
        
        if self.rate_limit:
            original_func = process_func
            
            async def adaptive_func(item):
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


class CpuAdaptiveProcessor(BatchProcessor):
    def __init__(self, initial_workers: int = 50, min_workers: int = 10, max_workers: int = 1000, target_cpu: float = 80.0):
        super().__init__(worker_count=initial_workers)
        self.min_workers = min_workers
        self.max_workers = max_workers
        self.target_cpu = target_cpu
        self.current_concurrency = initial_workers
        self._semaphore = asyncio.Semaphore(initial_workers)
        
    async def process(
        self,
        items: List[Any],
        process_func: Callable[[Any], tuple[bool, Any]],
        on_progress: Optional[Callable[[int, int, int, int, int], None]] = None,
        on_complete: Optional[Callable[[BatchResult], None]] = None
    ) -> BatchResult:
        
        start_time = asyncio.get_event_loop().time()
        queue = asyncio.Queue()
        
        for idx, item in enumerate(items):
            await queue.put((idx, item))
        
        stats = {
            "completed": 0,
            "success": 0,
            "failed": 0,
            "items": []
        }
        
        active_workers = 0
        worker_tasks = set()
        
        # Initial non-blocking call
        psutil.cpu_percent(interval=None)
        
        async def worker():
            nonlocal active_workers
            active_workers += 1
            try:
                while not self._cancelled:
                    try:
                        idx, item = queue.get_nowait()
                    except asyncio.QueueEmpty:
                        break
                    
                    try:
                        try:
                            success, result = await asyncio.wait_for(
                                process_func(item), 
                                timeout=30.0
                            )
                        except asyncio.TimeoutError:
                            success = False
                            result = "TIMEOUT"
                        
                        stats["completed"] += 1
                        if success:
                            stats["success"] += 1
                        else:
                            stats["failed"] += 1
                        
                        stats["items"].append({"idx": idx, "item": item, "success": success, "result": result})
                        
                    except asyncio.CancelledError:
                        queue.task_done()
                        raise
                    except Exception:
                        stats["completed"] += 1
                        stats["failed"] += 1
                    finally:
                        queue.task_done()
            finally:
                active_workers -= 1

        async def cpu_monitor():
            while not self._cancelled and stats["completed"] < len(items):
                # Wait 1.5s to get a reliable reading
                await asyncio.sleep(1.5)
                cpu_usage = psutil.cpu_percent(interval=None)
                
                # Filter out 0.0 readings if we have active workers (likely invalid reading)
                if cpu_usage == 0.0 and active_workers > 10:
                    continue
                
                # Aggressive scaling: +/- 50 workers
                if cpu_usage < self.target_cpu - 10:
                    self.current_concurrency = min(self.max_workers, self.current_concurrency + 50)
                elif cpu_usage > self.target_cpu:
                    self.current_concurrency = max(self.min_workers, self.current_concurrency - 30)
                
                if on_progress:
                     if asyncio.iscoroutinefunction(on_progress):
                         await on_progress(stats["completed"], len(items), stats["success"], stats["failed"], self.current_concurrency)
                     else:
                         on_progress(stats["completed"], len(items), stats["success"], stats["failed"], self.current_concurrency)
                         
        monitor_task = asyncio.create_task(cpu_monitor())
        
        try:
            while not queue.empty() or active_workers > 0:
                if self._cancelled:
                    break
                    
                target = self.current_concurrency
                current = len(worker_tasks)
                
                clean_tasks = {t for t in worker_tasks if not t.done()}
                worker_tasks.clear()
                worker_tasks.update(clean_tasks)
                current = len(worker_tasks)
                
                if current < target and not queue.empty():
                    needed = target - current
                    for _ in range(needed):
                        if queue.empty(): break
                        t = asyncio.create_task(worker())
                        worker_tasks.add(t)
                
                await asyncio.sleep(0.1)
                
                if queue.empty() and active_workers == 0:
                    break
                    
        finally:
            self._cancelled = True
            monitor_task.cancel()
            for t in worker_tasks:
                t.cancel()
            await asyncio.gather(*worker_tasks, return_exceptions=True)
            
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

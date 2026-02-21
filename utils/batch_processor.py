import asyncio
import logging
import psutil
import time
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
    """
    Base processor using a fixed Semaphore for concurrency control.
    """
    def __init__(
        self,
        worker_count: int = 20,
        progress_interval: float = 3.0,
        rate_limit: Optional[int] = None
    ):
        self.worker_count = worker_count
        self.progress_interval = progress_interval
        self.rate_limit = rate_limit
        self._cancelled = False
        
    async def process(
        self,
        items: List[Any],
        process_func: Callable[[Any], tuple[bool, Any]],
        on_progress: Optional[Callable[[int, int, int, int, int], None]] = None,
        on_complete: Optional[Callable[[BatchResult], None]] = None
    ) -> BatchResult:
        start_time = time.time()
        queue = asyncio.Queue()
        
        for idx, item in enumerate(items):
            queue.put_nowait((idx, item))
        
        stats = {
            "completed": 0,
            "success": 0,
            "failed": 0,
            "items": []
        }
        
        semaphore = asyncio.Semaphore(self.worker_count)
        
        async def worker():
            while not self._cancelled:
                try:
                    idx, item = queue.get_nowait()
                except asyncio.QueueEmpty:
                    break
                
                async with semaphore:
                    try:
                        if self.rate_limit:
                            await asyncio.sleep(1.0 / self.rate_limit)
                        
                        try:
                            # Hard timeout 45s to prevent stuck workers
                            success, result = await asyncio.wait_for(
                                process_func(item), 
                                timeout=45.0
                            )
                        except asyncio.TimeoutError:
                            success = False
                            result = "WATCHDOG_TIMEOUT"
                        except Exception as e:
                            success = False
                            result = f"Worker Error: {str(e)}"
                        
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
                        
                    except Exception as e:
                        logger.error(f"Critical worker crash: {e}")
                        stats["completed"] += 1
                        stats["failed"] += 1
                    finally:
                        queue.task_done()
        
        # Progress reporter
        progress_task = None
        if on_progress:
            async def progress_updater():
                while not self._cancelled and stats["completed"] < len(items):
                    try:
                        await asyncio.sleep(self.progress_interval)
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
                    except Exception:
                        pass
            
            progress_task = asyncio.create_task(progress_updater())
        
        # Spawn workers
        # Limit total coroutines to avoid memory explosion on huge lists
        num_workers = min(self.worker_count * 2, len(items))
        workers = [asyncio.create_task(worker()) for _ in range(num_workers)]
            
        await asyncio.gather(*workers, return_exceptions=True)
        
        if progress_task:
            progress_task.cancel()
            try: await progress_task
            except: pass
        
        duration = time.time() - start_time
        result = BatchResult(
            total=len(items),
            success=stats["success"],
            failed=stats["failed"],
            items=stats["items"],
            duration=duration
        )
        
        if on_complete:
            try: on_complete(result)
            except: pass
        
        return result
    
    def cancel(self):
        self._cancelled = True


class SmartBatchProcessor(BatchProcessor):
    """
    Extended processor with error tracking (backwards compatibility).
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.error_count = 0
        self.max_errors = 50
    
    async def process(self, items, process_func, on_progress=None, on_complete=None):
        return await super().process(items, process_func, on_progress, on_complete)


class CpuAdaptiveProcessor(BatchProcessor):
    """
    Processor that aggressively adjusts concurrency based on CPU usage.
    """
    def __init__(self, initial_workers: int = 200, min_workers: int = 50, max_workers: int = 2000, target_cpu: float = 90.0):
        super().__init__(worker_count=initial_workers)
        self.min_workers = min_workers
        self.max_workers = max_workers
        self.target_cpu = target_cpu
        self.current_concurrency = initial_workers
        
    async def process(
        self,
        items: List[Any],
        process_func: Callable[[Any], tuple[bool, Any]],
        on_progress: Optional[Callable[[int, int, int, int, int], None]] = None,
        on_complete: Optional[Callable[[BatchResult], None]] = None
    ) -> BatchResult:
        
        start_time = time.time()
        queue = asyncio.Queue()
        
        for idx, item in enumerate(items):
            queue.put_nowait((idx, item))
        
        stats = {
            "completed": 0,
            "success": 0,
            "failed": 0,
            "items": []
        }
        
        active_tasks_count = 0
        
        async def worker():
            nonlocal active_tasks_count
            while not self._cancelled:
                try:
                    idx, item = queue.get_nowait()
                except asyncio.QueueEmpty:
                    break
                
                # Dynamic semaphore logic
                while active_tasks_count >= self.current_concurrency:
                    await asyncio.sleep(0.05) # Быстрая проверка
                
                active_tasks_count += 1
                
                try:
                    try:
                        success, result = await asyncio.wait_for(
                            process_func(item), 
                            timeout=30.0
                        )
                    except asyncio.TimeoutError:
                        success = False
                        result = "TIMEOUT"
                    except Exception as e:
                        success = False
                        result = str(e)
                    
                    stats["completed"] += 1
                    if success:
                        stats["success"] += 1
                    else:
                        stats["failed"] += 1
                    
                    stats["items"].append({"idx": idx, "item": item, "success": success, "result": result})
                    
                except Exception:
                    stats["completed"] += 1
                    stats["failed"] += 1
                finally:
                    active_tasks_count -= 1
                    queue.task_done()

        # Aggressive CPU Monitor
        async def cpu_monitor():
            while not self._cancelled and stats["completed"] < len(items):
                await asyncio.sleep(1.0) # Проверяем каждую секунду
                try:
                    cpu_usage = psutil.cpu_percent(interval=None)
                    
                    # Агрессивный рост (геометрическая прогрессия)
                    if cpu_usage < self.target_cpu - 15:
                        # Если CPU < 75%, увеличиваем на 50% сразу
                        self.current_concurrency = int(min(self.max_workers, self.current_concurrency * 1.5))
                    elif cpu_usage < self.target_cpu:
                        # Если CPU близко к цели, добавляем линейно
                        self.current_concurrency = int(min(self.max_workers, self.current_concurrency + 50))
                    elif cpu_usage > self.target_cpu + 5:
                        # Если перегрев, сбрасываем плавно
                        self.current_concurrency = int(max(self.min_workers, self.current_concurrency * 0.8))
                        
                    if on_progress:
                         if asyncio.iscoroutinefunction(on_progress):
                             await on_progress(stats["completed"], len(items), stats["success"], stats["failed"], self.current_concurrency)
                         else:
                             on_progress(stats["completed"], len(items), stats["success"], stats["failed"], self.current_concurrency)
                except:
                    pass
                         
        monitor_task = asyncio.create_task(cpu_monitor())
        
        # Start workers. We start A LOT of runners to consume the queue rapidly
        num_runners = self.max_workers + 100 
        runners = [asyncio.create_task(worker()) for _ in range(num_runners)]
        
        await asyncio.gather(*runners, return_exceptions=True)
            
        self._cancelled = True
        monitor_task.cancel()
            
        duration = time.time() - start_time
        result = BatchResult(
            total=len(items),
            success=stats["success"],
            failed=stats["failed"],
            items=stats["items"],
            duration=duration
        )
        
        if on_complete:
            try: on_complete(result)
            except: pass
        
        return result

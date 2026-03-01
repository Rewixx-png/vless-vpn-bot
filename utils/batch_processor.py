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
    def __init__(
        self,
        worker_count: int = 40,
        progress_interval: float = 2.0,
        rate_limit: Optional[int] = None,
        max_concurrent_per_core: int = 4
    ):
        import multiprocessing
        cpu_count = multiprocessing.cpu_count()
        self.worker_count = min(worker_count, cpu_count * max_concurrent_per_core)
        self.progress_interval = progress_interval
        self.rate_limit = rate_limit
        self._cancelled = False
        self.cpu_count = cpu_count
        
    async def process(
        self,
        items: List[Any],
        process_func: Callable[[Any], tuple[bool, Any]],
        on_progress: Optional[Callable[[int, int, int, int, int], None]] = None,
        on_complete: Optional[Callable[[BatchResult], None]] = None,
        collect_results: bool = True
    ) -> BatchResult:
        start_time = time.time()
        queue = asyncio.Queue()
        
        for idx, item in enumerate(items):
            queue.put_nowait((idx, item))
        
        stats = {
            "completed": 0,
            "success": 0,
            "failed": 0,
            "items":[]
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
                        
                        if collect_results:
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
                        del item
                        del result
        
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
        
        num_workers = min(self.worker_count * 2, len(items))
        workers =[asyncio.create_task(worker()) for _ in range(num_workers)]
            
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
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.error_count = 0
        self.max_errors = 50
    
    async def process(self, items, process_func, on_progress=None, on_complete=None, collect_results=True):
        return await super().process(
            items,
            process_func,
            on_progress,
            on_complete,
            collect_results=collect_results
        )

class CpuAdaptiveProcessor(BatchProcessor):
    def __init__(
        self, 
        initial_workers: int = 5, 
        min_workers: int = 5, 
        max_workers: int = 200, 
        target_cpu: float = 85.0,
        target_ram: float = 90.0
    ):
        super().__init__(worker_count=initial_workers)
        self.min_workers = min_workers
        self.max_workers = max_workers
        self.target_cpu = target_cpu
        self.target_ram = target_ram
        self.current_concurrency = initial_workers
        self.increase_step = 5
        
    async def process(
        self,
        items: List[Any],
        process_func: Callable[[Any], tuple[bool, Any]],
        on_progress: Optional[Callable[[int, int, int, int, int], None]] = None,
        on_complete: Optional[Callable[[BatchResult], None]] = None,
        collect_results: bool = True
    ) -> BatchResult:
        
        start_time = time.time()
        queue = asyncio.Queue()
        
        for idx, item in enumerate(items):
            queue.put_nowait((idx, item))
        
        stats = {
            "completed": 0,
            "success": 0,
            "failed": 0,
            "items":[]
        }
        
        active_tasks_count = 0
        
        async def worker():
            nonlocal active_tasks_count
            while not self._cancelled:
                try:
                    idx, item = queue.get_nowait()
                except asyncio.QueueEmpty:
                    break
                
                while active_tasks_count >= self.current_concurrency:
                    await asyncio.sleep(0.1)
                
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
                    
                    if collect_results:
                        stats["items"].append({"idx": idx, "item": item, "success": success, "result": result})
                    
                except Exception:
                    stats["completed"] += 1
                    stats["failed"] += 1
                finally:
                    active_tasks_count -= 1
                    queue.task_done()
                    del item
                    if 'result' in locals():
                        del result

        async def cpu_monitor():
            while not self._cancelled and stats["completed"] < len(items):
                await asyncio.sleep(2.0)
                try:
                    cpu_usage = psutil.cpu_percent(interval=None)
                    ram_usage = psutil.virtual_memory().percent
                    
                    if ram_usage >= self.target_ram:
                        self.current_concurrency = int(max(self.min_workers, self.current_concurrency - 40))
                        self.increase_step = 5
                    elif cpu_usage < self.target_cpu:
                        self.current_concurrency = int(min(self.max_workers, self.current_concurrency + self.increase_step))
                        self.increase_step = min(20, self.increase_step + 5)
                    else:
                        self.current_concurrency = int(max(self.min_workers, self.current_concurrency - 20))
                        self.increase_step = 5
                        
                    if on_progress:
                         if asyncio.iscoroutinefunction(on_progress):
                             await on_progress(stats["completed"], len(items), stats["success"], stats["failed"], self.current_concurrency)
                         else:
                             on_progress(stats["completed"], len(items), stats["success"], stats["failed"], self.current_concurrency)
                except Exception:
                    pass
                         
        monitor_task = asyncio.create_task(cpu_monitor())
        
        num_runners = self.max_workers + 40 
        runners =[asyncio.create_task(worker()) for _ in range(num_runners)]
        
        await asyncio.gather(*runners, return_exceptions=True)
            
        self._cancelled = True
        monitor_task.cancel()
            
        duration = time.time() - start_time
        res_obj = BatchResult(
            total=len(items),
            success=stats["success"],
            failed=stats["failed"],
            items=stats["items"],
            duration=duration
        )
        
        if on_complete:
            try: on_complete(res_obj)
            except: pass
        
        return res_obj

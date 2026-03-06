import asyncio
import psutil
import time
from typing import Callable, List, Any, Optional, Dict
from dataclasses import dataclass

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
        
        queue = asyncio.Queue(maxsize=self.worker_count * 3)
        
        stats = {
            "completed": 0,
            "success": 0,
            "failed": 0,
            "items":[]
        }
        
        semaphore = asyncio.Semaphore(self.worker_count)

        async def producer():
            for idx, item in enumerate(items):
                if self._cancelled:
                    break
                await queue.put((idx, item))

        prod_task = asyncio.create_task(producer())
        
        async def worker():
            while not self._cancelled:
                if prod_task.done() and queue.empty():
                    break
                
                try:
                    idx, item = await asyncio.wait_for(queue.get(), timeout=1.0)
                except asyncio.TimeoutError:
                    continue
                
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
                        
                    except Exception:
                        stats["completed"] += 1
                        stats["failed"] += 1
                    finally:
                        queue.task_done()
        
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
        workers = [asyncio.create_task(worker()) for _ in range(num_workers)]
            
        await asyncio.gather(*workers, return_exceptions=True)
        
        if progress_task:
            progress_task.cancel()
            try: await progress_task
            except: pass
            
        if not prod_task.done():
            prod_task.cancel()
            try: await prod_task
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

class CpuAdaptiveProcessor(BatchProcessor):
    def __init__(
        self, 
        initial_workers: int = 50, 
        min_workers: int = 10, 
        max_workers: int = 400,
        target_cpu: float = 85.0,
        target_ram: float = 90.0
    ):
        super().__init__(worker_count=max_workers)
        self.min_workers = min_workers
        self.max_workers = max_workers
        self.target_cpu = target_cpu
        self.target_ram = target_ram
        self.current_concurrency = initial_workers
        
    async def process(
        self,
        items: List[Any],
        process_func: Callable[[Any], tuple[bool, Any]],
        on_progress: Optional[Callable[[int, int, int, int, int], None]] = None,
        on_complete: Optional[Callable[[BatchResult], None]] = None,
        collect_results: bool = True
    ) -> BatchResult:
        
        start_time = time.time()
        queue = asyncio.Queue(maxsize=1000)
        
        stats = {
            "completed": 0,
            "success": 0,
            "failed": 0,
            "items":[]
        }
        
        active_tasks_count = 0

        async def producer():
            for idx, item in enumerate(items):
                if self._cancelled:
                    break
                await queue.put((idx, item))

        prod_task = asyncio.create_task(producer())
        
        async def worker():
            nonlocal active_tasks_count
            while not self._cancelled:
                if prod_task.done() and queue.empty():
                    break
                
                if active_tasks_count >= self.current_concurrency:
                    await asyncio.sleep(0.5)
                    continue
                
                try:
                    idx, item = queue.get_nowait()
                except asyncio.QueueEmpty:
                    await asyncio.sleep(0.5)
                    continue
                
                active_tasks_count += 1
                try:
                    success, result = await asyncio.wait_for(
                        process_func(item), 
                        timeout=40.0
                    )
                    stats["completed"] += 1
                    if success: stats["success"] += 1
                    else: stats["failed"] += 1
                    if collect_results:
                        stats["items"].append({"idx": idx, "item": item, "success": success, "result": result})
                except Exception:
                    stats["completed"] += 1
                    stats["failed"] += 1
                finally:
                    active_tasks_count -= 1
                    queue.task_done()

        async def monitor():
            while not self._cancelled and stats["completed"] < len(items):
                await asyncio.sleep(2.0)
                try:
                    cpu_usage = psutil.cpu_percent(interval=None)
                    ram_usage = psutil.virtual_memory().percent
                    
                    if ram_usage >= self.target_ram:
                        self.current_concurrency = max(self.min_workers, int(self.current_concurrency * 0.5))
                    elif cpu_usage >= self.target_cpu:
                        self.current_concurrency = max(self.min_workers, int(self.current_concurrency * 0.8))
                    else:
                        diff = self.target_cpu - cpu_usage
                        if diff > 50: self.current_concurrency += 50
                        elif diff > 25: self.current_concurrency += 20
                        else: self.current_concurrency += 10
                        
                    self.current_concurrency = min(self.current_concurrency, self.max_workers)
                        
                    if on_progress:
                         if asyncio.iscoroutinefunction(on_progress):
                             await on_progress(stats["completed"], len(items), stats["success"], stats["failed"], self.current_concurrency)
                         else:
                             on_progress(stats["completed"], len(items), stats["success"], stats["failed"], self.current_concurrency)
                except Exception:
                    pass

        monitor_task = asyncio.create_task(monitor())
        workers =[asyncio.create_task(worker()) for _ in range(min(self.max_workers, len(items)))]

        global_timeout = max(300.0, len(items) * 60.0)
        try:
            await asyncio.wait_for(
                asyncio.gather(*workers, return_exceptions=True),
                timeout=global_timeout
            )
        except asyncio.TimeoutError:
            self._cancelled = True
            for w in workers:
                if not w.done():
                    w.cancel()
        
        self._cancelled = True
        monitor_task.cancel()
        if not prod_task.done():
            prod_task.cancel()
            try: await prod_task
            except: pass
            
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

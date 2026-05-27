"""
Async Celery Task utilities for proper async/await support without event loop hacks.
"""
import asyncio
import functools
from typing import Callable, Any
from celery import Task
from celery_app import app


class AsyncTask(Task):
    def __call__(self, *args, **kwargs):
        if asyncio.iscoroutinefunction(self.run):
            return asyncio.run(self.run(*args, **kwargs))
        return self.run(*args, **kwargs)


def async_task(*args, **kwargs):
    def decorator(func: Callable) -> Task:
        @functools.wraps(func)
        @app.task(*args, **kwargs, base=AsyncTask)
        def wrapper(*f_args, **f_kwargs):
            return func(*f_args, **f_kwargs)
        return wrapper
    return decorator


class AsyncWorkerPool:
    def __init__(self, worker_count: int = 10):
        self.worker_count = worker_count
        self.semaphore = asyncio.Semaphore(worker_count)
    
    async def process_batch(
        self, 
        items: list[Any], 
        process_func: Callable[[Any], Any],
        on_progress: Callable[[int, int], None] = None
    ) -> list[Any]:
        results = []
        completed = 0
        total = len(items)
        
        async def process_one(item):
            nonlocal completed
            async with self.semaphore:
                try:
                    result = await process_func(item)
                    completed += 1
                    if on_progress and completed % max(1, total // 10) == 0:
                        on_progress(completed, total)
                    return result
                except Exception:
                    completed += 1
                    return None
        
        tasks = [process_one(item) for item in items]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        return [r for r in results if not isinstance(r, Exception) and r is not None]


class RateLimiter:
    def __init__(self, max_calls: int, period: float = 1.0):
        self.max_calls = max_calls
        self.period = period
        self.calls = []
        self.lock = asyncio.Lock()
    
    async def acquire(self) -> None:
        while True:
            sleep_time = 0.0
            async with self.lock:
                now = asyncio.get_event_loop().time()
                self.calls = [c for c in self.calls if now - c < self.period]
                if len(self.calls) >= self.max_calls:
                    sleep_time = self.calls[0] + self.period - now
                else:
                    self.calls.append(now)
                    return
            if sleep_time > 0:
                await asyncio.sleep(sleep_time)

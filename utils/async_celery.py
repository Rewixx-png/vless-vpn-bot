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



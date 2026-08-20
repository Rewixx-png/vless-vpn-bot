import asyncio
import logging
import logging.handlers

from celery_app import app
from utils.async_celery import AsyncTask

def setup_log_rotation():
    root_logger = logging.getLogger()
    if not any(isinstance(h, logging.handlers.RotatingFileHandler) for h in root_logger.handlers):
        handler = logging.handlers.RotatingFileHandler("worker.log", maxBytes=15*1024*1024, backupCount=3)
        formatter = logging.Formatter('[%(asctime)s] %(levelname)s in %(name)s: %(message)s')
        handler.setFormatter(formatter)
        root_logger.addHandler(handler)

logger = logging.getLogger("Worker")

async def setup_loop_exception_handler_async() -> None:
    loop = asyncio.get_running_loop()

    def custom_exc_handler(loop, context):
        msg = context.get("message", "")
        exc = context.get("exception")
        if exc:
            exc_type = str(type(exc)).lower()
            if any(err in exc_type for err in ["gaierror", "dnserror", "clientconnectorerror", "timeouterror", "cancellederror", "softtimelimitexceeded"]):
                return
        if "Future exception was never retrieved" in msg or "Task was destroyed but it is pending" in msg:
            return
        loop.default_exception_handler(context)

    loop.set_exception_handler(custom_exc_handler)



def format_time(seconds: int) -> str:
    if seconds < 60:
        return f"{seconds} сек"
    elif seconds < 3600:
        m = seconds // 60
        s = seconds % 60
        return f"{m} мин {s} сек"
    else:
        h = seconds // 3600
        m = (seconds % 3600) // 60
        return f"{h} ч {m} мин"

OptimizedTask = AsyncTask  # ponytail: alias, all task files use this; rename when touching them
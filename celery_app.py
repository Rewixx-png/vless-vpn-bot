import os
import sys
import logging
import warnings
import asyncio
from celery import Celery, signals, Task
from celery.exceptions import SecurityWarning
from kombu import Queue, Exchange
from config import config

try:
    from settings import WORKER_SETTINGS, BEAT_SCHEDULE
except ImportError:
    WORKER_SETTINGS = {
        "concurrency": 8,
        "max_tasks_per_child": 50,
        "prefetch_multiplier": 2,
    }
    BEAT_SCHEDULE = {"collector_interval": 3600}

warnings.simplefilter("ignore", SecurityWarning)
os.environ.setdefault("C_FORCE_ROOT", "1")


class AsyncTask(Task):
    def __call__(self, *args, **kwargs):
        if asyncio.iscoroutinefunction(self.run):
            try:
                loop = asyncio.get_event_loop()
                if loop.is_closed():
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)

            return loop.run_until_complete(self.run(*args, **kwargs))

        return self.run(*args, **kwargs)


app = Celery(
    "vless_bot_worker",
    broker=config.REDIS_URL,
    backend=config.REDIS_URL,
    include=["tasks"],
    task_cls=AsyncTask,
)

app.conf.task_queues = (
    Queue("high_priority", Exchange("high_priority"), routing_key="high_priority"),
    Queue("low_priority", Exchange("low_priority"), routing_key="low_priority"),
)

app.conf.task_routes = {
    "tasks.check_subs_batch_task": {"queue": "high_priority"},
    "tasks.run_admin_recheck_task": {"queue": "high_priority"},
    "tasks.cleanup_database_task": {"queue": "high_priority"},
    "tasks.run_collector_task": {"queue": "low_priority"},
    "tasks.check_stability_task": {"queue": "low_priority"},
    "tasks.update_geoip_task": {"queue": "low_priority"},
    "tasks.run_backup_snapshot_task": {"queue": "low_priority"},
    "tasks.update_tg_proxy_task": {"queue": "high_priority"},
    "tasks.probe_blocked_users_task": {"queue": "low_priority"},
}

app.conf.beat_schedule = {
    "run-collector-every-30-minutes": {
        "task": "tasks.run_collector_task",
        "schedule": float(BEAT_SCHEDULE.get("collector_interval", 3600.0)),
    },
    "check-stability-every-30-minutes": {
        "task": "tasks.check_stability_task",
        "schedule": float(BEAT_SCHEDULE.get("stability_interval", 3600.0)),
    },
    "update-geoip-monthly": {
        "task": "tasks.update_geoip_task",
        "schedule": 2592000.0,
    },
    "backup-db-hourly": {
        "task": "tasks.run_backup_snapshot_task",
        "schedule": float(BEAT_SCHEDULE.get("backup_interval", 3600.0)),
    },
    "update-tg-proxy-hourly": {
        "task": "tasks.update_tg_proxy_task",
        "schedule": float(BEAT_SCHEDULE.get("tg_proxy_interval", 3600.0)),
    },
    "probe-blocked-users-hourly": {
        "task": "tasks.probe_blocked_users_task",
        "schedule": float(BEAT_SCHEDULE.get("user_probe_interval", 3600.0)),
    },
}

app.conf.update(
    timezone="Europe/Moscow",
    enable_utc=True,
    worker_concurrency=WORKER_SETTINGS.get("concurrency", 8),
    worker_prefetch_multiplier=WORKER_SETTINGS.get("prefetch_multiplier", 2),
    worker_max_tasks_per_child=WORKER_SETTINGS.get("max_tasks_per_child", 50),
    worker_max_memory_per_child=150000,
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    worker_redirect_stdouts=False,
    broker_connection_retry_on_startup=True,
    task_default_queue="low_priority",
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_pool_restarts=True,
    task_time_limit=300,
    task_soft_time_limit=240,
)


@signals.after_setup_logger.connect
def setup_loggers(logger, *args, **kwargs):
    noisy = ["celery", "kombu", "asyncio", "aiogram", "aiohttp"]
    for name in noisy:
        logging.getLogger(name).setLevel(logging.WARNING)


if __name__ == "__main__":
    app.start()

import os
import logging
import warnings
import asyncio
from celery import Celery, signals, Task
from celery.exceptions import SecurityWarning
from kombu import Queue, Exchange
from config import config

warnings.simplefilter('ignore', SecurityWarning)
os.environ.setdefault('C_FORCE_ROOT', '1')

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
    'vless_bot_worker',
    broker=config.REDIS_URL,
    backend=config.REDIS_URL,
    include=['tasks'],
    task_cls=AsyncTask
)

app.conf.task_queues = (
    Queue('high_priority', Exchange('high_priority'), routing_key='high_priority'),
    Queue('low_priority', Exchange('low_priority'), routing_key='low_priority'),
)

app.conf.task_routes = {
    'tasks.check_subs_batch_task': {'queue': 'high_priority'},
    'tasks.run_collector_task': {'queue': 'low_priority'},
    'tasks.cleanup_database_task': {'queue': 'high_priority'},
    'tasks.check_stability_task': {'queue': 'low_priority'},
    'tasks.update_geoip_task': {'queue': 'low_priority'},
}

app.conf.beat_schedule = {
    'run-collector-every-30-minutes': {
        'task': 'tasks.run_collector_task',
        'schedule': 1800.0,
    },
    'check-stability-every-30-minutes': {
        'task': 'tasks.check_stability_task',
        'schedule': 1800.0,
    },
    'update-geoip-monthly': {
        'task': 'tasks.update_geoip_task',
        'schedule': 2592000.0, 
    },
}

app.conf.update(
    timezone='Europe/Moscow',
    enable_utc=True,
    worker_concurrency=2,
    worker_prefetch_multiplier=1,
    worker_max_tasks_per_child=25,
    worker_max_memory_per_child=120000, 
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    worker_redirect_stdouts=False,
    broker_connection_retry_on_startup=True,
    task_default_queue='low_priority',
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_pool_restarts=True,
    task_time_limit=300,
    task_soft_time_limit=240
)

@signals.after_setup_logger.connect
def setup_loggers(logger, *args, **kwargs):
    noisy = ["celery", "kombu", "asyncio", "aiogram", "aiohttp"]
    for name in noisy:
        logging.getLogger(name).setLevel(logging.WARNING)

if __name__ == '__main__':
    app.start()
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
    Queue('medium_priority', Exchange('medium_priority'), routing_key='medium_priority'),
    Queue('low_priority', Exchange('low_priority'), routing_key='low_priority'),
    Queue('stability_check', Exchange('stability_check'), routing_key='stability_check'),
    Queue('geoip_update', Exchange('geoip_update'), routing_key='geoip_update'),
)

app.conf.task_routes = {
    'tasks.check_subs_batch_task': {'queue': 'high_priority'},
    'tasks.run_collector_task': {'queue': 'low_priority'},
    'tasks.cleanup_database_task': {'queue': 'high_priority'},
}

app.conf.beat_schedule = {
    'run-collector-every-5-minutes': {
        'task': 'tasks.run_collector_task',
        'schedule': 300.0,
    },
}

app.conf.update(
    timezone='Europe/Moscow',
    enable_utc=True,
    worker_concurrency=16,
    worker_prefetch_multiplier=2,
    worker_max_tasks_per_child=200,
    worker_max_memory_per_child=300000,
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    worker_redirect_stdouts=False,
    broker_connection_retry_on_startup=True,
    task_default_queue='low_priority',
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_pool_restarts=True
)

@signals.after_setup_logger.connect
def setup_loggers(logger, *args, **kwargs):
    noisy = ["celery", "kombu", "asyncio"]
    for name in noisy:
        logging.getLogger(name).setLevel(logging.WARNING)

if __name__ == '__main__':
    app.start()
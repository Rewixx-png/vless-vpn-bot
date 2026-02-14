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
    """Base task class with native async support"""
    
    def __call__(self, *args, **kwargs):
        """Override to properly handle async functions"""
        if asyncio.iscoroutinefunction(self.run):
            # Get or create event loop
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
}

app.conf.update(
    timezone='Europe/Moscow',
    enable_utc=True,
    worker_concurrency=30,
    worker_prefetch_multiplier=1,
    worker_max_tasks_per_child=150,
    worker_max_memory_per_child=300000,
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    worker_redirect_stdouts=False,
    broker_connection_retry_on_startup=True,
    task_default_queue='low_priority'
)

@signals.after_setup_logger.connect
def setup_loggers(logger, *args, **kwargs):
    noisy = ["celery", "kombu", "asyncio"]
    for name in noisy:
        logging.getLogger(name).setLevel(logging.WARNING)

if __name__ == '__main__':
    app.start()
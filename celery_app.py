import os
import logging
from celery import Celery, signals
from config import config

app = Celery(
    'vless_bot_worker',
    broker=config.REDIS_URL,
    backend=config.REDIS_URL,
    include=['tasks']
)

app.conf.update(
    timezone='Europe/Moscow',
    enable_utc=True,
    worker_max_tasks_per_child=100,
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    worker_redirect_stdouts=False,
    worker_hijack_root_logger=False 
)

@signals.after_setup_logger.connect
def setup_loggers(logger, *args, **kwargs):
    # Убираем шум от стандартных логгеров Celery
    noisy_loggers = [
        "celery",
        "celery.app.trace",
        "celery.worker.strategy",
        "celery.redirected",
        "kombu",
        "asyncio"
    ]
    
    for name in noisy_loggers:
        logging.getLogger(name).setLevel(logging.WARNING)

    # Настраиваем формат для наших логгеров
    formatter = logging.Formatter('%(asctime)s | %(message)s', datefmt='%H:%M:%S')
    
    # Применяем формат к корневому логгеру, если нужно, или конкретным
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    
    root_logger = logging.getLogger()
    # Очищаем старые хендлеры, чтобы не дублировалось
    if root_logger.hasHandlers():
        root_logger.handlers.clear()
    
    root_logger.addHandler(console_handler)
    root_logger.setLevel(logging.INFO)

if __name__ == '__main__':
    app.start()
import os
import logging
import warnings
from celery import Celery, signals
from celery.exceptions import SecurityWarning
from config import config

# Игнорируем SecurityWarning (запуск от root) и настраиваем окружение
warnings.simplefilter('ignore', SecurityWarning)
os.environ.setdefault('C_FORCE_ROOT', '1')

app = Celery(
    'vless_bot_worker',
    broker=config.REDIS_URL,
    backend=config.REDIS_URL,
    include=['tasks']
)

app.conf.update(
    timezone='Europe/Moscow',
    enable_utc=True,
    # ВАЖНО: Строго 1 процесс. Это предотвращает запуск двух тяжелых задач одновременно.
    worker_concurrency=1,
    # Перезапускаем воркер чаще, чтобы гарантированно возвращать память системе
    worker_max_tasks_per_child=10,
    # Лимиты памяти (мягкий и жесткий перезапуск при превышении) - в КБ
    # 500 МБ - если один процесс съест столько, он перезапустится после завершения задачи
    worker_max_memory_per_child=500000, 
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    worker_redirect_stdouts=False,
    worker_hijack_root_logger=False,
    broker_connection_retry_on_startup=True
)

@signals.after_setup_logger.connect
def setup_loggers(logger, *args, **kwargs):
    # Список модулей, которые нужно заглушить
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

    formatter = logging.Formatter('%(asctime)s | %(message)s', datefmt='%H:%M:%S')
    
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    
    root_logger = logging.getLogger()
    if root_logger.hasHandlers():
        root_logger.handlers.clear()
    
    root_logger.addHandler(console_handler)
    
    # Уровень WARNING уберет все INFO сообщения из логов воркера
    root_logger.setLevel(logging.WARNING)

if __name__ == '__main__':
    app.start()
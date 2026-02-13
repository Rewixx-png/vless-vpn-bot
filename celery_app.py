import os
from celery import Celery
from config import config

# Инициализация Celery
# Broker - куда складывать задачи (Redis)
# Backend - где хранить результаты (Redis)
app = Celery(
    'vless_bot_worker',
    broker=config.REDIS_URL,
    backend=config.REDIS_URL,
    include=['tasks']  # Подключаем файл с задачами
)

# Настройки Celery
app.conf.update(
    timezone='Europe/Moscow',
    enable_utc=True,
    # Ограничиваем количество задач на один процесс воркера, чтобы освобождать память
    worker_max_tasks_per_child=100,
    # Сериализация
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
)

if __name__ == '__main__':
    app.start()
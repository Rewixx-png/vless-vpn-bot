# Настройки коллектора (сборщика конфигов)
COLLECTOR_SETTINGS = {
    "max_links_per_batch": 2000,   # ОЧЕНЬ СИЛЬНО УМЕНЬШЕНО (было 5000)
    "initial_workers": 5,          # Уменьшено
    "min_workers": 2,              # Уменьшено
    "max_workers": 10,             # Максимум 10 потоков внутри процесса
    "target_cpu": 60.0,            # Держим нагрузку низкой
    "check_timeout": 8,
    "fetch_timeout": 10,
    "batch_size_fetch": 3,
}

# Настройки чекера (проверяльщика работоспособности)
CHECKER_SETTINGS = {
    "max_concurrent": 15,   # Уменьшено с 20 (а было 80)
    "timeout": 8,
    "connect_timeout": 3,
    "workers": 2,           # Gunicorn workers
}

# Настройки Celery воркера (обработка задач)
WORKER_SETTINGS = {
    "concurrency": 2,              # Жесткий лимит
    "max_tasks_per_child": 25,     # Частый перезапуск для очистки RAM
    "prefetch_multiplier": 1,
}

# Расписание автоматических задач
BEAT_SCHEDULE = {
    "collector_interval": 1800,
}

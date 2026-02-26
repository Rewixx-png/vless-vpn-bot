# Настройки коллектора (сборщика конфигов)
COLLECTOR_SETTINGS = {
    "max_links_per_batch": 5000,   # Уменьшено с 40000 - меньше нагрузка
    "initial_workers": 10,          # Уменьшено с 20
    "min_workers": 4,                # Уменьшено с 8
    "max_workers": 20,              # Уменьшено с 60 - основная причина high CPU
    "target_cpu": 70.0,            # Снижено с 90% - оставить запас
    "check_timeout": 10,            # Уменьшено с 15
    "fetch_timeout": 15,            # Уменьшено с 20
    "batch_size_fetch": 5,          # Уменьшено с 9
}

# Настройки чекера (проверяльщика работоспособности)
CHECKER_SETTINGS = {
    "max_concurrent": 20,   # Уменьшено с 80 - основная причина высокой нагрузки
    "timeout": 8,           # Уменьшено с 10
    "connect_timeout": 3,  # Оставить как есть
    "workers": 4,           # Уменьшено с 8
}

# Настройки Celery воркера (обработка задач)
WORKER_SETTINGS = {
    "concurrency": 4,              # Уменьшено с 16 - слишком много
    "max_tasks_per_child": 100,    # Уменьшено с 500
    "prefetch_multiplier": 1,
}

# Расписание автоматических задач
BEAT_SCHEDULE = {
    "collector_interval": 1800,  # Увеличено до 30 минут (было 5 минут)
}

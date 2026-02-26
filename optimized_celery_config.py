import multiprocessing

# Базовые настройки
CPU_COUNT = multiprocessing.cpu_count()
WORKER_CONCURRENCY = min(CPU_COUNT * 4, 32)  # До 32 воркеров
PREFETCH_MULTIPLIER = 2

# Настройки Redis
REDIS_MAX_CONNECTIONS = 1000
REDIS_SOCKET_TIMEOUT = 10
REDIS_SOCKET_CONNECT_TIMEOUT = 5

# Настройки базы данных
DB_POOL_SIZE = 25
DB_MAX_OVERFLOW = 35
DB_POOL_RECYCLE = 1800  # 30 минут

# Настройки очередей
QUEUES = {
    'high_priority': {
        'concurrency': WORKER_CONCURRENCY // 2,
        'prefetch': 1
    },
    'medium_priority': {
        'concurrency': WORKER_CONCURRENCY // 3,
        'prefetch': 2
    },
    'low_priority': {
        'concurrency': WORKER_CONCURRENCY // 4,
        'prefetch': 4
    },
    'stability_check': {
        'concurrency': WORKER_CONCURRENCY // 2,
        'prefetch': 1
    }
}

# Настройки таймаутов
TASK_TIMEOUTS = {
    'short': 30,      # Быстрые задачи
    'medium': 60,     # Средние задачи
    'long': 300,      # Длительные задачи
    'collector': 600  # Сбор подписок
}

print(f"Оптимизированные настройки для {CPU_COUNT} ядер CPU:")
print(f"  • Worker concurrency: {WORKER_CONCURRENCY}")
print(f"  • Prefetch multiplier: {PREFETCH_MULTIPLIER}")
print(f"  • DB pool size: {DB_POOL_SIZE}")
print(f"  • DB max overflow: {DB_MAX_OVERFLOW}")
print(f"  • Redis max connections: {REDIS_MAX_CONNECTIONS}")

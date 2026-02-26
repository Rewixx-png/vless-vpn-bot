#!/bin/bash

# Оптимизированный запуск Celery воркеров

# Количество ядер CPU
CPU_CORES=$(nproc)
echo "Система имеет $CPU_CORES ядер CPU"

# Расчет количества воркеров
WORKER_COUNT=$((CPU_CORES * 4))
if [ $WORKER_COUNT -gt 32 ]; then
    WORKER_COUNT=32
fi

echo "Запуск $WORKER_COUNT воркеров..."

# Запуск Celery с оптимизированными настройками
celery -A celery_app:app worker \
    --loglevel=info \
    --concurrency=$WORKER_COUNT \
    --prefetch-multiplier=2 \
    --max-tasks-per-child=200 \
    --max-memory-per-child=300000 \
    --queues=high_priority,medium_priority,low_priority,stability_check,geoip_update \
    --hostname=vless_worker_%h \
    --pool=prefork \
    --autoscale=$WORKER_COUNT,$((WORKER_COUNT / 2)) \
    --without-gossip \
    --without-mingle \
    --without-heartbeat

#!/bin/bash

# Очистка
pm2 delete CheckerSVC 2>/dev/null
pm2 delete VPN_Worker 2>/dev/null
pm2 delete VPN_Bot 2>/dev/null

echo "♻️  Old processes cleaned."

# 1. Запускаем Микросервис Чекера (MAX POWER)
pm2 start utils/checker/service.py \
    --name "CheckerSVC" \
    --interpreter python3

echo "✅ Checker Service started."

# 2. Запускаем Celery Worker
# TURBO MAXIMUM: Concurrency 30
pm2 start "celery -A celery_app worker -Q high_priority,low_priority --loglevel=WARNING --concurrency=30" \
    --name "VPN_Worker"

echo "✅ Celery Worker started (Turbo Maximum)."

# 3. Запускаем Основного Бота
pm2 start bot.py \
    --name "VPN_Bot" \
    --interpreter python3

echo "✅ VPN Bot started."

# Сохраняем и выводим статус
pm2 save
sleep 2
pm2 list
pm2 logs --lines 10 --nostream
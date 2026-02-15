#!/bin/bash

# Очистка
pm2 delete CheckerSVC 2>/dev/null
pm2 delete VPN_Worker 2>/dev/null
pm2 delete VPN_Bot 2>/dev/null

echo "♻️  Old processes cleaned."

# Пауза для завершения процессов
sleep 2

# Настройки PM2 для стабильности
export PM2_HOME="/root/.pm2"
export PM2_PID_FILE_PATH="/root/.pm2/pm2.pid"

# 1. Запускаем Микросервис Чекера (MAX POWER)
pm2 start utils/checker/service.py --name "CheckerSVC" --interpreter python3

echo "✅ Checker Service started."

# 2. Запускаем Celery Worker
pm2 start "celery -A celery_app worker -Q high_priority,low_priority --loglevel=ERROR --concurrency=30 --max-tasks-per-child=500" --name "VPN_Worker"

echo "✅ Celery Worker started (Turbo Maximum)."

# 3. Запускаем Основного Бота
pm2 start bot.py --name "VPN_Bot" --interpreter python3

echo "✅ VPN Bot started."

# Сохраняем и выводим статус
pm2 save
sleep 3
pm2 list
pm2 logs --lines 5 --nostream
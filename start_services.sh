#!/bin/bash

GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${GREEN}🔄 Перезапуск VLESS VPN Bot (Safe Mode)...${NC}"

# 1. Остановка только наших сервисов
echo -e "${RED}🛑 Остановка процессов...${NC}"
pm2 delete CheckerSVC 2>/dev/null
pm2 delete VPN_Worker 2>/dev/null
pm2 delete VPN_Bot 2>/dev/null
pm2 delete VPN_Beat 2>/dev/null

# 2. Очистка временных файлов и кэшей
echo -e "🧹 Очистка временных файлов..."
rm -rf /tmp/xray_*.json
rm -f celerybeat-schedule

# 3. Принудительная очистка очереди задач (ВАЖНО ПРИ ПЕРЕГРУЗКЕ)
# Это удалит накопившиеся задачи, которые убивают сервер при старте
echo -e "${RED}🔥 Очистка очереди Celery (Purge)...${NC}"
python3 -m celery -A celery_app purge -f

# 4. Запуск сервисов с минимальными ресурсами
echo -e "${GREEN}🚀 Запуск Checker Service...${NC}"
pm2 start utils/checker/service.py --name CheckerSVC --interpreter python3 --max-memory-restart 300M

echo -e "${GREEN}🚀 Запуск Celery Worker (Concurrency: 2)...${NC}"
pm2 start celery_app.py --name VPN_Worker --interpreter python3 --max-memory-restart 500M

echo -e "${GREEN}🚀 Запуск Celery Beat (Scheduler)...${NC}"
pm2 start celery_app.py --name VPN_Beat --interpreter python3 -- beat

echo -e "${GREEN}🚀 Запуск Telegram Bot...${NC}"
pm2 start bot.py --name VPN_Bot --interpreter python3 --max-memory-restart 300M

echo -e "${GREEN}✅ Система перезапущена в безопасном режиме!${NC}"
pm2 list
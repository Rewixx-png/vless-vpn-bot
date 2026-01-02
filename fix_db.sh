#!/bin/bash
echo "🛠 Начинаем исправление базы данных..."

# Принудительно сбрасываем подключения и удаляем старое (если было)
sudo -u postgres psql -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = 'vless_bot_db';" > /dev/null 2>&1
sudo -u postgres psql -c "DROP DATABASE IF EXISTS vless_bot_db;"
sudo -u postgres psql -c "DROP USER IF EXISTS vless_bot;"

# Создаем заново с гарантированно правильным паролем
echo "👤 Создаем пользователя vless_bot..."
sudo -u postgres psql -c "CREATE USER vless_bot WITH PASSWORD 'VlessBotSecurePass2024!';"

# Создаем БД
echo "📦 Создаем базу vless_bot_db..."
sudo -u postgres psql -c "CREATE DATABASE vless_bot_db OWNER vless_bot;"
sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE vless_bot_db TO vless_bot;"

echo "✅ База данных пересоздана успешно."

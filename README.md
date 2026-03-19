# VLESS VPN Telegram Bot

Telegram-бот и набор сервисов для автоматической выдачи и управления VLESS/Reality подписками.
Проект ориентирован на продакшен-нагрузку: отдельный checker-сервис, очереди Celery, фоновая очистка и мониторинг.

## Что умеет

- Автоматически выдает подписки пользователям через Telegram.
- Поддерживает группы подписок и фильтры по странам/тегам.
- Проверяет прокси в фоне через отдельный сервис (`CheckerSVC`), не блокируя бота.
- Разделяет тяжелые задачи по очередям (`high_priority` / `low_priority`) через Celery.
- Ведет админ-инструменты: массовый импорт, статистика, рассылки и обслуживание базы.

## Архитектура в двух словах

- `VPN_Bot` (`bot.py`) - Telegram-бот на Aiogram.
- `CheckerSVC` (`utils/checker/service.py`) - микросервис проверки прокси.
- `VPN_Worker` + `VPN_Beat` (`celery_app.py`) - обработка и планирование фоновых задач.
- `SubscriptionServer` (`utils/sub_server.py`) - HTTP endpoint для ссылок подписки (по умолчанию порт `2082`).
- PostgreSQL - хранение пользователей, подписок, групп, источников.
- Redis - брокер и backend очередей Celery.

## Требования

- Ubuntu 20.04+ или Debian 11+
- Python 3.10+
- PostgreSQL
- Redis
- Xray-core
- Node.js/npm (для PM2)

## Быстрый старт

1) Установите системные зависимости:

```bash
sudo apt update
sudo apt install -y python3 python3-pip python3-venv postgresql redis-server git curl
```

2) Установите Xray-core:

```bash
bash -c "$(curl -L https://github.com/XTLS/Xray-install/raw/main/install-release.sh)" @ install
```

3) Клонируйте проект и установите Python-зависимости:

```bash
git clone https://github.com/your-username/vless-vpn-bot.git
cd vless-vpn-bot
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

4) Создайте `.env` в корне проекта:

```ini
BOT_TOKEN=123456:AA...
ADMIN_IDS=[12345678]
DB_URL=postgresql+asyncpg://user:pass@localhost/dbname
CRYPTO_BOT_TOKEN=1234:AA...

REDIS_URL=redis://localhost:6379/0
PUBLIC_IP=1.2.3.4
WEB_PORT=2082

CHECKER_PORT=8081
CHECKER_URL=http://127.0.0.1:8081

# Опционально
EXTERNAL_SUB_URL=
public_domain=
```

5) Первый запуск для инициализации таблиц:

```bash
python3 bot.py
```

После успешного старта остановите процесс `Ctrl+C`.

## Продакшен-запуск через PM2

Установите PM2:

```bash
sudo npm install -g pm2
```

Запустите все сервисы из `ecosystem.config.js`:

```bash
chmod +x start_services.sh
./start_services.sh
```

Скрипт запускает:

- `CheckerSVC`
- `VPN_Worker`
- `VPN_Worker_Low`
- `VPN_Beat`
- `VPN_Bot`

Полезные команды:

- `pm2 list` - статус процессов
- `pm2 logs` - агрегированные логи
- `pm2 restart VPN_Bot` - перезапуск бота
- `pm2 restart VPN_Worker` - перезапуск воркера
- `pm2 restart CheckerSVC` - перезапуск checker-сервиса

## Ручной запуск (для отладки)

В отдельных терминалах:

```bash
python3 utils/checker/service.py
python3 -m celery -A celery_app worker -Q high_priority,low_priority -c 1 --prefetch-multiplier=1
python3 -m celery -A celery_app beat
python3 bot.py
```

## Полезные URL

- Подписка пользователя: `http://<SERVER_IP>:2082/sub?id=<TELEGRAM_ID>`

## Структура проекта

- `bot.py` - точка входа бота
- `celery_app.py` - конфигурация Celery и расписания
- `handlers/` - роутеры и сценарии Telegram
- `database/` - модели, репозитории, инициализация БД
- `tasks/` - фоновые задачи Celery
- `utils/` - checker, генерация подписок, вспомогательные сервисы
- `MD/` - расширенная документация

## Документация

Основные документы находятся в `MD/`:

- `MD/README.md` - индекс документации
- `MD/ARCHITECTURE.md` - устройство системы
- `MD/API.md` - API и форматы подписок
- `MD/USER_COMMANDS.md` - команды для пользователей
- `MD/ADMIN_COMMANDS.md` - команды для админов
- `MD/TROUBLESHOOTING.md` - диагностика проблем

## Частые проблемы

- Не открывается ссылка подписки - проверьте firewall: `sudo ufw allow 2082/tcp`.
- Задачи Celery не выполняются - проверьте Redis (`redis-cli ping`) и `pm2 logs VPN_Worker`.
- Checker недоступен - проверьте `CHECKER_PORT`, `CHECKER_URL` и статус `CheckerSVC`.

## Безопасность

- Не коммитьте `.env` и токены.
- Ограничьте доступ к порту `2082` (подписки) через firewall/reverse proxy.
- Для продакшена рекомендуется поставить Nginx/Caddy перед публичными endpoint.

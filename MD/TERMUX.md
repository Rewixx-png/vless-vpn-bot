# Termux запуск (Lite)

Документ описывает запуск этой копии проекта на Android через Termux.

## Что изменено для Termux

- База по умолчанию: `SQLite` (`DB_URL=sqlite+aiosqlite:///./storage/vless.db`).
- Убрана жесткая привязка к Postgres-only upsert в репозиториях.
- Checker ищет бинарник `xray` через `XRAY_BIN` и `PATH`, а не только `/usr/local/bin/xray`.
- Добавлены скрипты управления сервисами: `termux/setup.sh`, `termux/start.sh`, `termux/stop.sh`, `termux/status.sh`.
- Для установки зависимостей добавлен `requirements-termux.txt`.

## Быстрый старт

```bash
bash termux/setup.sh
cp .env.termux.example .env
nano .env
bash termux/start.sh
bash termux/status.sh
```

## Минимальный `.env`

```ini
BOT_TOKEN=123456:AA...
ADMIN_IDS=[12345678]
DB_URL=sqlite+aiosqlite:///./storage/vless.db
REDIS_URL=redis://127.0.0.1:6379/0
CHECKER_URL=http://127.0.0.1:8081
```

`CRYPTO_BOT_TOKEN` можно оставить пустым - донаты через CryptoPay будут отключены.

## Управление сервисами

- Запуск: `bash termux/start.sh`
- Статус: `bash termux/status.sh`
- Остановка: `bash termux/stop.sh`

Логи:

- `.termux/logs/bot.log`
- `.termux/logs/worker.log`
- `.termux/logs/beat.log`
- `.termux/logs/checker.log`
- `.termux/logs/redis.log`

## Примечания

- Для полной работы checker нужен `xray` в PATH или в `XRAY_BIN`.
- В Lite-профиле backup-задача для Postgres автоматически пропускается.
- Если SQLite начинает блокироваться под высокой нагрузкой, уменьшите параллелизм Celery (в start-скрипте уже стоит `-c 1`).

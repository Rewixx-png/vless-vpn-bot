# Архитектура VLESS VPN Bot

## Общая схема

```text
Telegram users
    |
    v
VPN_Bot (Aiogram, polling)
    |\
    | +--> SubscriptionServer (HTTP :2082, /sub)
    |
    +--> PostgreSQL (users, groups, subscriptions, config)
    |
    +--> Redis (Celery broker/backend)
            |
            +--> VPN_Worker (queues: high_priority, low_priority)
            +--> VPN_Beat (periodic tasks)

CheckerSVC (HTTP :8081) <--- bot/worker отправляют проверки прокси
```

## Ключевые процессы

### `VPN_Bot` (`bot.py`)

- Точка входа Telegram-бота.
- Инициализирует БД и роутеры (`handlers/user`, `handlers/admin`).
- Запускает фоновые процессы и `SubscriptionServer`.
- Отправляет админам уведомления об ошибках и статусе старта.

### `SubscriptionServer` (`utils/sub_server.py`)

- Отдает подписки по HTTP.
- Базовый endpoint: `/sub?id=<telegram_id>`.
- Порт берется из `WEB_PORT` (по умолчанию `2082`).

### `CheckerSVC` (`utils/checker/service.py`)

- Изолированный сервис проверки прокси.
- Выполняет сетевые проверки и определяет качество/регион.
- Обычно работает локально на `127.0.0.1:8081`.

### `Celery` (`celery_app.py`, `tasks/`)

- `VPN_Worker` обрабатывает фоновые задачи в очередях:
  - `high_priority`: критичные проверки и админские действия.
  - `low_priority`: коллектор, стабильность, GeoIP.
- `VPN_Beat` планирует периодические задачи.

Текущие periodic-задачи:

- `run_collector_task` - каждые 30 минут.
- `check_stability_task` - каждые 30 минут.
- `update_geoip_task` - раз в 30 дней.

## Данные и репозитории

- Модели и engine: `database/core.py`, `database/models.py`.
- Репозитории доступа к данным: `database/repo/`.
- Основные сущности: пользователи, группы, подписки, источники, системные настройки.

## Поток запроса пользователя

```text
Telegram update -> Aiogram router -> handler
handler -> repo/service -> DB и/или CheckerSVC
handler -> ответ пользователю (message/edit)
```

## Основные конфиги (`config.py`)

- `BOT_TOKEN`, `ADMIN_IDS` - доступ к Telegram и админке.
- `DB_URL` - подключение к PostgreSQL.
- `REDIS_URL` - брокер/результаты Celery.
- `PUBLIC_IP`, `WEB_PORT` - генерация и выдача ссылок подписки.
- `CHECKER_PORT`, `CHECKER_URL` - интеграция с checker-сервисом.
- `EXTERNAL_SUB_URL`, `public_domain` - опциональные публичные настройки.

## Почему такая архитектура

- Разделение checker и бота снижает блокировки event loop.
- Очереди Celery изолируют тяжелые операции от пользовательских запросов.
- PM2-оркестрация упрощает перезапуск и мониторинг отдельных процессов.

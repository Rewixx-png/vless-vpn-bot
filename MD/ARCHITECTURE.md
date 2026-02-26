# Архитектура VLESS VPN Bot

## Общая схема

```
┌─────────────────────────────────────────────────────────────────────────┐
│                            Telegram Users                                │
└─────────────────────────────────┬───────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                        Telegram Bot (bot.py)                           │
│                  Aiogram 3.x + FSM (States)                            │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  │
│  │  Handlers   │  │  Keyboards  │  │   Repos     │  │  Services   │  │
│  │  /user/     │  │  /user/     │  │  /repo/     │  │  /utils/    │  │
│  │  /admin/    │  │  /admin/    │  │             │  │             │  │
│  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘  │
└────────────────────────────┬────────────────────────────────────────────┘
                             │
         ┌───────────────────┼───────────────────┐
         │                   │                   │
         ▼                   ▼                   ▼
┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐
│  PostgreSQL     │  │  Redis          │  │  Web Server    │
│  (database/)    │  │  (Celery)       │  │  (sub_server)  │
│                 │  │                 │  │  Port: 2082    │
│  - users        │  │  - Queue        │  │  /sub?id=xxx   │
│  - subs         │  │  - Cache        │  │                │
│  - groups       │  │                 │  │                │
└─────────────────┘  └─────────────────┘  └─────────────────┘
         │                   │                   │
         │                   │                   │
         ▼                   ▼                   ▼
┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐
│  Celery Worker │  │  Checker SVC   │  │  VPN Clients   │
│  (tasks.py)    │  │  Port: 8081    │  │  v2rayNG       │
│                 │  │  Proxy Check   │  │  FlClash       │
│  - collector   │  │                 │  │  Clash         │
│  - stability   │  │                 │  │                │
└─────────────────┘  └─────────────────┘  └─────────────────┘
```

## Компоненты системы

### 1. Telegram Bot (`bot.py`)
Основной процесс бота, обрабатывающий команды пользователей.

**Функции:**
- Инициализация БД при старте
- Регистрация роутеров (user/admin)
- Запуск фоновых задач (BackgroundTasks)
- Подписка на обновления (polling)
- Уведомление админов об ошибках

**Запуск:**
```bash
pm2 start bot.py --name VPN_Bot
```

### 2. Subscription Server (`utils/sub_server.py`)
Веб-сервер для раздачи подписок по URL.

**Параметры:**
- Порт: `config.WEB_PORT` (по умолчанию 2082)
- Эндпоинт: `/sub?id={user_id}`

**Поддерживаемые форматы:**
- `vless://` - plain text (по умолчанию)
- `?format=clash` - Clash YAML
- `?format=base64` - Base64 encoded

### 3. Checker Microservice (`utils/checker/service.py`)
Отдельный легковесный сервис для проверки прокси.

**Функции:**
- HTTP ping
- HTTPS handshake проверка
- Определение страны (GeoIP)
- AI/ChatGPT доступность

**Порт:** 8081 (локально)

### 4. Celery Worker (`celery_app.py`, `tasks.py`)
Очередь задач для фоновой обработки.

**Задачи:**
- `run_collector_task` - сбор прокси из интернета (каждые 10 мин)
- `check_stability_task` - проверка стабильности серверов (каждые 10 мин)

### 5. Background Tasks (`utils/background.py`)
Python asyncio scheduler для запуска Celery задач.

---

## База данных (PostgreSQL)

### Таблицы

#### `users`
| Поле | Тип | Описание |
|------|-----|----------|
| id | BigInteger | Telegram ID пользователя |
| username | String | Username (nullable) |
| country_filter | Text | Фильтр стран через запятую |
| tags_filter | Text | Фильтр тегов (stable,ai,fast,wl) |
| subscription_limit | Integer | Лимит серверов в подписке |
| created_at | DateTime | Дата регистрации |

#### `subscriptions`
| Поле | Тип | Описание |
|------|-----|----------|
| id | Integer | ID записи |
| vless_key | Text | Полная VLESS ссылка |
| region | String | Страна/регион |
| latency_ms | Integer | Пинг в миллисекундах |
| ai_available | Boolean | Доступен ли для AI |
| is_active | Boolean | Активен/отключен |
| death_count | Integer | Количество "смертей" |
| stability_streak | Integer | Непрерывная работа |

#### `user_groups`
| Поле | Тип | Описание |
|------|-----|----------|
| id | Integer | ID группы |
| user_id | BigInteger | Владелец |
| name | String | Название группы |
| country_filter | Text | Фильтр стран |
| tags_filter | Text | Фильтр тегов |

#### `system_config`
| Поле | Тип | Описание |
|------|-----|----------|
| key | String | Ключ настройки |
| value | Text | Значение |

---

## Обработка сообщений (Flow)

```
User sends callback
        │
        ▼
┌───────────────────┐
│  Router (aiogram) │
│  определяет хендлер│
└────────┬──────────┘
         │
         ▼
┌───────────────────┐
│  Handler Function │
│  (handlers/user/) │
└────────┬──────────┘
         │
    ┌────┴────┐
    │         │
    ▼         ▼
┌───────┐ ┌────────┐
│  DB   │ │  API   │
│ Repo  │ │External│
└───┬───┘ └───┬────┘
    │         │
    └────┬────┘
         │
         ▼
┌───────────────────┐
│ edit_or_answer()  │
│ (handlers/start)  │
└────────┬──────────┘
         │
    ┌────┴────┐
    │         │
    ▼         ▼
┌─────────┐ ┌──────────┐
│ Edit    │ │ Send New │
│ Message │ │  Message │
└─────────┘ └──────────┘
```

---

## Конфигурация (config.py)

| Параметр | Тип | Описание |
|----------|-----|----------|
| BOT_TOKEN | SecretStr | Telegram Bot Token |
| ADMIN_IDS | List[int] | Список ID админов |
| DB_URL | str | PostgreSQL connection string |
| CRYPTO_BOT_TOKEN | SecretStr | CryptoBot API Token |
| REDIS_URL | str | Redis connection string |
| PUBLIC_IP | str | Публичный IP сервера |
| WEB_PORT | int | Порт подписочного сервера |
| CHECKER_PORT | int | Порт чекера |
| public_domain | str | Домен для HTTPS ссылок |
| EXTERNAL_SUB_URL | str | Внешняя подписка для микса |

---

## Теги серверов

| Тег | Описание | Фильтр |
|-----|----------|--------|
| `stable` | Серверы с аптаймом 24ч+ | 🛡 Stable |
| `ai` | Доступ к ChatGPT/Gemini | AI Ready |
| `fast` | Пинг < 100ms | Low Latency |
| `wl` | Reality/Vision | Reality / Vision |

---

## Зависимости (основные)

- `aiogram` - Telegram Bot API
- `sqlalchemy` + `asyncpg` - База данных
- `celery` - Очередь задач
- `redis` - Брокер сообщений
- `aiohttp` - Асинхронные HTTP запросы
- `psycopg2-binary` - PostgreSQL драйвер
- `pydantic` - Валидация конфигурации
- `python-dotenv` - Переменные окружения

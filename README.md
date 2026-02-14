# 🚀 VLESS VPN Telegram Bot (High Performance Edition)

Профессиональный Telegram бот для автоматической продажи, выдачи и управления VLESS/Reality конфигурациями.
Построен на микросервисной архитектуре для работы под высокой нагрузкой (10k+ подписок).

---

## ✨ Ключевые возможности

### ⚡️ High-Performance Architecture
*   **Микросервисы:** Проверка прокси вынесена в отдельный легковесный сервис (`CheckerSVC`), который не блокирует основного бота.
*   **Очереди задач (Celery):** Разделение на `High Priority` (проверка пользовательских подписок) и `Low Priority` (сбор мусора из интернета).
*   **Turbo Mode:** Поддержка 50+ одновременных процессов Xray и 100+ HTTP-воркеров.
*   **Smart Cleanup:** Автоматическое удаление "мертвых" серверов и удержание ТОП-100 лучших по пингу для каждой страны.

### 👤 Для Пользователей
*   **Гибкие подписки:**
    *   **Группы:** Возможность создавать отдельные ссылки (например, "Для работы", "Только Германия").
    *   **Фильтры:** Настройка стран и тегов (AI, Fast, Reality) для каждой группы.
*   **AI Ready:** Специальный фильтр для ChatGPT и Google Gemini (строгая проверка доступа к API).
*   **Клиенты:** Ссылки адаптированы для v2rayNG, Streisand, NekoBox, Hiddify, FlClash (поддержка `clash.yaml`).

### 🛠 Для Администратора
*   **Массовый импорт:** Загрузка `.txt` файлов с тысячами ключей.
*   **Deep Check:** Двухуровневая проверка качества:
    1.  Быстрый HTTP Ping.
    2.  Строгий HTTPS Handshake (отсеивает прокси с перехватом SSL).
*   **GeoIP:** Автоматическое определение страны и флага.
*   **Рассылка:** Отправка сообщений всем пользователям.
*   **Статистика:** Детальный отчет по регионам и нагрузке.

---

## ⚙️ Требования

*   **OS:** Ubuntu 20.04+ / Debian 11+
*   **Python:** 3.10+
*   **Database:** PostgreSQL
*   **Broker:** Redis (для очередей задач)
*   **Core:** Xray-core (бинарный файл)

---

## 🚀 Установка

### 1. Подготовка системы
Установите необходимые пакеты:
```bash
sudo apt update
sudo apt install -y python3 python3-pip python3-venv postgresql redis-server git unzip curl
```

Установите **Xray Core**:
```bash
bash -c "$(curl -L https://github.com/XTLS/Xray-install/raw/main/install-release.sh)" @ install
```

### 2. Клонирование и зависимости
```bash
git clone https://github.com/your-username/vless-vpn-bot.git
cd vless-vpn-bot

# Создание виртуального окружения (рекомендуется)
python3 -m venv venv
source venv/bin/activate

# Установка библиотек
pip install -r requirements.txt
```

### 3. Настройка окружения
Создайте файл `.env` на основе примера:
```ini
BOT_TOKEN=123456:AAH...
ADMIN_IDS=[12345678]
DB_URL=postgresql+asyncpg://user:pass@localhost/dbname
CRYPTO_BOT_TOKEN=1234:AA...
REDIS_URL=redis://localhost:6379/0

# Публичный IP вашего сервера (для ссылок подписки)
PUBLIC_IP=1.2.3.4
# Порт микросервиса чекера (не менять, если не знаете зачем)
CHECKER_PORT=8081
CHECKER_URL=http://127.0.0.1:8081
```

### 4. Инициализация БД
При первом запуске бот сам создаст таблицы. Просто запустите его один раз вручную:
```bash
python3 bot.py
# После успешного старта нажмите Ctrl+C
```

---

## 🔥 Запуск в Production (PM2)

Проект использует скрипт `start_services.sh` для правильного запуска всех микросервисов в нужном порядке.

1.  **Установите PM2:**
    ```bash
    sudo npm install -g pm2
    ```

2.  **Запустите проект:**
    ```bash
    chmod +x start_services.sh
    ./start_services.sh
    ```

Скрипт автоматически:
1.  Очистит старые процессы.
2.  Запустит **Checker Microservice** (порт 8081).
3.  Запустит **Celery Worker** (с concurrency=30).
4.  Запустит **Telegram Bot**.

### Управление
*   `pm2 list` — статус сервисов.
*   `pm2 logs` — просмотр логов.
*   `pm2 restart VPN_Bot` — перезагрузка только бота.
*   `pm2 restart VPN_Worker` — перезагрузка воркера обработки задач.

---

## 🧩 Структура проекта

*   `bot.py` — Точка входа Telegram бота.
*   `celery_app.py` — Конфигурация Celery и очередей.
*   `utils/checker/service.py` — **Микросервис** проверки прокси (aiohttp).
*   `utils/sub_server.py` — Веб-сервер для отдачи подписок (порт 2082).
*   `database/` — Модели и репозитории (SQLAlchemy).
*   `handlers/` — Логика бота (Aiogram routers).

---

## ⚠️ Важно
Для корректной работы ссылок подписки убедитесь, что порт `2082` (или тот, который вы указали в конфиге) открыт в Firewall:
```bash
sudo ufw allow 2082/tcp
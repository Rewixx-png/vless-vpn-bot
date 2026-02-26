# VLESS VPN Bot - Документация

Добро пожаловать в документацию VLESS VPN Bot!

## 📚 Содержание

### Основное
- [ARCHITECTURE.md](ARCHITECTURE.md) - Архитектура системы
- [API.md](API.md) - API endpoints и интеграции
- [TROUBLESHOOTING.md](TROUBLESHOOTING.md) - Устранение неполадок

### Использование
- [USER_COMMANDS.md](USER_COMMANDS.md) - Команды для пользователей
- [ADMIN_COMMANDS.md](ADMIN_COMMANDS.md) - Команды для админов

---

## Быстрый старт

### 1. Запуск сервисов
```bash
pm2 start bot.py --name VPN_Bot
pm2 start utils/checker/service.py --name CheckerSVC
pm2 start celery_app.py --name VPN_Worker
```

### 2. Проверка статуса
```bash
pm2 list
```

### 3. Получить подписку
```
http://IP:2082/sub?id=TELEGRAM_ID
```

---

## Возможности

- ✅ Автоматическая выдача VLESS подписок
- ✅ Фильтрация по странам и тегам
- ✅ Множественные профили
- ✅ AI/ChatGPT фильтр
- ✅ Проверка серверов (ping, latency)
- ✅ Админ-панель
- ✅ Донат через CryptoBot

---

## Поддержка

При проблемах смотрите [TROUBLESHOOTING.md](TROUBLESHOOTING.md)

# Устранение неполадок

## Частые проблемы

### Бот не запускается

**Ошибка: `ModuleNotFoundError`**
```bash
pip install -r requirements.txt
```

**Ошибка: `Database connection failed`**
```bash
# Проверьте PostgreSQL
sudo systemctl status postgresql

# Проверьте DB_URL в .env
cat .env | grep DB_URL
```

**Ошибка: `Circular import`**
```bash
# Проверьте импорты в handlers/user/router.py
# Убедитесь что нет циклических зависимостей
```

---

### Ошибки подписки

**Пустая подписка**
- Проверьте что в БД есть сервера: `SELECT COUNT(*) FROM subscriptions`
- Проверьте что порт 2082 открыт: `sudo ufw status`

**Ошибка: `Bad Request`**
- Проверьте формат ссылок в БД
- Проверьте что UUID валидный

---

### Проблемы сChecker

**Checker Service Offline**
```bash
# Проверьте запущен ли checker
pm2 list | grep Checker

# Перезапустите
pm2 restart CheckerSVC

# Проверьте логи
pm2 logs CheckerSVC
```

---

### Проблемы с Celery

**Задачи не выполняются**
```bash
# Проверьте Redis
sudo systemctl status redis

# Проверьте воркера
pm2 list | grep Worker

# Перезапустите
pm2 restart VPN_Worker
```

---

## Логи

### Основные логи
```bash
# Логи бота
pm2 logs VPN_Bot

# Логи checker
pm2 logs CheckerSVC

# Логи воркера
pm2 logs VPN_Worker
```

### Уровни логирования
```python
# Изменить уровень в bot.py
logging.basicConfig(level=logging.DEBUG)
```

---

## Диагностика

### Проверка БД
```bash
# Подключиться к PostgreSQL
psql -U user -d dbname

# Проверить таблицы
\d users
\d subscriptions

# Количество серверов
SELECT COUNT(*) FROM subscriptions WHERE is_active = true;
```

### Проверка сети
```bash
# Проверить порт подписки
curl http://localhost:2082/sub?id=1

# Проверить checker
curl -X POST http://127.0.0.1:8081/check \
  -H "Content-Type: application/json" \
  -d '{"config":"vless://test@localhost:443"}'
```

---

## Скорая помощь

### Полный перезапуск
```bash
pm2 delete all
./start_services.sh
```

### Очистка и перезапуск
```bash
# Остановить все
pm2 delete all

# Очистить логи
pm2 logs --empty

# Запустить заново
./start_services.sh
```

### Backup БД
```bash
pg_dump -U user dbname > backup_$(date +%Y%m%d).sql
```

### Восстановление БД
```bash
psql -U user dbname < backup_20240101.sql
```

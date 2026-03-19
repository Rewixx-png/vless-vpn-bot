# Устранение неполадок

Короткие сценарии диагностики для продакшен-инстанса.

## 0) Быстрый чек за 60 секунд

```bash
pm2 list
redis-cli ping
curl -sS http://127.0.0.1:2082/sub?id=1
```

Если `pm2 list` показывает `errored/stopped`, сначала перезапустите проблемный процесс и проверьте его логи.

## 1) Бот не запускается

### `ModuleNotFoundError`

```bash
source venv/bin/activate
pip install -r requirements.txt
```

### Ошибка подключения к БД

```bash
sudo systemctl status postgresql
python3 - <<'PY'
from config import config
print(config.DB_URL)
PY
```

Проверьте, что в `DB_URL` корректные логин/пароль/хост/база.

### Бот падает сразу после старта

```bash
pm2 logs VPN_Bot --lines 200
```

Чаще всего причина: неверный `BOT_TOKEN`, недоступный Redis/БД, или ошибка импорта.

## 2) Подписка пустая или не открывается

Проверьте:

- открыт ли порт `2082` (`sudo ufw status`),
- есть ли активные подписки в БД,
- корректен ли `PUBLIC_IP`/`public_domain` в конфиге.

Быстрый тест:

```bash
curl -v "http://127.0.0.1:2082/sub?id=<TELEGRAM_ID>"
```

## 3) Checker недоступен

Симптомы: массовые ошибки проверки, в боте статус checker = `OFFLINE`.

```bash
pm2 restart CheckerSVC
pm2 logs CheckerSVC --lines 200
curl -sS -X POST http://127.0.0.1:8081/check -H "Content-Type: application/json" -d '{"config":"vless://test@localhost:443?security=none"}'
```

Если checker работает только локально - убедитесь, что `CHECKER_URL=http://127.0.0.1:8081`.

## 4) Celery-задачи не выполняются

```bash
redis-cli ping
pm2 restart VPN_Worker
pm2 restart VPN_Beat
pm2 logs VPN_Worker --lines 200
pm2 logs VPN_Beat --lines 200
```

Проверьте, что запущены оба процесса: `VPN_Worker` и `VPN_Beat`.

## 5) Полезные логи

```bash
pm2 logs VPN_Bot --lines 300
pm2 logs VPN_Worker --lines 300
pm2 logs VPN_Beat --lines 300
pm2 logs CheckerSVC --lines 300
```

## 6) Безопасный перезапуск всех сервисов

```bash
./start_services.sh
pm2 list
```

Если нужно полностью переинициализировать PM2-процессы:

```bash
pm2 delete all
./start_services.sh
```

## 7) Резервная копия БД

```bash
pg_dump -U <db_user> <db_name> > backup_$(date +%Y%m%d).sql
```

Восстановление:

```bash
psql -U <db_user> <db_name> < backup_YYYYMMDD.sql
```

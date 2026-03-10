# API и endpoints

Документ описывает три HTTP-контрагента проекта:

- подписочный сервер (`utils/sub_server.py`),
- checker-сервис (`utils/checker/service.py`),
- Admin API (`api/main.py`).

## 1) Subscription Server

### `GET /sub`

Выдает подписку для пользователя Telegram.

Пример:

```text
http://<SERVER_IP>:2082/sub?id=<TELEGRAM_ID>
```

Параметры запроса:

| Параметр | Тип | Описание |
|---|---|---|
| `id` | int | Telegram ID пользователя |
| `format` | string | Формат выдачи (например, `clash`, `base64`, `raw`) |

Примеры:

```bash
# Базовая выдача
curl "http://127.0.0.1:2082/sub?id=123456789"

# Для Clash-совместимого клиента
curl "http://127.0.0.1:2082/sub?id=123456789&format=clash"
```

Примечания:

- Если пользователь не найден или нет доступных серверов, endpoint может вернуть пустой/ограниченный ответ.
- Для продакшена рекомендуется reverse proxy (Nginx/Caddy) и ограничение публичного доступа.

## 2) Checker Service (внутренний)

### `POST /check`

Проверяет один прокси-конфиг.

URL по умолчанию:

```text
http://127.0.0.1:8081/check
```

Тело запроса:

```json
{
  "config": "vless://..."
}
```

Типичный ответ:

```json
{
  "success": true,
  "region": "Germany",
  "latency": 45,
  "ai": true,
  "error": "OK"
}
```

## 3) Admin API

Base URL (по умолчанию):

```text
http://<SERVER_IP>:3000/api
```

Основные endpoints:

| Метод | Путь | Назначение |
|---|---|---|
| `GET` | `/health` | Быстрый health-check (CPU/Memory/Uptime) |
| `GET` | `/stats` | Системная статистика подписок |
| `GET` | `/subs` | Список подписок с фильтрами/пагинацией |
| `DELETE` | `/subs/{sub_id}` | Удаление подписки |
| `POST` | `/subs/cleanup` | Очистка «мертвых» подписок |
| `GET` | `/sources` | Список источников |
| `POST` | `/sources` | Добавление источника |
| `PUT` | `/sources/{source_id}` | Вкл/выкл источника |
| `DELETE` | `/sources/{source_id}` | Удаление источника |
| `GET` | `/users` | Список пользователей |
| `GET` | `/groups` | Список групп |
| `GET` | `/system` | Статусы PM2/Redis/DB |
| `POST` | `/system/restart/{service}` | Перезапуск сервиса через PM2 |
| `POST` | `/tasks/run-collector` | Принудительный запуск collector-задачи |
| `POST` | `/tasks/run-stability` | Принудительный запуск stability-задачи |

Примеры:

```bash
curl "http://127.0.0.1:3000/api/health"
curl "http://127.0.0.1:3000/api/subs?page=1&per_page=20&is_active=true"
curl -X POST "http://127.0.0.1:3000/api/tasks/run-collector"
```

## Модель VLESS-ссылки (кратко)

```text
vless://UUID@HOST:PORT?encryption=none&security=reality&sni=example.com&type=tcp#NAME
```

Ключевые параметры:

- `security` - режим безопасности (`tls`/`reality`).
- `sni` - SNI домен.
- `type` - транспорт (`tcp`, `ws`, `grpc`).
- `flow` - вариант flow для XTLS/Reality (если используется).

## Безопасность API

- Не публикуйте checker-порт (`8081`) наружу.
- Ограничьте доступ к Admin API (`3000`) по IP или через auth на reverse proxy.
- Не передавайте токены и внутренние URL в публичные клиентские конфиги.

# Справочник API VLESS VPN Bot

## Endpoint подписки

### GET /sub

Основной endpoint для получения конфигураций подписки.

**URL:**
```
http://YOUR_SERVER:2082/sub?id={user_id}
```

**Параметры:**

| Параметр | Тип | Описание |
|----------|-----|----------|
| `id` | int | Telegram ID пользователя |
| `format` | string | Формат: `clash`, `yaml`, `base64`, `raw` |
| `types` | string | Типы протоколов через запятую: `vless,vmess,trojan` |

**Примеры:**

```bash
# Базовая ссылка (plain text)
http://108.165.164.160:2082/sub?id=123456789

# С группой
http://108.165.164.160:2082/sub?id=123456789/Work

# Clash формат
http://108.165.164.160:2082/sub?id=123456789&format=clash

# Только VLESS
http://108.165.164.160:2082/sub?id=123456789&types=vless
```

**User-Agent Определение:**
- `clash`, `flclash`, `stash`, `meta`, `verge` → Clash YAML
- `v2raytun` → Raw text
- `happ` → Raw text

---

## Checker API (внутренний)

### POST /check

Проверка одного прокси.

**URL:**
```
http://127.0.0.1:8081/check
```

**Тело запроса:**
```json
{
  "config": "vless://..."
}
```

**Ответ:**
```json
{
  "success": true,
  "region": "🇩🇪 Germany",
  "latency": 45,
  "ai": true,
  "error": "OK"
}
```

---

## База данных

### Async Session Factory

```python
from database.core import async_session_factory

async with async_session_factory() as session:
    # работа с БД
    await session.commit()
```

### Пример запроса

```python
from database.repo import UserRepo, SubRepo

# Получить пользователя
user = await UserRepo.get_user(telegram_id)

# Получить подписки
subs = await SubRepo.get_smart_keys(
    regions=["DE", "US"],
    tags=["ai", "fast"],
    limit=10
)
```

---

## Структура VLESS ссылки

```
vless://UUID@HOST:PORT?encryption=none&flow=xtls-rprx-vision&security=reality&sni=SNI&fp=random&type=tcp#NAME
```

**Параметры:**
- `encryption` - шифрование (обычно `none`)
- `flow` - поток (`xtls-rprx-vision`, `xtls-rprx`, `none`)
- `security` - безопасность (`tls`, `reality`)
- `sni` - Server Name Indication
- `fp` - отпечаток (`random`, `chrome`, `firefox`)
- `type` - тип транспорта (`tcp`, `grpc`, `ws`)

---

## Клиенты и совместимость

| Клиент | Формат | Особенности |
|--------|--------|-------------|
| v2rayNG | vless:// | Требует `AllowInsecure` для HTTP |
| FlClash | vless:// | Рекомендуется |
| Streisand | vless:// | |
| NekoBox | vless:// | |
| Hiddify | vless:// | |
| Clash | clash:// | Требует `?format=clash` |
| V2RayTun | raw | Автоопределение по UA |

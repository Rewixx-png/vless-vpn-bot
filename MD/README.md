# Документация VLESS VPN Bot

Этот раздел содержит практичные документы для запуска, эксплуатации и поддержки проекта.

## Карта документации

- [ARCHITECTURE.md](ARCHITECTURE.md) - компоненты, потоки данных, сервисы и зависимости.
- [API.md](API.md) - HTTP endpoints подписочного сервера и checker.
- [USER_COMMANDS.md](USER_COMMANDS.md) - пользовательские сценарии в Telegram-боте.
- [ADMIN_COMMANDS.md](ADMIN_COMMANDS.md) - функции админ-панели и операционные действия.
- [TERMUX.md](TERMUX.md) - запуск и сопровождение Lite-профиля на Android.
- [TROUBLESHOOTING.md](TROUBLESHOOTING.md) - диагностика и быстрые восстановительные шаги.

## С чего начать

- Если разворачиваете проект с нуля - начните с корневого `README.md`.
- Если нужно понять устройство системы - откройте `ARCHITECTURE.md`.
- Если интегрируете внешние сервисы - откройте `API.md`.
- Если проблема уже в проде - сразу в `TROUBLESHOOTING.md`.

## Быстрые команды для эксплуатации

```bash
pm2 list
pm2 logs VPN_Bot --lines 100
pm2 logs VPN_Worker --lines 100
pm2 logs CheckerSVC --lines 100
```

## Полезные ссылки

- Подписка пользователя: `http://<SERVER_IP>:2082/sub?id=<TELEGRAM_ID>`

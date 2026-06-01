import asyncio
import uuid
from typing import Any, Dict, cast

import redis.asyncio as redis
from aiogram import Bot
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.enums import ChatAction
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramRetryAfter

from celery_app import app
from config import config
from database.repo import UserRepo
from tasks.base import OptimizedTask, setup_loop_exception_handler_async, setup_log_rotation
from utils.reporter import Reporter


USER_PROBE_LOCK_KEY = "lock:tasks:user_probe"
USER_PROBE_LOCK_TTL_SEC = 7200
USER_PROBE_SLEEP_SEC = 0.05
USER_PROBE_BUFFER_SIZE = 50

_BLOCKED_MARKERS = (
    "bot was blocked by the user",
    "user is deactivated",
    "chat not found",
    "user not found",
)


async def _acquire_probe_lock() -> tuple[redis.Redis | None, str | None]:
    client = None
    try:
        client = redis.from_url(config.REDIS_URL, decode_responses=True)
        token = uuid.uuid4().hex
        acquired = await client.set(
            USER_PROBE_LOCK_KEY,
            token,
            ex=USER_PROBE_LOCK_TTL_SEC,
            nx=True,
        )
        if acquired:
            return client, token
    except Exception:
        pass

    if client is not None:
        try:
            await client.close()
        except Exception:
            pass
    return None, None


async def _release_probe_lock(client: redis.Redis | None, token: str | None) -> None:
    if client is None or token is None:
        return

    try:
        await cast(Any, client).eval(
            "if redis.call('get', KEYS[1]) == ARGV[1] then "
            "return redis.call('del', KEYS[1]) else return 0 end",
            1,
            USER_PROBE_LOCK_KEY,
            token,
        )
    except Exception:
        pass
    finally:
        try:
            await client.close()
        except Exception:
            pass


def _is_blocked_bad_request(error: TelegramBadRequest) -> bool:
    text = str(error or "").lower()
    return any(marker in text for marker in _BLOCKED_MARKERS)


@app.task(
    name="tasks.probe_blocked_users_task",
    base=OptimizedTask,
    time_limit=3600,
    soft_time_limit=3540,
)
async def probe_blocked_users_task() -> Dict[str, Any]:
    setup_log_rotation()
    await setup_loop_exception_handler_async()

    bot = Bot(token=config.BOT_TOKEN.get_secret_value(), session=AiohttpSession())
    lock_client = None
    lock_token = None

    checked = 0
    ok_count = 0
    blocked_count = 0
    removed_count = 0
    retry_after_count = 0
    bad_request_count = 0
    error_count = 0
    blocked_buffer: list[int] = []

    async def flush_blocked() -> None:
        nonlocal removed_count, blocked_buffer
        if not blocked_buffer:
            return
        to_delete = blocked_buffer
        blocked_buffer = []
        removed_count += await UserRepo.delete_users(to_delete)

    try:
        lock_client, lock_token = await _acquire_probe_lock()
        if lock_client is None:
            await Reporter.send_system_log(
                bot,
                "🧹 <b>User Probe</b>\nПропуск запуска: предыдущая задача еще активна.",
            )
            return {"status": "skipped", "reason": "already_running"}

        users = await UserRepo.get_all_users()
        user_ids = [int(user.id) for user in users if getattr(user, "id", None)]
        total = len(user_ids)

        if total == 0:
            await Reporter.send_system_log(
                bot,
                "🧹 <b>User Probe</b>\nПроверка пропущена: пользователей в базе нет.",
            )
            return {"checked": 0, "removed": 0, "blocked": 0}

        for user_id in user_ids:
            checked += 1
            try:
                await asyncio.wait_for(
                    bot.send_chat_action(chat_id=user_id, action=ChatAction.TYPING),
                    timeout=8.0,
                )
                ok_count += 1
            except TelegramRetryAfter as retry_error:
                retry_after_count += 1
                wait_for = min(max(float(retry_error.retry_after), 0.2), 10.0)
                await asyncio.sleep(wait_for)
                try:
                    await asyncio.wait_for(
                        bot.send_chat_action(
                            chat_id=user_id,
                            action=ChatAction.TYPING,
                        ),
                        timeout=8.0,
                    )
                    ok_count += 1
                except TelegramForbiddenError:
                    blocked_count += 1
                    blocked_buffer.append(user_id)
                except TelegramBadRequest as bad_request_error:
                    if _is_blocked_bad_request(bad_request_error):
                        blocked_count += 1
                        blocked_buffer.append(user_id)
                    else:
                        bad_request_count += 1
                except Exception:
                    error_count += 1
            except TelegramForbiddenError:
                blocked_count += 1
                blocked_buffer.append(user_id)
            except TelegramBadRequest as bad_request_error:
                if _is_blocked_bad_request(bad_request_error):
                    blocked_count += 1
                    blocked_buffer.append(user_id)
                else:
                    bad_request_count += 1
            except Exception:
                error_count += 1

            if len(blocked_buffer) >= USER_PROBE_BUFFER_SIZE:
                await flush_blocked()

            await asyncio.sleep(USER_PROBE_SLEEP_SEC)

        await flush_blocked()

        await Reporter.send_system_log(
            bot,
            (
                "🧹 <b>User Probe</b>\n"
                f"Проверено: {checked}/{total}\n"
                f"OK: {ok_count}\n"
                f"Заблокировали/недоступны: {blocked_count}\n"
                f"Удалено из БД: {removed_count}\n"
                f"RetryAfter: {retry_after_count}\n"
                f"BadRequest: {bad_request_count}\n"
                f"Ошибки: {error_count}"
            ),
        )

        return {
            "checked": checked,
            "ok": ok_count,
            "blocked": blocked_count,
            "removed": removed_count,
            "retry_after": retry_after_count,
            "bad_request": bad_request_count,
            "errors": error_count,
        }
    except asyncio.CancelledError:
        raise
    except Exception as error:
        await Reporter.send_error(bot, f"User probe failed: {error}")
        raise
    finally:
        await _release_probe_lock(lock_client, lock_token)
        try:
            await bot.session.close()
        except Exception:
            pass

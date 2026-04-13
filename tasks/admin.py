import asyncio
import psutil
from typing import Dict, Any

from celery_app import app
from tasks.base import (
    OptimizedTask,
    setup_log_rotation,
    _setup_loop_exception_handler,
    format_time,
    logger,
)
from database.repo import SubRepo
from utils.checker import VlessChecker
from utils.batch_processor import CpuAdaptiveProcessor
from utils.state import BotState
from utils.reporter import Reporter
from config import config

from aiogram import Bot
from aiogram.client.session.aiohttp import AiohttpSession


@app.task(
    name="tasks.run_admin_recheck_task",
    base=OptimizedTask,
    bind=True,
    acks_late=False,
    reject_on_worker_lost=False,
    time_limit=7200,
    soft_time_limit=7140,
)
async def run_admin_recheck_task(
    self, mode: str, total_passes: int, chat_id: int, message_id: int
) -> Dict[str, Any]:
    setup_log_rotation()
    _setup_loop_exception_handler()
    from aiogram.exceptions import TelegramRetryAfter, TelegramBadRequest
    from keyboards.admin import recheck_menu_kb

    session = AiohttpSession()
    bot = Bot(token=config.BOT_TOKEN.get_secret_value(), session=session)

    await Reporter.send_admin_action(
        bot,
        f"Recheck task started: mode={mode}, passes={total_passes}, chat_id={chat_id}, message_id={message_id}",
    )

    raw_subs = []
    if mode == "all":
        raw_subs = await SubRepo.get_all_subscriptions_for_check()
    elif mode == "active":
        raw_subs = await SubRepo.get_active_subscriptions_for_check()
    elif mode == "dead":
        raw_subs = await SubRepo.get_dead_subscriptions_for_check()

    if not raw_subs:
        await BotState.set_maintenance(False)
        await Reporter.send_admin_action(
            bot,
            f"Recheck task finished early: no servers for mode={mode}",
        )
        try:
            await bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text="<blockquote>⚠️ <b>Нет серверов для проверки!</b></blockquote>",
                reply_markup=recheck_menu_kb(),
                parse_mode="HTML",
            )
        except Exception:
            pass
        await bot.session.close()
        return {"status": "empty"}

    current_subs = [
        {
            "id": s.id,
            "vless_key": s.vless_key,
            "is_active": s.is_active,
            "death_count": int(getattr(s, "death_count", 0) or 0),
            "region": s.region,
        }
        for s in raw_subs
    ]
    checked_ids = [s["id"] for s in current_subs]
    del raw_subs

    global_active = 0
    global_died = 0
    total_died = 0
    last_stats = None
    effective_total_passes = 1

    try:
        for current_pass in range(1, effective_total_passes + 1):
            if not current_subs:
                break

            total = len(current_subs)
            update_lock = asyncio.Lock()
            status_buffer = []
            region_buffer = []
            key_buffer = []

            stats = {
                "completed": 0,
                "active": 0,
                "died": 0,
                "revived": 0,
                "saved": 0,
                "f1_dead": 0,
                "f2_dead": 0,
                "f3_dead": 0,
                "f4_dead": 0,
                "f5_dead": 0,
                "f6_dead": 0,
                "sys_err": 0,
            }

            survived_ids = set()
            next_pass_retry_ids = set()
            start_time = asyncio.get_event_loop().time()
            is_running = True

            async def run_single_check(vless_key: str):
                try:
                    result = await asyncio.wait_for(
                        VlessChecker.process_subscription(
                            vless_key,
                            strict_speed=False,
                        ),
                        timeout=55.0,
                    )
                    return result, None
                except asyncio.TimeoutError:
                    return None, "timeout"

            async def flush_buffers():
                to_save_status = None
                to_save_region = None
                to_save_keys = None

                async with update_lock:
                    if status_buffer:
                        to_save_status = list(status_buffer)
                        status_buffer.clear()
                    if region_buffer:
                        to_save_region = list(region_buffer)
                        region_buffer.clear()
                    if key_buffer:
                        to_save_keys = list(key_buffer)
                        key_buffer.clear()

                if to_save_status:
                    await SubRepo.batch_update_status(to_save_status)
                    stats["saved"] += len(to_save_status)
                if to_save_region:
                    await SubRepo.batch_update_regions(to_save_region)
                if to_save_keys:
                    await SubRepo.batch_update_keys(to_save_keys)

            async def db_flusher():
                while is_running:
                    try:
                        await asyncio.sleep(2.0)
                        if not is_running:
                            break
                        await flush_buffers()
                    except asyncio.CancelledError:
                        break
                    except Exception as e:
                        logger.error(f"DB Flusher Error: {e}")

            flusher_task = asyncio.create_task(db_flusher())

            async def ui_loop():
                while is_running:
                    try:
                        await asyncio.sleep(10.0)
                        if not is_running:
                            break

                        completed = stats["completed"]
                        elapsed = asyncio.get_event_loop().time() - start_time

                        percent = int((completed / total) * 100) if total > 0 else 0
                        speed = int(completed / elapsed * 60) if elapsed > 0 else 0

                        if completed > 0 and elapsed > 0:
                            calc_speed = completed / elapsed
                            if calc_speed > 0:
                                remaining = int((total - completed) / calc_speed)
                            else:
                                remaining = 9999
                        else:
                            remaining = 0

                        remaining_str = format_time(remaining)

                        cpu = psutil.cpu_percent()
                        ram = psutil.virtual_memory().percent

                        await bot.edit_message_text(
                            chat_id=chat_id,
                            message_id=message_id,
                            text=f"<blockquote>⚡ <b>CHECK</b> (Проход {current_pass}/{effective_total_passes})\n\n"
                            f"📊 Прогресс: <b>{percent}%</b> ({completed}/{total})\n"
                            f"⚡ Скорость: <b>{speed}</b> серв/мин | ⏱️ Осталось: ~{remaining_str}\n\n"
                            f"💻 Ресурсы: CPU <b>{cpu}%</b> | RAM <b>{ram}%</b>\n"
                            f"━━━━━━━━━━━━━━━━━━━━━━\n"
                            f"✅ <b>Рабочих:</b> {stats['active']} | 💀 <b>Потеряно:</b> {stats['died']}\n"
                            f"🆙 <b>Восстановлено:</b> {stats['revived']} | 💾 <b>Сохранено:</b> {stats['saved']}\n\n"
                            f"📉 <b>Причины отказа:</b>\n"
                            f"├ 🚫 TCP: {stats['f1_dead']}\n"
                            f"├ 🌐 Connectivity: {stats['f4_dead']}\n"
                            f"├ 🤖 Checker: {stats['f3_dead']}\n"
                            f"└ ⚙️ SysErr: {stats['sys_err']}</blockquote>",
                            parse_mode="HTML",
                        )
                    except asyncio.CancelledError:
                        break
                    except TelegramRetryAfter as e:
                        await asyncio.sleep(e.retry_after)
                    except TelegramBadRequest as e:
                        if "message is not modified" not in str(e).lower():
                            logger.error(f"UI Loop Bad Request: {e}")
                    except Exception as e:
                        if "SoftTimeLimitExceeded" not in type(e).__name__:
                            logger.error(f"UI Loop Error: {e}")

            ui_task = asyncio.create_task(ui_loop())

            async def process_sub(sub):
                try:
                    first_check, first_error = await run_single_check(sub["vless_key"])
                    if first_error == "timeout" or first_check is None:
                        async with update_lock:
                            status_buffer.append(
                                {
                                    "id": sub["id"],
                                    "check_status": "sys_err",
                                }
                            )
                            stats["sys_err"] += 1
                            stats["completed"] += 1
                        return (False, {"status": "timeout"})

                    (
                        is_alive,
                        region,
                        latency,
                        speed_mbps,
                        ai_avail,
                        no_ads,
                        err,
                        updated_link,
                    ) = first_check

                    err_str = str(err or "")
                    status_upd = None
                    region_upd = None
                    key_upd = None

                    def _is_standard_error(err_value: str) -> bool:
                        return err_value and any(
                            f"Factor {i}" in str(err_value) for i in range(0, 7)
                        )

                    if updated_link != sub["vless_key"]:
                        key_upd = {"id": sub["id"], "vless_key": updated_link}
                        sub["vless_key"] = updated_link

                    is_standard_err = _is_standard_error(err)
                    measured_speed = float(speed_mbps or 0.0)

                    if is_alive and measured_speed < 10.0:
                        is_alive = False
                        err = f"Factor 6: Speed < 10 Mbps ({measured_speed:.2f})"
                        err_str = str(err)
                        is_standard_err = True

                    if not is_alive and not is_standard_err:
                        async with update_lock:
                            status_buffer.append(
                                {
                                    "id": sub["id"],
                                    "check_status": "sys_err",
                                }
                            )
                            stats["sys_err"] += 1
                            stats["completed"] += 1
                        return (False, {"status": "error"})

                    if is_alive:
                        stats["active"] += 1
                        survived_ids.add(sub["id"])
                        if not sub["is_active"]:
                            stats["revived"] += 1
                        sub["death_count"] = 0

                        status_upd = {
                            "id": sub["id"],
                            "check_status": "alive",
                            "is_active": True,
                            "latency_ms": latency,
                            "speed_mbps": measured_speed,
                            "ai_available": ai_avail,
                            "no_ads": no_ads,
                        }
                        if region and "Unk" not in region:
                            region_upd = {"id": sub["id"], "region": region}
                        result_status = "active"
                    else:
                        if err_str.startswith("SYS_ERR"):
                            stats["sys_err"] += 1
                            result_status = "sys_err"
                            status_upd = {
                                "id": sub["id"],
                                "check_status": "sys_err",
                            }
                            async with update_lock:
                                status_buffer.append(status_upd)
                                stats["completed"] += 1
                            return (True, {"status": result_status})

                        if "Factor 1" in err_str:
                            stats["f1_dead"] += 1
                        elif "Factor 2" in err_str:
                            stats["f2_dead"] += 1
                        elif "Factor 4" in err_str:
                            stats["f4_dead"] += 1
                        elif "Factor 5" in err_str:
                            stats["f5_dead"] += 1
                        elif "Factor 6" in err_str:
                            stats["f6_dead"] += 1
                        else:
                            stats["f3_dead"] += 1

                        next_death_count = int(sub.get("death_count", 0) or 0) + 1
                        sub["death_count"] = next_death_count

                        if sub["is_active"] and next_death_count >= 3:
                            stats["died"] += 1

                        status_upd = {
                            "id": sub["id"],
                            "check_status": "dead",
                            "is_active": False,
                            "latency_ms": 9999,
                            "speed_mbps": 0.0,
                            "ai_available": False,
                            "no_ads": False,
                        }
                        result_status = "dead"

                    async with update_lock:
                        if status_upd:
                            status_buffer.append(status_upd)
                            status_value = status_upd.get("check_status")
                            if status_value == "alive":
                                sub["is_active"] = True
                            elif status_value == "dead":
                                sub["is_active"] = bool(sub.get("death_count", 0) < 3)
                        if region_upd:
                            region_buffer.append(region_upd)
                        if key_upd:
                            key_buffer.append(key_upd)
                        stats["completed"] += 1

                    return (True, {"status": result_status})
                except asyncio.CancelledError:
                    async with update_lock:
                        status_buffer.append(
                            {
                                "id": sub["id"],
                                "check_status": "sys_err",
                            }
                        )
                        stats["sys_err"] += 1
                        stats["completed"] += 1
                    return (False, {"status": "cancelled"})
                except Exception as e:
                    if "SoftTimeLimitExceeded" not in type(e).__name__:
                        logger.error(f"Process Sub Error: {e}")
                    async with update_lock:
                        status_buffer.append(
                            {
                                "id": sub["id"],
                                "check_status": "sys_err",
                            }
                        )
                        stats["sys_err"] += 1
                        stats["completed"] += 1
                    return (False, {"status": "error"})

            processor = None
            try:
                recheck_max_workers = min(config.MAX_WORKERS, 30)
                recheck_min_workers = min(config.MIN_WORKERS, recheck_max_workers)
                processor = CpuAdaptiveProcessor(
                    initial_workers=recheck_max_workers,
                    min_workers=recheck_min_workers,
                    max_workers=recheck_max_workers,
                    target_cpu=75.0,
                    target_ram=80.0,
                )

                await processor.process(
                    items=current_subs,
                    process_func=process_sub,
                    on_progress=None,
                    collect_results=False,
                )

                total_died += stats["died"]

            except Exception as e:
                logger.error(f"Processing error in pass {current_pass}: {e}")
                raise
            finally:
                is_running = False
                if processor:
                    processor.cancel()

                    try:
                        await flusher_task
                    except Exception:
                        pass

                    await flush_buffers()

                    ui_task.cancel()
                    try:
                        await ui_task
                    except Exception:
                        pass

            last_stats = stats

            if current_pass < effective_total_passes:
                if mode in {"active", "all"}:
                    current_subs = [
                        s for s in current_subs if s["id"] in next_pass_retry_ids
                    ]
                elif mode == "dead":
                    current_subs = [s for s in current_subs if s["id"] not in survived_ids]
                else:
                    current_subs = [s for s in current_subs if s["id"] in survived_ids]
                await asyncio.sleep(2)

        await SubRepo.cleanup_dead_subs(max_deaths=10)
        checked_after = await SubRepo.get_subs_by_ids(checked_ids)
        global_active = sum(1 for s in checked_after if s.is_active)
        global_died = total_died
        await BotState.set_maintenance(False)

        if last_stats is None:
            last_stats = {
                "saved": 0,
                "revived": 0,
                "sys_err": 0,
                "f1_dead": 0,
                "f2_dead": 0,
                "f3_dead": 0,
                "f4_dead": 0,
                "f5_dead": 0,
                "f6_dead": 0,
            }

        try:
            total_dead = (
                last_stats["f1_dead"]
                + last_stats["f2_dead"]
                + last_stats["f3_dead"]
                + last_stats["f4_dead"]
                + last_stats["f5_dead"]
                + last_stats["f6_dead"]
            )

            await bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=f"<blockquote>✅ <b>Проверка успешно завершена!</b>\n\n"
                f"🟢 <b>MAINTENANCE MODE ОТКЛЮЧЕН</b>\n"
                f"Бот снова доступен для пользователей ✅\n\n"
                f"📊 <b>Итоговый отчёт:</b> (Проходов: {effective_total_passes})\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"🟢 <b>Рабочих серверов:</b> {global_active}\n"
                f"💀 <b>Потеряно (стало мертвыми):</b> {global_died}\n"
                f"🆙 <b>Восстановлено:</b> {last_stats['revived']}\n"
                f"💾 <b>Сохранено в БД:</b> {last_stats['saved']}\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"📉 <b>Анализ отказов ({total_dead} всего):</b>\n"
                f"├ 🚫 TCP ошибка: {last_stats['f1_dead']}\n"
                f"├ 🌐 Connectivity ошибка: {last_stats['f4_dead']}\n"
                f"└ 🤖 Checker ошибка: {last_stats['f3_dead']}\n\n"
                f"⚙️ <b>Системных ошибок:</b> {last_stats['sys_err']}</blockquote>",
                reply_markup=recheck_menu_kb(),
                parse_mode="HTML",
            )
        except Exception:
            pass

        await Reporter.send_admin_action(
            bot,
            "Recheck task completed successfully",
        )

    except asyncio.CancelledError:
        raise
    except Exception as e:
        if "SoftTimeLimitExceeded" in type(e).__name__:
            logger.warning("Admin Recheck hit SoftTimeLimitExceeded.")
            try:
                await bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=message_id,
                    text="<blockquote>⚠️ <b>Проверка прервана по тайм-ауту (2 часа)!</b>\nЧасть серверов была обработана.</blockquote>",
                    reply_markup=recheck_menu_kb(),
                    parse_mode="HTML",
                )
            except Exception:
                pass
            await Reporter.send_admin_action(
                bot,
                "Recheck task stopped by soft time limit",
            )
            return {"status": "timeout_graceful"}

        await Reporter.send_error(bot, f"Admin Recheck failed: {str(e)}")
        await Reporter.send_admin_action(bot, f"Recheck task failed: {e}")
        raise
    finally:
        await BotState.set_maintenance(False)
        await bot.session.close()

    return {"status": "done"}

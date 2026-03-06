import asyncio
import logging
import logging.handlers
import psutil
from typing import Dict, Any

from celery_app import app
from utils.async_celery import AsyncTask
from utils.collector import SubscriptionCollector
from database.repo import SubRepo, SystemRepo, StatsRepo
from utils.checker import VlessChecker
from utils.batch_processor import SmartBatchProcessor, CpuAdaptiveProcessor
from utils.state import BotState
from utils.smart_alerts import SmartAlerts
from utils.checker.geo_ip import GeoIP
from utils.reporter import Reporter
from config import config

from aiogram import Bot
from aiogram.client.session.aiohttp import AiohttpSession

def setup_log_rotation():
    root_logger = logging.getLogger()
    if not any(isinstance(h, logging.handlers.RotatingFileHandler) for h in root_logger.handlers):
        handler = logging.handlers.RotatingFileHandler("worker.log", maxBytes=15*1024*1024, backupCount=3)
        formatter = logging.Formatter('[%(asctime)s] %(levelname)s in %(name)s: %(message)s')
        handler.setFormatter(formatter)
        root_logger.addHandler(handler)

logger = logging.getLogger("Worker")

def _setup_loop_exception_handler():
    try:
        loop = asyncio.get_running_loop()
        def custom_exc_handler(loop, context):
            msg = context.get("message", "")
            exc = context.get("exception")
            if exc:
                exc_type = str(type(exc)).lower()
                if any(err in exc_type for err in["gaierror", "dnserror", "clientconnectorerror", "timeouterror", "cancellederror", "softtimelimitexceeded"]):
                    return
            if "Future exception was never retrieved" in msg or "Task was destroyed but it is pending" in msg:
                return
            loop.default_exception_handler(context)
        loop.set_exception_handler(custom_exc_handler)
    except Exception:
        pass

def format_time(seconds: int) -> str:
    if seconds < 60:
        return f"{seconds} сек"
    elif seconds < 3600:
        m = seconds // 60
        s = seconds % 60
        return f"{m} мин {s} сек"
    else:
        h = seconds // 3600
        m = (seconds % 3600) // 60
        return f"{h} ч {m} мин"

class OptimizedTask(AsyncTask):
    pass

@app.task(base=OptimizedTask, bind=True, max_retries=3, time_limit=3600, soft_time_limit=3540)
async def check_subs_batch_task(self, sub_ids: list) -> Dict[str, Any]:
    setup_log_rotation()
    _setup_loop_exception_handler()
    return {"status": "disabled"}

@app.task(base=OptimizedTask, time_limit=3600, soft_time_limit=3540)
async def run_collector_task() -> Dict[str, Any]:
    setup_log_rotation()
    _setup_loop_exception_handler()
    
    is_maint = await BotState.is_maintenance()
    if is_maint:
        return {"status": "skipped", "reason": "maintenance"}

    enabled_str = await SystemRepo.get_config("collector_enabled")
    if enabled_str == "false":
        return {"status": "skipped", "reason": "admin_disabled"}

    start_time = asyncio.get_event_loop().time()
    result = {}

    try:
        old_counts = await StatsRepo.get_regions_counts()
        result = await SubscriptionCollector.run_collection()
        cleaned = await SubRepo.cleanup_dead_subs(max_deaths=3)
        new_counts = await StatsRepo.get_regions_counts()

        await SmartAlerts.process_changes(old_counts, new_counts)
        duration = asyncio.get_event_loop().time() - start_time

        try:
            bot_instance = Bot(token=config.BOT_TOKEN.get_secret_value(), session=AiohttpSession())
            await Reporter.send_new_configs(bot_instance, result.get("added", 0), result.get("region_stats", {}))
            await Reporter.send_not_configs(bot_instance, result.get("rejected", 0), result.get("rejected_reasons", {}))
            await bot_instance.session.close()
        except asyncio.CancelledError:
            raise
        except Exception as e:
            if "SoftTimeLimitExceeded" not in type(e).__name__:
                logger.error(f"Failed to send reports: {e}")

        return {"success": True, "duration": duration, "result": result, "cleaned": cleaned}

    except asyncio.CancelledError:
        raise
    except Exception as e:
        if "SoftTimeLimitExceeded" in type(e).__name__:
            logger.warning("Collector task hit SoftTimeLimitExceeded, completing gracefully.")
            try:
                bot_instance = Bot(token=config.BOT_TOKEN.get_secret_value(), session=AiohttpSession())
                if result:
                    await Reporter.send_new_configs(bot_instance, result.get("added", 0), result.get("region_stats", {}))
                    await Reporter.send_not_configs(bot_instance, result.get("rejected", 0), result.get("rejected_reasons", {}))
                await Reporter.send_info(bot_instance, "⚠️ Сборщик прерван по таймауту (достигнут лимит времени).")
                await bot_instance.session.close()
            except Exception:
                pass
            return {"status": "timeout_graceful"}

        try:
            bot_instance = Bot(token=config.BOT_TOKEN.get_secret_value(), session=AiohttpSession())
            await Reporter.send_error(bot_instance, f"Collector failed: {str(e)}")
            await bot_instance.session.close()
        except Exception:
            pass
        raise

@app.task(base=OptimizedTask, time_limit=3600, soft_time_limit=3540)
async def check_stability_task() -> Dict[str, Any]:
    setup_log_rotation()
    _setup_loop_exception_handler()
    
    is_maint = await BotState.is_maintenance()
    if is_maint:
        return {"status": "skipped", "reason": "maintenance"}

    subs = await SubRepo.get_candidates_for_stability()
    if not subs:
        return {"checked": 0}

    worker_count = min(config.MAX_WORKERS, max(config.MIN_WORKERS, len(subs) // 10))
    processor = SmartBatchProcessor(worker_count=worker_count)

    old_counts = await StatsRepo.get_regions_counts()

    def check_one(sub):
        async def _check():
            try:
                is_alive, _, latency, speed_mbps, ai_avail, no_ads, err, _ = await VlessChecker.process_subscription(sub.vless_key)

                is_standard_err = err and any(f"Factor {i}" in str(err) for i in range(1, 7))
                if not is_alive and not is_standard_err:
                    return (True, None)

                return (True, {"id": sub.id, "is_alive": is_alive, "latency": latency, "speed_mbps": speed_mbps, "ai": ai_avail, "no_ads": no_ads})
            except asyncio.CancelledError:
                raise
            except Exception:
                return (True, None)
        return _check()

    try:
        batch_res = await processor.process(
            items=subs,
            process_func=check_one,
            collect_results=True
        )

        updates = [item["result"] for item in batch_res.items if item["success"] and item["result"] is not None]

        if updates:
            await SubRepo.batch_update_stability(updates)
            status_updates =[
                {
                    "id": u["id"], 
                    "is_active": u["is_alive"], 
                    "latency_ms": u["latency"],
                    "speed_mbps": u["speed_mbps"],
                    "ai_available": u["ai"],
                    "no_ads": u["no_ads"]
                } 
                for u in updates
            ]
            await SubRepo.batch_update_status(status_updates)
            await SubRepo.cleanup_dead_subs(max_deaths=3)

        new_counts = await StatsRepo.get_regions_counts()
        await SmartAlerts.process_changes(old_counts, new_counts)

        return {"checked": len(updates)}
    except Exception as e:
        if "SoftTimeLimitExceeded" in type(e).__name__:
            logger.warning("Stability check hit SoftTimeLimitExceeded.")
            return {"status": "timeout_graceful"}
        raise

@app.task(base=OptimizedTask, time_limit=600, soft_time_limit=540)
async def update_geoip_task() -> Dict[str, Any]:
    setup_log_rotation()
    _setup_loop_exception_handler()
    success = await GeoIP.update_database()
    return {"status": "updated" if success else "failed"}

@app.task(base=OptimizedTask, bind=True, time_limit=7200, soft_time_limit=7140)
async def run_admin_recheck_task(self, mode: str, total_passes: int, chat_id: int, message_id: int) -> Dict[str, Any]:
    setup_log_rotation()
    _setup_loop_exception_handler()
    from aiogram.exceptions import TelegramRetryAfter, TelegramBadRequest
    from keyboards.admin import recheck_menu_kb

    session = AiohttpSession()
    bot = Bot(token=config.BOT_TOKEN.get_secret_value(), session=session)

    raw_subs =[]
    if mode == "all":
        raw_subs = await SubRepo.get_all_subscriptions_for_check()
    elif mode == "active":
        raw_subs = await SubRepo.get_active_subscriptions_for_check()
    elif mode == "dead":
        raw_subs = await SubRepo.get_dead_subscriptions_for_check()

    if not raw_subs:
        await BotState.set_maintenance(False)
        try:
            await bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text="<blockquote>⚠️ <b>Нет серверов для проверки!</b></blockquote>",
                reply_markup=recheck_menu_kb(),
                parse_mode="HTML"
            )
        except Exception:
            pass
        await bot.session.close()
        return {"status": "empty"}

    current_subs =[{"id": s.id, "vless_key": s.vless_key, "is_active": s.is_active, "region": s.region} for s in raw_subs]
    del raw_subs

    global_active = 0
    global_died = 0

    try:
        for current_pass in range(1, total_passes + 1):
            if not current_subs:
                break

            total = len(current_subs)
            update_lock = asyncio.Lock()
            status_buffer = []
            region_buffer = []
            key_buffer =[]

            stats = {
                "completed": 0, "active": 0, "died": 0, "revived": 0, "saved": 0, 
                "f1_dead": 0, "f2_dead": 0, "f3_dead": 0, "f4_dead": 0, "f5_dead": 0, "f6_dead": 0, "sys_err": 0
            }

            survived_ids = set()
            start_time = asyncio.get_event_loop().time()
            is_running = True

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
                try:
                    while is_running:
                        await asyncio.sleep(2.0)
                        await flush_buffers()
                except asyncio.CancelledError:
                    pass

            flusher_task = asyncio.create_task(db_flusher())

            async def ui_loop():
                try:
                    while is_running:
                        await asyncio.sleep(4.0)
                        completed = stats["completed"]

                        elapsed = asyncio.get_event_loop().time() - start_time
                        percent = int((completed / total) * 100) if total > 0 else 0
                        speed = int(completed / elapsed * 60) if elapsed > 0 else 0
                        remaining = int((total - completed) / (completed / elapsed)) if completed > 0 else 0
                        cpu = psutil.cpu_percent()
                        ram = psutil.virtual_memory().percent

                        remaining_str = format_time(remaining)

                        await bot.edit_message_text(
                            chat_id=chat_id,
                            message_id=message_id,
                    text=f"<blockquote>⚡ <b>6-FACTOR CHECK</b> (Проход {current_pass}/{total_passes})\n\n"
                        f"📊 Прогресс: <b>{percent}%</b> ({completed}/{total})\n"
                        f"⚡ Скорость: <b>{speed}</b> серв/мин | ⏱️ Осталось: ~{remaining_str}\n\n"
                        f"💻 Ресурсы: CPU <b>{cpu}%</b> | RAM <b>{ram}%</b>\n"
                        f"━━━━━━━━━━━━━━━━━━━━━━\n"
                        f"✅ <b>Рабочих:</b> {stats['active']} | 💀 <b>Потеряно:</b> {stats['died']}\n"
                        f"🆙 <b>Восстановлено:</b> {stats['revived']} | 💾 <b>Сохранено:</b> {stats['saved']}\n\n"
                        f"📉 <b>Причины отказа:</b>\n"
                        f"├ 🚫 TCP: {stats['f1_dead']} | 🔐 SSL: {stats['f2_dead']}\n"
                        f"├ 🤖 Xray: {stats['f3_dead']} | 🌐 Portal: {stats['f4_dead']}\n"
                        f"├ 🛡 Route: {stats['f5_dead']} | 🐌 Speed: {stats['f6_dead']}\n"
                        f"└ ⚙️ SysErr: {stats['sys_err']}</blockquote>",
                            parse_mode="HTML"
                        )
                except asyncio.CancelledError:
                    pass
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
                    is_alive, region, latency, speed_mbps, ai_avail, no_ads, err, updated_link = await VlessChecker.process_subscription(sub["vless_key"])

                    status_upd = None
                    region_upd = None
                    key_upd = None

                    if updated_link != sub["vless_key"]:
                        key_upd = {"id": sub["id"], "vless_key": updated_link}
                        sub["vless_key"] = updated_link

                    is_standard_err = err and any(f"Factor {i}" in str(err) for i in range(1, 7))

                    if not is_alive and not is_standard_err:
                        async with update_lock:
                            stats["sys_err"] += 1
                            stats["completed"] += 1
                        return (False, {"status": "error"})

                    if is_alive:
                        stats["active"] += 1
                        survived_ids.add(sub["id"])
                        if not sub["is_active"]:
                            stats["revived"] += 1

                        status_upd = {
                            "id": sub["id"],
                            "is_active": True,
                            "latency_ms": latency,
                            "speed_mbps": speed_mbps,
                            "ai_available": ai_avail,
                            "no_ads": no_ads
                        }
                        if region and "Unk" not in region:
                            region_upd = {"id": sub["id"], "region": region}
                        result_status = "active"
                    else:
                        err_str = str(err)
                        if "Factor 1" in err_str: stats["f1_dead"] += 1
                        elif "Factor 2" in err_str: stats["f2_dead"] += 1
                        elif "Factor 4" in err_str: stats["f4_dead"] += 1
                        elif "Factor 5" in err_str: stats["f5_dead"] += 1
                        elif "Factor 6" in err_str: stats["f6_dead"] += 1
                        else: stats["f3_dead"] += 1

                        if sub["is_active"]:
                            stats["died"] += 1

                        status_upd = {
                            "id": sub["id"],
                            "is_active": False,
                            "latency_ms": 9999,
                            "speed_mbps": 0.0,
                            "ai_available": False,
                            "no_ads": False
                        }
                        result_status = "dead"

                    async with update_lock:
                        if status_upd: status_buffer.append(status_upd)
                        if region_upd: region_buffer.append(region_upd)
                        if key_upd: key_buffer.append(key_upd)
                        stats["completed"] += 1

                    return (True, {"status": result_status})
                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    if "SoftTimeLimitExceeded" not in type(e).__name__:
                        logger.error(f"Process Sub Error: {e}")
                    async with update_lock:
                        stats["sys_err"] += 1
                        stats["completed"] += 1
                    return (False, {"status": "error"})

        processor = None
        try:
            processor = CpuAdaptiveProcessor(
                initial_workers=config.MAX_WORKERS // 2,
                min_workers=config.MIN_WORKERS,
                max_workers=config.MAX_WORKERS,
                target_cpu=85.0,
                target_ram=85.0
            )

            await asyncio.wait_for(
                processor.process(
                    items=current_subs,
                    process_func=process_sub,
                    on_progress=None,
                    collect_results=False
                ),
                timeout=config.RECHECK_TIMEOUT_PER_PASS
            )

            if current_pass == total_passes:
                global_active = stats["active"]
                global_died = stats["died"]

        except asyncio.TimeoutError:
            logger.warning(f"Pass {current_pass} timed out after 8 minutes")
            remaining = total - stats["completed"]
            if remaining > 0:
                logger.warning(f"Force completing {remaining} unfinished items")
                stats["completed"] += remaining
                stats["sys_err"] += remaining
            if current_pass == total_passes:
                global_active = stats["active"]
                global_died = stats["died"]
        except Exception as e:
            logger.error(f"Processing error in pass {current_pass}: {e}")
            raise
        finally:
            is_running = False
            if processor:
                processor.cancel()

                try: await flusher_task
                except Exception: pass

                await flush_buffers()

                ui_task.cancel()
                try: await ui_task
                except Exception: pass

        if current_pass < total_passes:
            current_subs =[s for s in current_subs if s["id"] in survived_ids]
            await asyncio.sleep(2)

        await SubRepo.cleanup_dead_subs(max_deaths=3)
        await BotState.set_maintenance(False)
        del current_subs

        try:
            total_dead = stats['f1_dead'] + stats['f2_dead'] + stats['f3_dead'] + stats['f4_dead'] + stats['f5_dead'] + stats['f6_dead']

            await bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=f"<blockquote>✅ <b>Проверка успешно завершена!</b>\n\n"
                f"🟢 <b>MAINTENANCE MODE ОТКЛЮЧЕН</b>\n"
                f"Бот снова доступен для пользователей ✅\n\n"
                f"📊 <b>Итоговый отчёт:</b> (Проходов: {total_passes})\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"🟢 <b>Рабочих серверов:</b> {global_active}\n"
                f"💀 <b>Потеряно (стало мертвыми):</b> {global_died}\n"
                f"🆙 <b>Восстановлено:</b> {stats['revived']}\n"
                f"💾 <b>Сохранено в БД:</b> {stats['saved']}\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"📉 <b>Анализ отказов ({total_dead} всего):</b>\n"
                f"├ 🚫 TCP недоступен: {stats['f1_dead']}\n"
                f"├ 🔐 SSL ошибка: {stats['f2_dead']}\n"
                f"├ 🤖 Xray ошибка: {stats['f3_dead']}\n"
                f"├ 🌐 Portal блок: {stats['f4_dead']}\n"
                f"├ 🛡 Route проблема: {stats['f5_dead']}\n"
                f"└ 🐌 Скорость <25: {stats['f6_dead']}\n\n"
                f"⚙️ <b>Системных ошибок:</b> {stats['sys_err']}</blockquote>",
                reply_markup=recheck_menu_kb(),
                parse_mode="HTML"
            )
        except Exception:
            pass

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
                    parse_mode="HTML"
                )
            except Exception:
                pass
            return {"status": "timeout_graceful"}

        await Reporter.send_error(bot, f"Admin Recheck failed: {str(e)}")
        raise
    finally:
        await BotState.set_maintenance(False)
        await bot.session.close()

    return {"status": "done"}

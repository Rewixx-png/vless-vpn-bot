import asyncio
import logging
import psutil
import gc
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
from config import config

logger = logging.getLogger("Worker")

class OptimizedTask(AsyncTask):
    pass

@app.task(base=OptimizedTask, bind=True, max_retries=3)
async def check_subs_batch_task(self, sub_ids: list) -> Dict[str, Any]:
    return {"status": "disabled"}

@app.task(base=OptimizedTask)
async def run_collector_task() -> Dict[str, Any]:
    if BotState.is_maintenance():
        return {"status": "skipped", "reason": "maintenance"}

    enabled_str = await SystemRepo.get_config("collector_enabled")
    if enabled_str == "false":
        return {"status": "skipped", "reason": "admin_disabled"}

    start_time = asyncio.get_event_loop().time()
    
    try:
        old_counts = await StatsRepo.get_regions_counts()
        result = await SubscriptionCollector.run_collection()
        cleaned = await SubRepo.cleanup_dead_subs(max_deaths=3)
        new_counts = await StatsRepo.get_regions_counts()
        
        await SmartAlerts.process_changes(old_counts, new_counts)
        duration = asyncio.get_event_loop().time() - start_time
        return {"success": True, "duration": duration, "result": result, "cleaned": cleaned}
    except Exception:
        raise

@app.task(base=OptimizedTask)
async def check_stability_task() -> Dict[str, Any]:
    if BotState.is_maintenance():
        return {"status": "skipped", "reason": "maintenance"}

    subs = await SubRepo.get_candidates_for_stability()
    if not subs:
        return {"checked": 0}

    worker_count = min(20, max(10, len(subs) // 10))
    processor = SmartBatchProcessor(worker_count=worker_count)
    
    old_counts = await StatsRepo.get_regions_counts()
    
    def check_one(sub):
        async def _check():
            try:
                is_alive, _, latency, speed_mbps, _, err, _ = await VlessChecker.process_subscription(sub.vless_key)
                if not is_alive and err and "SYS_ERR" in str(err):
                    return (True, None)
                return (True, {"id": sub.id, "is_alive": is_alive, "latency": latency, "speed_mbps": speed_mbps})
            except Exception:
                return (True, None)
        return _check()

    batch_res = await processor.process(
        items=subs,
        process_func=check_one,
        collect_results=True
    )
    
    updates = [item["result"] for item in batch_res.items if item["success"] and item["result"] is not None]
    
    if updates:
        await SubRepo.batch_update_stability(updates)
        status_updates = [
            {
                "id": u["id"], 
                "is_active": u["is_alive"], 
                "latency_ms": u["latency"],
                "speed_mbps": u["speed_mbps"],
                "ai_available": False
            } 
            for u in updates
        ]
        await SubRepo.batch_update_status(status_updates)
        await SubRepo.cleanup_dead_subs(max_deaths=3)

    new_counts = await StatsRepo.get_regions_counts()
    await SmartAlerts.process_changes(old_counts, new_counts)

    return {"checked": len(updates)}

@app.task(base=OptimizedTask)
async def update_geoip_task() -> Dict[str, Any]:
    success = await GeoIP.update_database()
    return {"status": "updated" if success else "failed"}

@app.task(base=OptimizedTask, bind=True)
async def run_admin_recheck_task(self, mode: str, total_passes: int, chat_id: int, message_id: int) -> Dict[str, Any]:
    from aiogram import Bot
    from aiogram.client.session.aiohttp import AiohttpSession
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
        BotState.set_maintenance(False)
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
    gc.collect()

    global_active = 0
    global_died = 0

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
            "f1_dead": 0, "f2_dead": 0, "f3_dead": 0, "f4_dead": 0, "f5_dead": 0, "f6_dead": 0
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
            while is_running:
                await asyncio.sleep(2.0)
                await flush_buffers()
                
        flusher_task = asyncio.create_task(db_flusher())

        async def ui_loop():
            while is_running:
                try:
                    await asyncio.sleep(4.0)
                    completed = stats["completed"]

                    elapsed = asyncio.get_event_loop().time() - start_time
                    percent = int((completed / total) * 100) if total > 0 else 0
                    speed = int(completed / elapsed * 60) if elapsed > 0 else 0
                    remaining = int((total - completed) / (completed / elapsed)) if completed > 0 else 0
                    cpu = psutil.cpu_percent()
                    ram = psutil.virtual_memory().percent

                    await bot.edit_message_text(
                        chat_id=chat_id,
                        message_id=message_id,
                        text=f"<blockquote>⚡ <b>6-FACTOR CHECK (Pass {current_pass}/{total_passes}): {percent}%</b>\n\n"
                             f"📊 <b>{completed} / {total}</b>\n"
                             f"💻 <b>CPU:</b> {cpu}% | 🧠 <b>RAM:</b> {ram}%\n"
                             f"⚡ Скорость: {speed} серв/мин\n"
                             f"⏱️ Осталось: ~{remaining}сек\n"
                             f"━━━━━━━━━━━━━━━━━━\n"
                             f"🟢 Рабочих: <b>{stats['active']}</b>\n"
                             f"💀 Потеряно: <b>{stats['died']}</b>\n"
                             f"├── 🚫 TCP Fail: <b>{stats['f1_dead']}</b>\n"
                             f"├── 🔐 SSL Fail: <b>{stats['f2_dead']}</b>\n"
                             f"├── 🤖 Xray Fail: <b>{stats['f3_dead']}</b>\n"
                             f"├── 🌐 Portal Fail: <b>{stats['f4_dead']}</b>\n"
                             f"├── 🛡 Route Fail: <b>{stats['f5_dead']}</b>\n"
                             f"└── 🐌 Low Speed: <b>{stats['f6_dead']}</b>\n"
                             f"🆙 Восстановлено: <b>{stats['revived']}</b></blockquote>",
                        parse_mode="HTML"
                    )
                except TelegramRetryAfter as e:
                    await asyncio.sleep(e.retry_after)
                except TelegramBadRequest as e:
                    if "message is not modified" not in str(e).lower():
                        logger.error(f"UI Loop Bad Request: {e}")
                except Exception as e:
                    logger.error(f"UI Loop Error: {e}")

        ui_task = asyncio.create_task(ui_loop())

        async def process_sub(sub):
            try:
                is_alive, region, latency, speed_mbps, ai_avail, err, updated_link = await VlessChecker.process_subscription(sub["vless_key"])
                
                status_upd = None
                region_upd = None
                key_upd = None

                if updated_link != sub["vless_key"]:
                    key_upd = {"id": sub["id"], "vless_key": updated_link}
                    sub["vless_key"] = updated_link
                
                if not is_alive and err and "SYS_ERR" in str(err):
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
                        "ai_available": ai_avail
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
                        "ai_available": False
                    }
                    result_status = "dead"

                async with update_lock:
                    if status_upd: status_buffer.append(status_upd)
                    if region_upd: region_buffer.append(region_upd)
                    if key_upd: key_buffer.append(key_upd)

                return (True, {"status": result_status})
            except Exception as e:
                logger.error(f"Process Sub Error: {e}")
                return (False, {"status": "error"})

        try:
            processor = CpuAdaptiveProcessor(
                initial_workers=100,
                min_workers=10,
                max_workers=400,
                target_cpu=85.0,
                target_ram=85.0
            )
            await processor.process(
                items=current_subs,
                process_func=process_sub,
                on_progress=None,
                collect_results=False
            )
            
            if current_pass == total_passes:
                global_active = stats["active"]
                global_died = stats["died"]
            
        finally:
            is_running = False
            
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
    BotState.set_maintenance(False)
    del current_subs
    gc.collect()

    try:
        await bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=f"<blockquote>✅ <b>Проверка завершена!</b>\n\n"
                 f"🟢 <b>MAINTENANCE MODE DISABLED</b>\n"
                 f"Фоновые задачи возобновлены.\n\n"
                 f"📊 <b>Итоговый отчёт (Выполнено проходов: {total_passes}):</b>\n"
                 f"━━━━━━━━━━━━━━━━━━\n"
                 f"🟢 Итого рабочих серверов: <b>{global_active}</b>\n"
                 f"💀 Итого потеряно (Active->Dead): <b>{global_died}</b>\n"
                 f"━━━━━━━━━━━━━━━━━━\n"
                 f"ℹ️ <i>Авто-ротация SNI спасла часть конфигураций.</i>\n"
                 f"ℹ️ <i>Медленные серверы (<25 Мбит/с) отключены.</i>\n"
                 f"ℹ️ <i>База данных обновлена.</i></blockquote>",
            reply_markup=recheck_menu_kb(),
            parse_mode="HTML"
        )
    except Exception:
        pass

    await bot.session.close()
    return {"status": "done"}

import asyncio
import aiohttp
from aiogram import Router, F
from aiogram.types import CallbackQuery, Message
from database.repo import SubRepo
from utils.checker import VlessChecker
from keyboards.admin import back_to_admin

router = Router()

async def safe_edit_text(message: Message, text: str, reply_markup=None, parse_mode="HTML"):
    try:
        await message.edit_text(text, reply_markup=reply_markup, parse_mode=parse_mode)
    except: pass

@router.callback_query(F.data == "admin_fix_regions")
async def fix_unknown_regions(callback: CallbackQuery):
    msg = await callback.message.edit_text(
        "<blockquote>🚀 <b>Запуск Turbo Batch Mode...</b>\n\n"
        "ℹ️ <i>Используем пакетную проверку IP.</i></blockquote>", 
        parse_mode="HTML"
    )

    subs = await SubRepo.get_unknown_regions_subs()
    if not subs:
        await msg.edit_text("<blockquote>✅ Unknown регионов не найдено.</blockquote>", reply_markup=back_to_admin(), parse_mode="HTML")
        return

    host_to_subs = {}
    for sub in subs:
        parsed = VlessChecker.parse_config(sub.vless_key)
        if parsed and parsed.get("host"):
            host = parsed["host"]
            if host not in host_to_subs:
                host_to_subs[host] = []
            host_to_subs[host].append(sub)

    unique_hosts = list(host_to_subs.keys())
    total_hosts = len(unique_hosts)
    stats = {"fixed": 0, "processed": 0, "is_finished": False}

    async def ui_updater():
        while not stats["is_finished"]:
            percent = int((stats["processed"] / total_hosts) * 100) if total_hosts > 0 else 0
            text = (
                f"<blockquote>🚀 <b>GeoIP Update: {percent}%</b>\n"
                f"✅ Исправлено ключей: {stats['fixed']}\n"
                f"📡 Проверено хостов: {stats['processed']}/{total_hosts}</blockquote>"
            )
            await safe_edit_text(msg, text)
            await asyncio.sleep(3.0)

    updater_task = asyncio.create_task(ui_updater())

    async with aiohttp.ClientSession() as session:
        results = await VlessChecker.get_regions_batch(unique_hosts, session)
        
        for host, region in results.items():
            if "Unknown" not in region:
                if host in host_to_subs:
                    for sub in host_to_subs[host]:
                        await SubRepo.update_sub_region(sub.id, region)
                        stats["fixed"] += 1
            stats["processed"] += 1

    stats["is_finished"] = True
    updater_task.cancel()

    await safe_edit_text(
        msg,
        f"<blockquote>🏁 <b>Обновление регионов завершено!</b>\n\n"
        f"✅ Обновлено ключей: <b>{stats['fixed']}</b></blockquote>",
        reply_markup=back_to_admin()
    )

@router.callback_query(F.data == "admin_recheck")
async def recheck_all_subs(callback: CallbackQuery):
    msg = await callback.message.edit_text(
        "<blockquote>🚀 <b>Xray Core Recheck</b>\n"
        "<i>Запускаю проверку через реальное ядро Xray...</i>\n"
        "Это может занять время.</blockquote>", 
        parse_mode="HTML"
    )

    subs = await SubRepo.get_all_subscriptions_for_check()
    if not subs:
        await msg.edit_text("<blockquote>⚠️ База пуста.</blockquote>", reply_markup=back_to_admin(), parse_mode="HTML")
        return

    stats = {
        "active_now": 0, "died": 0, "revived": 0, 
        "checked": 0, "total": len(subs), "is_finished": False
    }

    queue = asyncio.Queue()
    for sub in subs:
        queue.put_nowait(sub)

    WORKERS_COUNT = 10 

    async def worker():
        while True:
            try:
                sub = queue.get_nowait()
            except asyncio.QueueEmpty:
                break

            try:
                success, region, latency, ai_avail, err = await VlessChecker.process_subscription(sub.vless_key)

                if success:
                    stats["active_now"] += 1
                    if not sub.is_active:
                        stats["revived"] += 1
                    
                    await SubRepo.update_sub_status(sub.id, is_active=True, latency=latency, ai_available=ai_avail)
                    if region and "Unknown" not in region:
                        await SubRepo.update_sub_region(sub.id, region)
                else:
                    if sub.is_active:
                        stats["died"] += 1
                    await SubRepo.update_sub_status(sub.id, is_active=False, latency=9999)
            except Exception:
                pass
            finally:
                stats["checked"] += 1
                queue.task_done()

    async def ui_updater():
        while not stats["is_finished"]:
            percent = int((stats["checked"] / stats["total"]) * 100) if stats["total"] > 0 else 0
            text = (
                f"<blockquote>🔄 <b>Xray Check: {percent}%</b>\n"
                f"📡 Проверено: {stats['checked']}/{stats['total']}\n\n"
                f"🟢 <b>Живых: {stats['active_now']}</b>\n"
                f"💀 Умерло: {stats['died']}\n"
                f"🆙 Воскресло: {stats['revived']}</blockquote>"
            )
            await safe_edit_text(msg, text)
            await asyncio.sleep(3.0)

    updater_task = asyncio.create_task(ui_updater())

    workers = [asyncio.create_task(worker()) for _ in range(WORKERS_COUNT)]
    await asyncio.gather(*workers)

    stats["is_finished"] = True
    updater_task.cancel()

    await safe_edit_text(
        msg,
        f"<blockquote>🏁 <b>Xray Recheck завершен!</b>\n\n"
        f"Всего ключей: <b>{stats['total']}</b>\n"
        f"🟢 <b>Активных: {stats['active_now']}</b>\n"
        f"💀 Мертвых: <b>{stats['died']}</b>\n"
        f"🆙 Воскресло: <b>{stats['revived']}</b></blockquote>",
        reply_markup=back_to_admin()
    )
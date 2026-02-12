import re
import io
import asyncio
import aiohttp
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.exceptions import TelegramRetryAfter, TelegramBadRequest
from sqlalchemy.exc import IntegrityError

from config import config
from database.repo import SubRepo
from utils.vless_checker import VlessChecker
from keyboards.admin import back_to_admin, regions_kb, subs_list_kb, sub_control_kb
from handlers.admin.states import AdminStates

router = Router()

async def safe_edit_text(message: Message, text: str, reply_markup=None, parse_mode="HTML"):
    try:
        await message.edit_text(text, reply_markup=reply_markup, parse_mode=parse_mode)
    except TelegramRetryAfter as e:
        wait_time = e.retry_after
        if wait_time < 15:
            await asyncio.sleep(wait_time)
            try:
                await message.edit_text(text, reply_markup=reply_markup, parse_mode=parse_mode)
            except Exception:
                pass
    except TelegramBadRequest:
        pass
    except Exception:
        pass

@router.callback_query(F.data == "admin_fix_regions")
async def fix_unknown_regions(callback: CallbackQuery):
    msg = await callback.message.edit_text(
        "🚀 <b>Запуск Turbo Batch Mode...</b>\n\n"
        "ℹ️ <i>Используем пакетную проверку (100 IP за 1 запрос).</i>", 
        parse_mode="HTML"
    )

    subs = await SubRepo.get_unknown_regions_subs()
    if not subs:
        await msg.edit_text("✅ Unknown регионов не найдено.", reply_markup=back_to_admin())
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

    CHUNK_SIZE = 100
    chunks = [unique_hosts[i:i + CHUNK_SIZE] for i in range(0, len(unique_hosts), CHUNK_SIZE)]

    async def ui_updater():
        while not stats["is_finished"]:
            percent = int((stats["processed"] / total_hosts) * 100) if total_hosts > 0 else 0
            text = (
                f"🚀 <b>Turbo Update: {percent}%</b>\n"
                f"✅ Исправлено ключей: {stats['fixed']}\n"
                f"📡 Проверено хостов: {stats['processed']}/{total_hosts}"
            )
            await safe_edit_text(msg, text)
            await asyncio.sleep(5.0)

    updater_task = asyncio.create_task(ui_updater())

    async with aiohttp.ClientSession() as session:
        for chunk in chunks:
            results = await VlessChecker.get_regions_batch(chunk, session)

            for ip, region in results.items():
                if "Unknown" not in region:
                    if ip in host_to_subs:
                        for sub in host_to_subs[ip]:
                            await SubRepo.update_sub_region(sub.id, region)
                            stats["fixed"] += 1

            stats["processed"] += len(chunk)
            await asyncio.sleep(0.5)

    stats["is_finished"] = True
    updater_task.cancel()

    await safe_edit_text(
        msg,
        f"🏁 <b>Turbo-обновление завершено!</b>\n\n"
        f"✅ Исправлено ключей: <b>{stats['fixed']}</b>\n"
        f"📡 Уникальных IP: <b>{total_hosts}</b>",
        reply_markup=back_to_admin()
    )

@router.callback_query(F.data == "admin_recheck")
async def recheck_all_subs(callback: CallbackQuery):
    msg = await callback.message.edit_text(
        "🚀 <b>Starting DEEP Force Recheck...</b>\n"
        "<i>Включаю эмуляцию VLESS клиента (Real URL Test)...</i>", 
        parse_mode="HTML"
    )

    subs = await SubRepo.get_all_subscriptions_for_check()
    if not subs:
        await msg.edit_text("⚠️ База пуста.", reply_markup=back_to_admin())
        return

    stats = {
        "active_now": 0, 
        "died": 0, 
        "revived": 0, 
        "checked": 0, 
        "total": len(subs),
        "is_finished": False
    }

    queue = asyncio.Queue()
    for sub in subs:
        queue.put_nowait(sub)

    async def worker():
        while True:
            try:
                sub = queue.get_nowait()
            except asyncio.QueueEmpty:
                break

            try:
                parsed = VlessChecker.parse_config(sub.vless_key)
                is_alive = False
                latency = 9999

                if parsed:
                    # Таймаут здесь уже обрабатывается внутри check_connection в VlessChecker (мы его обновили)
                    latency_check = await VlessChecker.check_connection(parsed)
                    if latency_check != -1:
                        is_alive = True
                        latency = latency_check

                if is_alive:
                    stats["active_now"] += 1
                    if not sub.is_active:
                        stats["revived"] += 1
                else:
                    if sub.is_active:
                        stats["died"] += 1

                await SubRepo.update_sub_status(sub.id, is_active=is_alive, latency=latency)
            except Exception:
                pass
            finally:
                stats["checked"] += 1
                queue.task_done()

    async def ui_updater():
        while not stats["is_finished"]:
            percent = int((stats["checked"] / stats["total"]) * 100) if stats["total"] > 0 else 0
            text = (
                f"🔄 <b>Deep Check: {percent}%</b>\n"
                f"<code>[{'#' * (percent // 10)}{'.' * (10 - (percent // 10))}]</code>\n"
                f"📡 Проверено: {stats['checked']}/{stats['total']}\n\n"
                f"🟢 <b>Живых: {stats['active_now']}</b>\n"
                f"💀 Умерло: {stats['died']}\n"
                f"🆙 Воскресло: {stats['revived']}"
            )
            await safe_edit_text(msg, text)
            await asyncio.sleep(5.0)

    updater_task = asyncio.create_task(ui_updater())

    workers = [asyncio.create_task(worker()) for _ in range(30)]
    await asyncio.gather(*workers)

    stats["is_finished"] = True
    updater_task.cancel()

    await safe_edit_text(
        msg,
        f"🏁 <b>Deep Recheck завершен!</b>\n\n"
        f"Всего ключей: <b>{stats['total']}</b>\n"
        f"🟢 <b>Активных: {stats['active_now']}</b>\n"
        f"💀 Отсеяно мертвых: <b>{stats['died']}</b>\n"
        f"🆙 Воскресло: <b>{stats['revived']}</b>\n",
        reply_markup=back_to_admin()
    )

@router.callback_query(F.data == "admin_add")
async def start_add_subs(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        "📝 <b>Массовая загрузка</b>\n\n"
        "Отправьте .txt файл или сообщение со списком ссылок (vless://).",
        parse_mode="HTML",
        reply_markup=back_to_admin()
    )
    await state.set_state(AdminStates.waiting_for_subs)

@router.message(StateFilter(AdminStates.waiting_for_subs), F.from_user.id.in_(config.ADMIN_IDS))
async def process_batch(message: Message, state: FSMContext, bot: Bot):
    text_content = ""
    if message.document:
        if not message.document.file_name.endswith('.txt'):
            await message.answer("❌ Жду только .txt файл", reply_markup=back_to_admin())
            return
        status_msg = await message.answer("📥 Скачиваю файл...")
        file_io = io.BytesIO()
        await bot.download(message.document, destination=file_io)
        try:
            text_content = file_io.getvalue().decode('utf-8')
        except UnicodeDecodeError:
            await status_msg.edit_text("❌ Ошибка кодировки файла.")
            return
        await status_msg.delete()
    elif message.text:
        text_content = message.text
    else:
        await message.answer("❌ Нужен текст или файл.", reply_markup=back_to_admin())
        return

    links = re.findall(r'(vless://\S+|vmess://\S+|trojan://\S+|ss://\S+)', text_content)
    links = [link.strip() for link in links if link.strip()]

    if not links:
        await message.answer("⚠️ Валидные ссылки не найдены.", reply_markup=back_to_admin())
        return

    msg = await message.answer(f"⏳ Deep Analyzing {len(links)} links...")

    stats = {"added": 0, "err": 0, "checked": 0, "total": len(links), "is_finished": False}
    report = []

    queue = asyncio.Queue()
    for link in links:
        queue.put_nowait(link)

    connector = aiohttp.TCPConnector(limit=100)
    async with aiohttp.ClientSession(connector=connector, headers=VlessChecker.HEADERS) as session:

        async def worker():
            while True:
                try:
                    link = queue.get_nowait()
                except asyncio.QueueEmpty:
                    break

                try:
                    # Добавлен жесткий таймаут для воркера, хотя VlessChecker.process_subscription теперь тоже имеет таймаут
                    success, region, latency, err = await asyncio.wait_for(
                        VlessChecker.process_subscription(link, session=session),
                        timeout=15.0
                    )

                    if success:
                        try:
                            await SubRepo.add_subscription(vless_key=link, region=region, latency=latency)
                            stats["added"] += 1
                            report.append(f"✅ {region} ({latency}ms)")
                        except IntegrityError:
                            report.append(f"⚠️ Duplicate")
                    else:
                        stats["err"] += 1
                        report.append(f"❌ {err}")
                except asyncio.TimeoutError:
                    stats["err"] += 1
                    report.append("❌ Timeout Worker")
                except Exception:
                    stats["err"] += 1
                finally:
                    stats["checked"] += 1
                    queue.task_done()

        async def ui_updater():
            while not stats["is_finished"]:
                percent = int((stats["checked"] / stats["total"]) * 100)
                text = (
                    f"🔄 Импорт и проверка: {stats['checked']}/{stats['total']} ({percent}%)\n"
                    f"✅ Живых: {stats['added']}\n"
                    f"❌ Мертвых: {stats['err']}"
                )
                await safe_edit_text(msg, text)
                await asyncio.sleep(5.0)

        updater_task = asyncio.create_task(ui_updater())
        workers = [asyncio.create_task(worker()) for _ in range(30)] 
        await asyncio.gather(*workers)

        stats["is_finished"] = True
        updater_task.cancel()

    final_text = (
        f"🏁 <b>Импорт завершен</b>\n\n"
        f"✅ Добавлено: <b>{stats['added']}</b>\n"
        f"❌ Отклонено (Dead): <b>{stats['err']}</b>\n\n"
        f"<i>Последние добавленные:</i>\n" + "\n".join(report[-10:])
    )
    if len(final_text) > 4000: final_text = final_text[:4000] + "..."
    await safe_edit_text(msg, final_text, reply_markup=back_to_admin())
    await state.clear()

@router.callback_query(F.data == "admin_manage")
async def manage_regions(callback: CallbackQuery):
    regions = await SubRepo.get_regions()
    if not regions:
        await callback.answer("База пуста.", show_alert=True)
        return
    await callback.message.edit_text("📂 Выберите регион для редактирования:", reply_markup=regions_kb(regions, "manage_region"))

@router.callback_query(F.data.startswith("manage_region_"))
async def list_subs_in_region(callback: CallbackQuery):
    region = callback.data.split("manage_region_")[1]
    subs = await SubRepo.get_subs_by_region(region)
    await callback.message.edit_text(f"📂 Регион: <b>{region}</b>\nСписок ключей:", parse_mode="HTML", reply_markup=subs_list_kb(subs, region))

@router.callback_query(F.data.startswith("sub_detail_"))
async def show_sub_details(callback: CallbackQuery):
    sub_id = int(callback.data.split("sub_detail_")[1])
    sub = await SubRepo.get_sub_by_id(sub_id)
    if not sub:
        await callback.answer("Ключ не найден", show_alert=True)
        return

    status_emoji = "🟢 АКТИВЕН" if sub.is_active else "🔴 ОТКЛЮЧЕН"
    text = (
        f"🆔 ID: <code>{sub.id}</code>\n"
        f"Статус: <b>{status_emoji}</b>\n"
        f"🌍 Регион: {sub.region}\n"
        f"⚡️ Latency: {sub.latency_ms} ms\n\n"
        f"🔑 Конфиг:\n<pre>{sub.vless_key}</pre>"
    )
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=sub_control_kb(sub.id, sub.is_active, sub.region))

@router.callback_query(F.data.startswith("sub_toggle_"))
async def toggle_sub(callback: CallbackQuery):
    sub_id = int(callback.data.split("sub_toggle_")[1])
    sub = await SubRepo.get_sub_by_id(sub_id)
    if sub:
        await SubRepo.toggle_active(sub_id, sub.is_active)
        await show_sub_details(callback)

@router.callback_query(F.data.startswith("sub_delete_"))
async def delete_sub(callback: CallbackQuery):
    sub_id = int(callback.data.split("sub_delete_")[1])
    sub = await SubRepo.get_sub_by_id(sub_id)
    if sub:
        region = sub.region
        await SubRepo.delete_sub(sub_id)
        await callback.answer("✅ Удалено")
        callback.data = f"manage_region_{region}"
        await list_subs_in_region(callback)
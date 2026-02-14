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
from keyboards.admin import back_to_admin, regions_kb, subs_list_kb, sub_control_kb, confirm_delete_all_kb, confirm_delete_unknown_kb
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
        "ℹ️ <i>Используем пакетную проверку IP.</i>", 
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

    async def ui_updater():
        while not stats["is_finished"]:
            percent = int((stats["processed"] / total_hosts) * 100) if total_hosts > 0 else 0
            text = (
                f"🚀 <b>GeoIP Update: {percent}%</b>\n"
                f"✅ Исправлено ключей: {stats['fixed']}\n"
                f"📡 Проверено хостов: {stats['processed']}/{total_hosts}"
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
        f"🏁 <b>Обновление регионов завершено!</b>\n\n"
        f"✅ Обновлено ключей: <b>{stats['fixed']}</b>",
        reply_markup=back_to_admin()
    )

@router.callback_query(F.data == "admin_recheck")
async def recheck_all_subs(callback: CallbackQuery):
    msg = await callback.message.edit_text(
        "🚀 <b>Xray Core Recheck</b>\n"
        "<i>Запускаю проверку через реальное ядро Xray...</i>\n"
        "Это может занять время.", 
        parse_mode="HTML"
    )

    subs = await SubRepo.get_all_subscriptions_for_check()
    if not subs:
        await msg.edit_text("⚠️ База пуста.", reply_markup=back_to_admin())
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
                f"🔄 <b>Xray Check: {percent}%</b>\n"
                f"📡 Проверено: {stats['checked']}/{stats['total']}\n\n"
                f"🟢 <b>Живых: {stats['active_now']}</b>\n"
                f"💀 Умерло: {stats['died']}\n"
                f"🆙 Воскресло: {stats['revived']}"
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
        f"🏁 <b>Xray Recheck завершен!</b>\n\n"
        f"Всего ключей: <b>{stats['total']}</b>\n"
        f"🟢 <b>Активных: {stats['active_now']}</b>\n"
        f"💀 Мертвых: <b>{stats['died']}</b>\n"
        f"🆙 Воскресло: <b>{stats['revived']}</b>\n",
        reply_markup=back_to_admin()
    )

@router.callback_query(F.data == "admin_add")
async def start_add_subs(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        "📝 <b>Массовая загрузка (ТОЛЬКО VLESS)</b>\n\n"
        "Отправьте .txt файл или список ссылок.\n"
        "Каждая ссылка будет проверена через Xray перед добавлением.",
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

    links = re.findall(r'(vless://\S+)', text_content)
    links = [link.strip() for link in links if link.strip()]

    if not links:
        await message.answer("⚠️ VLESS ссылки не найдены.", reply_markup=back_to_admin())
        return

    msg = await message.answer(f"⏳ Xray Check: {len(links)} links...")

    stats = {"added": 0, "err": 0, "checked": 0, "total": len(links), "is_finished": False}
    report = []
    
    queue = asyncio.Queue()
    for link in links:
        queue.put_nowait(link)

    async def worker():
        while True:
            try:
                link = queue.get_nowait()
            except asyncio.QueueEmpty:
                break

            try:
                success, region, latency, ai_avail, err = await VlessChecker.process_subscription(link)

                if success:
                    # Используем Smart Add
                    added = await SubRepo.smart_add_subscription(
                        vless_key=link, 
                        region=region, 
                        latency=latency, 
                        ai_available=ai_avail
                    )
                    
                    if added:
                        stats["added"] += 1
                        report.append(f"✅ {region} ({latency}ms)")
                    else:
                        stats["err"] += 1
                        report.append(f"⚠️ Limit/Unknown: {region}")
                else:
                    stats["err"] += 1
                    report.append(f"❌ {err}")
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
                f"✅ Добавлено/Заменено: {stats['added']}\n"
                f"❌ Отклонено (Err/Limit): {stats['err']}"
            )
            await safe_edit_text(msg, text)
            await asyncio.sleep(3.0)

    updater_task = asyncio.create_task(ui_updater())
    workers = [asyncio.create_task(worker()) for _ in range(15)] 
    await asyncio.gather(*workers)

    stats["is_finished"] = True
    updater_task.cancel()

    final_text = (
        f"🏁 <b>Импорт завершен</b>\n\n"
        f"✅ Добавлено: <b>{stats['added']}</b>\n"
        f"❌ Отклонено: <b>{stats['err']}</b>\n"
        f"ℹ️ <i>Unknown регионы и лимит >100 отфильтрованы.</i>\n\n"
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
        await callback.message.edit_text("📂 База пуста, но вы можете проверить управление:", reply_markup=regions_kb([], "manage_region"))
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

@router.callback_query(F.data == "admin_delete_all")
async def ask_delete_all(callback: CallbackQuery):
    await callback.message.edit_text(
        "⚠️ <b>ОПАСНАЯ ЗОНА</b> ⚠️\n\n"
        "Вы собираетесь удалить <b>ВСЕ</b> ключи (подписки) из базы данных.\n"
        "Это действие необратимо!\n\n"
        "Вы точно уверены?",
        parse_mode="HTML",
        reply_markup=confirm_delete_all_kb()
    )

@router.callback_query(F.data == "admin_delete_all_confirm")
async def execute_delete_all(callback: CallbackQuery):
    await SubRepo.delete_all_subs()
    await callback.answer("🗑 Все ключи успешно удалены!", show_alert=True)
    await callback.message.edit_text("✅ База данных очищена.", reply_markup=back_to_admin())

@router.callback_query(F.data == "admin_delete_unknown")
async def ask_delete_unknown(callback: CallbackQuery):
    count = len(await SubRepo.get_unknown_regions_subs())
    if count == 0:
         await callback.answer("Нет ключей с Unknown регионом!", show_alert=True)
         return
         
    await callback.message.edit_text(
        f"⚠️ <b>Удаление Unknown</b>\n\n"
        f"Найдено ключей: <b>{count}</b>\n"
        "Вы хотите удалить все конфигурации с неопределенным регионом?",
        parse_mode="HTML",
        reply_markup=confirm_delete_unknown_kb()
    )

@router.callback_query(F.data == "admin_delete_unknown_confirm")
async def execute_delete_unknown(callback: CallbackQuery):
    await SubRepo.delete_unknown_subs()
    await callback.answer("🗑 Unknown ключи удалены!", show_alert=True)
    await callback.message.edit_text("✅ База очищена от Unknown регионов.", reply_markup=back_to_admin())
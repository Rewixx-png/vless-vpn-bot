import asyncio
import aiohttp
from aiogram import Router, F
from aiogram.types import CallbackQuery
from aiogram.fsm.context import FSMContext

from database.repo import SubRepo
from utils.checker import VlessChecker
from keyboards.admin import back_to_admin, recheck_menu_kb
from handlers.admin.utils import safe_edit_message

router = Router()

@router.callback_query(F.data == "admin_fix_regions")
async def fix_unknown_regions(callback: CallbackQuery, state: FSMContext):
    try:
        await callback.answer()
    except:
        pass

    status_msg = await callback.message.answer(
        "<blockquote>🌍 <b>Запуск Ultimate GeoIP Scan...</b>\n\n"
        "1. DNS & Local MMDB\n"
        "2. Parallel API Race\n"
        "3. 🧩 <b>IATA Heuristics</b> (Поиск кодов аэропортов)\n"
        "4. 📝 <b>Name Analysis</b> (Чтение названия конфига)\n"
        "5. 🧠 <b>TLD Fallback</b> (.ru, .de)\n\n"
        "⏳ Анализирую хосты...</blockquote>",
        parse_mode="HTML"
    )

    subs = await SubRepo.get_all_subscriptions_for_check()
    if not subs:
        await safe_edit_message(status_msg, "<blockquote>✅ <b>База пуста!</b></blockquote>")
        return

    # Filter for Unknown
    unknown_subs = [s for s in subs if "Unknown" in s.region or "UNK" in s.region or "Unk" in s.region]
    
    if not unknown_subs:
        await safe_edit_message(status_msg, "<blockquote>✅ <b>Нет Unknown регионов!</b>\nВсе ключи уже имеют флаги.</blockquote>")
        return

    # Group by Host, but keep Remark info
    # host -> remark
    hosts_data = [] 
    host_to_subs = {}
    
    for sub in unknown_subs:
        parsed = VlessChecker.parse_config(sub.vless_key)
        if parsed and parsed.get("host"):
            host = parsed["host"]
            remark = parsed.get("ps", "") # Get remark/name
            
            if host in ["127.0.0.1", "localhost"]:
                continue
                
            if host not in host_to_subs:
                host_to_subs[host] = []
                # Only add unique host to processing list
                hosts_data.append((host, remark))
                
            host_to_subs[host].append(sub)

    total_hosts = len(hosts_data)
    total_keys = len(unknown_subs)

    if total_hosts == 0:
        await safe_edit_message(status_msg, "<blockquote>⚠️ <b>Не найдено валидных хостов.</b></blockquote>")
        return

    await safe_edit_message(
        status_msg,
        f"<blockquote>🌍 <b>Ultimate Scan</b>\n\n"
        f"🔑 Проблемных ключей: <b>{total_keys}</b>\n"
        f"📡 Уникальных хостов: <b>{total_hosts}</b>\n\n"
        f"🚀 Запускаю полный спектр проверок...</blockquote>"
    )

    async with aiohttp.ClientSession() as session:
        # Pass host+remark tuples to batch processor
        results = await VlessChecker.get_regions_batch(hosts_data, session)

    updates = []
    fixed_count = 0
    failed_hosts = 0

    for host, _ in hosts_data:
        region = results.get(host)
        
        if region and "Unk" not in region:
            if host in host_to_subs:
                for sub in host_to_subs[host]:
                    updates.append({"id": sub.id, "region": region})
                    fixed_count += 1
        else:
            failed_hosts += 1

    if updates:
        chunk_size = 500
        for i in range(0, len(updates), chunk_size):
            chunk = updates[i:i + chunk_size]
            await SubRepo.batch_update_regions(chunk)

    final_text = (
        f"<blockquote>✅ <b>Scan завершен!</b>\n\n"
        f"📊 <b>Отчёт:</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"🔑 Обработано ключей: <b>{total_keys}</b>\n"
        f"📡 Хостов проверено: <b>{total_hosts}</b>\n"
        f"✅ Успешно определено: <b>{fixed_count}</b>\n"
        f"⚠️ Всё еще Unknown: <b>{total_keys - fixed_count}</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"ℹ️ <i>Применены методы: IP, DNS, API, IATA, Keywords, TLD.</i></blockquote>"
    )

    await safe_edit_message(status_msg, final_text)
    try:
        await status_msg.edit_reply_markup(reply_markup=back_to_admin())
    except:
        pass


@router.callback_query(F.data == "admin_recheck_regions_force")
async def force_recheck_regions(callback: CallbackQuery, state: FSMContext):
    try:
        await callback.answer()
    except:
        pass

    status_msg = await callback.message.answer(
        "<blockquote>🌍 <b>Force Recheck (Ultimate Mode)</b>\n\n"
        "1. DNS & Local MMDB\n"
        "2. Parallel API Race\n"
        "3. IATA / Name Keywords / TLD\n"
        "4. Обновление БД\n\n"
        "⏳ Ждите...</blockquote>",
        parse_mode="HTML"
    )

    subs = await SubRepo.get_active_subscriptions_for_check()
    if not subs:
        await safe_edit_message(status_msg, "<blockquote>⚠️ <b>Нет активных подписок.</b></blockquote>")
        return

    hosts_data = []
    host_to_subs = {}
    
    for sub in subs:
        parsed = VlessChecker.parse_config(sub.vless_key)
        if parsed and parsed.get("host"):
            host = parsed["host"]
            remark = parsed.get("ps", "")
            
            if host in ["127.0.0.1", "localhost"]:
                continue
            
            if host not in host_to_subs:
                host_to_subs[host] = []
                hosts_data.append((host, remark))
            
            host_to_subs[host].append(sub)

    total_hosts = len(hosts_data)
    total_keys = len(subs)

    await safe_edit_message(
        status_msg,
        f"<blockquote>🌍 <b>Deep Analysis</b>\n\n"
        f"🔑 Активных ключей: <b>{total_keys}</b>\n"
        f"📡 Уникальных хостов: <b>{total_hosts}</b>\n\n"
        f"🚀 Запускаю проверку (All Methods)...</blockquote>"
    )

    async with aiohttp.ClientSession() as session:
        results = await VlessChecker.get_regions_batch(hosts_data, session)

    updates = []
    changed_count = 0

    for host, _ in hosts_data:
        new_region = results.get(host)
        
        if new_region and "Unk" not in new_region:
            if host in host_to_subs:
                for sub in host_to_subs[host]:
                    if sub.region != new_region:
                        updates.append({"id": sub.id, "region": new_region})
                        changed_count += 1

    if updates:
        chunk_size = 500
        for i in range(0, len(updates), chunk_size):
            chunk = updates[i:i + chunk_size]
            await SubRepo.batch_update_regions(chunk)

    final_text = (
        f"<blockquote>✅ <b>Регионы актуализированы!</b>\n\n"
        f"📊 <b>Отчёт:</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"🔑 Всего активных: <b>{total_keys}</b>\n"
        f"📡 Хостов проверено: <b>{total_hosts}</b>\n"
        f"🔄 Изменили страну: <b>{changed_count}</b>\n"
        f"✅ Без изменений: <b>{total_keys - changed_count}</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"ℹ️ <i>Включен эвристический анализ имен и доменов.</i></blockquote>"
    )

    await safe_edit_message(status_msg, final_text)
    try:
        await status_msg.edit_reply_markup(reply_markup=recheck_menu_kb())
    except:
        pass
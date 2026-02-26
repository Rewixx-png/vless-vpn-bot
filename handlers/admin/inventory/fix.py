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
@router.callback_query(F.data == "admin_recheck_regions_force")
async def fix_regions_logic(callback: CallbackQuery, state: FSMContext):
    is_force = "force" in callback.data
    
    try: await callback.answer()
    except: pass

    title = "Ultimate GeoIP Scan" if not is_force else "Force Recheck Regions"
    status_msg = await callback.message.answer(
        f"<blockquote>🌍 <b>{title}</b>\n\n"
        "1. DNS & Local MMDB\n"
        "2. Parallel API Race\n"
        "3. Name/TLD Heuristics\n\n"
        "⏳ Анализирую хосты...</blockquote>",
        parse_mode="HTML"
    )

    if is_force:
        subs = await SubRepo.get_active_subscriptions_for_check()
    else:
        subs = await SubRepo.get_unknown_regions_subs()

    if not subs:
        await safe_edit_message(status_msg, "<blockquote>✅ <b>Нет ключей для проверки!</b></blockquote>")
        return

    # Extract unique hosts to check
    hosts_data = [] 
    seen_hosts = set()
    host_to_subs = {}
    
    for sub in subs:
        parsed = VlessChecker.parse_config(sub.vless_key)
        if parsed and parsed.get("host") or parsed.get("server"):
            host = parsed.get("host") or parsed.get("server")
            remark = parsed.get("ps", "") or parsed.get("name", "")
            
            if host in ["127.0.0.1", "localhost"]: continue
                
            if host not in seen_hosts:
                seen_hosts.add(host)
                hosts_data.append((host, remark))
            
            if host not in host_to_subs:
                host_to_subs[host] = []
            host_to_subs[host].append(sub)

    total_hosts = len(hosts_data)
    total_keys = len(subs)

    await safe_edit_message(
        status_msg,
        f"<blockquote>🌍 <b>{title}</b>\n\n"
        f"🔑 Ключей: <b>{total_keys}</b>\n"
        f"📡 Уникальных хостов: <b>{total_hosts}</b>\n\n"
        f"🚀 Отправка запросов к GeoIP провайдерам...</blockquote>"
    )

    # Use a new session to ensure clean state
    async with aiohttp.ClientSession() as session:
        # Calls the updated GeoIP logic
        results = await VlessChecker.get_regions_batch(hosts_data, session)

    updates = []
    fixed_count = 0
    
    for host, region in results.items():
        if not region or "Unk" in region:
            continue
            
        if host in host_to_subs:
            for sub in host_to_subs[host]:
                # In force mode, update even if different. In fix mode, update if UNK.
                if is_force:
                    if sub.region != region:
                        updates.append({"id": sub.id, "region": region})
                        fixed_count += 1
                else:
                    # Logic for "Fix Unknowns" - update if current DB is UNK
                    if "Unk" in sub.region or not sub.region:
                         updates.append({"id": sub.id, "region": region})
                         fixed_count += 1

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
        f"🔄 Обновлено в БД: <b>{fixed_count}</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"ℹ️ <i>Использованы API: IP-API, IPAPI.co, IP.SB + MMDB</i></blockquote>"
    )

    await safe_edit_message(status_msg, final_text)
    
    kb = recheck_menu_kb() if is_force else back_to_admin()
    try:
        await status_msg.edit_reply_markup(reply_markup=kb)
    except: pass
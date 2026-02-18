import asyncio
import aiohttp
from aiogram import Router, F
from aiogram.types import CallbackQuery
from aiogram.fsm.context import FSMContext

from database.repo import SubRepo
from utils.checker import VlessChecker
from keyboards.admin import back_to_admin
from handlers.admin.utils import admin_edit_or_answer, safe_edit_message

router = Router()

@router.callback_query(F.data == "admin_fix_regions")
async def fix_unknown_regions(callback: CallbackQuery, state: FSMContext):
    # Explicitly answer first to prevent timeout
    try:
        await callback.answer()
    except:
        pass

    await admin_edit_or_answer(
        callback,
        state,
        "<blockquote>🌍 <b>Нормализация геолокации</b>\n\n"
        "📡 Перевожу названия стран в формат (De, Us...)\n"
        "⚡ Проверяю ВСЕ серверы в базе\n"
        "🔄 Использую мульти-провайдеры (Robust Mode)\n"
        "⏳ Анализирую хосты...</blockquote>"
    )

    subs = await SubRepo.get_all_subscriptions_for_check()
    if not subs:
        await safe_edit_message(
            callback.message,
            "<blockquote>✅ <b>База пуста!</b>\n\n"
            "ℹ️ Нет серверов для обновления.</blockquote>",
            reply_markup=back_to_admin()
        )
        return

    host_to_subs = {}
    for sub in subs:
        parsed = VlessChecker.parse_config(sub.vless_key)
        if parsed and parsed.get("host"):
            host = parsed["host"]
            if host in ["127.0.0.1", "localhost"]:
                continue
            if host not in host_to_subs:
                host_to_subs[host] = []
            host_to_subs[host].append(sub)

    unique_hosts = list(host_to_subs.keys())
    total_hosts = len(unique_hosts)

    if total_hosts == 0:
        await safe_edit_message(
            callback.message,
            "<blockquote>⚠️ <b>Не найдено валидных хостов.</b></blockquote>",
            reply_markup=back_to_admin()
        )
        return

    await safe_edit_message(
        callback.message,
        f"<blockquote>🌍 <b>Нормализация геолокации</b>\n\n"
        f"📡 Уникальных IP/Доменов: <b>{total_hosts}</b>\n"
        f"🔄 Опрашиваю GeoIP базы (это займет время)...\n"
        f"⚡ 20 потоков...</blockquote>"
    )

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }

    async with aiohttp.ClientSession(headers=headers) as session:
        results = await VlessChecker.get_regions_batch(unique_hosts, session)

    updates = []
    fixed_count = 0
    failed_hosts = 0

    for host in unique_hosts:
        region = results.get(host)
        
        if region and "Unk" not in region:
            if host in host_to_subs:
                for sub in host_to_subs[host]:
                    if sub.region != region:
                        updates.append({"id": sub.id, "region": region})
                        fixed_count += 1
        else:
            failed_hosts += 1

    if updates:
        chunk_size = 500
        for i in range(0, len(updates), chunk_size):
            chunk = updates[i:i + chunk_size]
            await SubRepo.batch_update_regions(chunk)

    # Use safe_edit_message here instead of admin_edit_or_answer to avoid "query is too old"
    await safe_edit_message(
        callback.message,
        f"<blockquote>✅ <b>Геолокация обновлена!</b>\n\n"
        f"📊 <b>Отчёт:</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"📡 IP проверено: <b>{total_hosts}</b>\n"
        f"✅ Обновлено записей: <b>{fixed_count}</b>\n"
        f"⚠️ Не определилось: <b>{failed_hosts}</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"ℹ️ <i>Теперь названия стран в формате (De, Us).</i></blockquote>",
        reply_markup=back_to_admin()
    )

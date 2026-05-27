from aiogram import Router, F
from aiogram.types import CallbackQuery
from aiogram.fsm.context import FSMContext
from database.repo import SubRepo
from keyboards.admin import subs_list_kb, sub_control_kb
from handlers.admin.utils import admin_edit_or_answer

router = Router()

ITEMS_PER_PAGE = 20

@router.callback_query(F.data.startswith("manage_region_"))
async def list_subs_in_region(callback: CallbackQuery, state: FSMContext):
    if not callback.data:
        return
    data_part = callback.data.split("manage_region_")[1]
    
    if ":" in data_part:
        region, page_str = data_part.rsplit(":", 1)
        try:
            page = int(page_str)
        except ValueError:
            page = 0
    else:
        region = data_part
        page = 0

    all_subs = await SubRepo.get_subs_by_region(region)
    total_items = len(all_subs)
    
    if total_items == 0:
        await callback.answer("В этом регионе нет ключей", show_alert=True)
        return

    total_pages = (total_items + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE
    
    if page >= total_pages:
        page = total_pages - 1
    if page < 0:
        page = 0
        
    start_idx = page * ITEMS_PER_PAGE
    end_idx = start_idx + ITEMS_PER_PAGE
    
    current_subs = all_subs[start_idx:end_idx]
    
    text = (
        f"<blockquote>📂 Регион: <b>{region}</b>\n\n"
        f"Всего ключей: <b>{total_items}</b>\n"
        f"Страница: <b>{page + 1}/{total_pages}</b>\n\n"
        f"👇 Нажмите на ключ для управления.</blockquote>"
    )
    
    await admin_edit_or_answer(
        callback,
        state,
        text,
        reply_markup=subs_list_kb(
            current_subs,
            region,
            page,
            total_pages,
            index_offset=start_idx,
        )
    )

@router.callback_query(F.data.startswith("sub_detail_"))
async def show_sub_details(callback: CallbackQuery, state: FSMContext):
    if not callback.data:
        return
    try:
        sub_id = int(callback.data.split("sub_detail_")[1])
    except ValueError:
        await callback.answer("Invalid ID")
        return

    sub = await SubRepo.get_sub_by_id(sub_id)
    if not sub:
        await callback.answer("Ключ не найден (возможно удален)", show_alert=True)
        return

    status_emoji = "🟢 АКТИВЕН" if sub.is_active else "🔴 ОТКЛЮЧЕН"
    ai_status = "✅ Да" if sub.ai_available else "❌ Нет"
    no_ads_status = "✅ Да" if sub.no_ads else "❌ Нет"
    
    short_config = sub.vless_key
    if len(short_config) > 50:
        short_config = short_config[:25] + "..." + short_config[-25:]
    
    text = (
        f"<blockquote>🆔 ID: <code>{sub.id}</code>\n"
        f"🌍 Страна: {sub.region}\n"
        f"📶 Статус: <b>{status_emoji}</b>\n"
        f"⚡️ Скорость: {sub.speed_mbps:.1f} Mbps\n"
        f"🤖 AI доступ: {ai_status}\n"
        f"🛡 No-Ads: {no_ads_status}\n\n"
        f"🔑 <b>Конфиг (Full):</b>\n<pre>{sub.vless_key}</pre></blockquote>"
    )
    
    await admin_edit_or_answer(
        callback,
        state,
        text,
        reply_markup=sub_control_kb(sub.id, sub.is_active, sub.region)
    )

@router.callback_query(F.data.startswith("sub_toggle_"))
async def toggle_sub(callback: CallbackQuery, state: FSMContext):
    if not callback.data:
        return
    try:
        sub_id = int(callback.data.split("sub_toggle_")[1])
    except ValueError:
        return

    sub = await SubRepo.get_sub_by_id(sub_id)
    if sub:
        await SubRepo.toggle_active(sub_id, sub.is_active)
        callback.data = f"sub_detail_{sub_id}"
        await show_sub_details(callback, state)
    else:
        await callback.answer("Ключ не найден", show_alert=True)

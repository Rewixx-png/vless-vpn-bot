from aiogram import Router, F
from aiogram.types import CallbackQuery
from aiogram.fsm.context import FSMContext
from database.repo import SubRepo
from keyboards.admin import subs_list_kb, sub_control_kb
from handlers.admin.utils import admin_edit_or_answer

router = Router()

@router.callback_query(F.data.startswith("manage_region_"))
async def list_subs_in_region(callback: CallbackQuery, state: FSMContext):
    region = callback.data.split("manage_region_")[1]
    subs = await SubRepo.get_subs_by_region(region)
    
    await admin_edit_or_answer(
        callback,
        state,
        f"<blockquote>📂 Регион: <b>{region}</b>\n\n"
        f"Всего ключей: {len(subs)}\n"
        f"👇 Нажмите на ключ для управления.</blockquote>",
        reply_markup=subs_list_kb(subs, region)
    )

@router.callback_query(F.data.startswith("sub_detail_"))
async def show_sub_details(callback: CallbackQuery, state: FSMContext):
    sub_id = int(callback.data.split("sub_detail_")[1])
    sub = await SubRepo.get_sub_by_id(sub_id)
    if not sub:
        await callback.answer("Ключ не найден", show_alert=True)
        return

    status_emoji = "🟢 АКТИВЕН" if sub.is_active else "🔴 ОТКЛЮЧЕН"
    ai_status = "✅ Есть" if sub.ai_available else "❌ Нет"
    
    text = (
        f"<blockquote>🆔 ID: <code>{sub.id}</code>\n"
        f"🌍 Страна: {sub.region}\n"
        f"📶 Статус: <b>{status_emoji}</b>\n"
        f"⚡️ Пинг: {sub.latency_ms} ms\n"
        f"🤖 AI доступ: {ai_status}\n\n"
        f"🔑 <b>Конфиг:</b>\n<pre>{sub.vless_key}</pre></blockquote>"
    )
    await admin_edit_or_answer(
        callback,
        state,
        text,
        reply_markup=sub_control_kb(sub.id, sub.is_active, sub.region)
    )

@router.callback_query(F.data.startswith("sub_toggle_"))
async def toggle_sub(callback: CallbackQuery):
    sub_id = int(callback.data.split("sub_toggle_")[1])
    sub = await SubRepo.get_sub_by_id(sub_id)
    if sub:
        await SubRepo.toggle_active(sub_id, sub.is_active)
        await show_sub_details(callback, None)

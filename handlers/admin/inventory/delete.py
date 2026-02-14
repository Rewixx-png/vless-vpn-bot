from aiogram import Router, F
from aiogram.types import CallbackQuery
from database.repo import SubRepo
from keyboards.admin import confirm_delete_all_kb, confirm_delete_unknown_kb, confirm_delete_country_kb, regions_kb, back_to_admin
from handlers.admin.utils import safe_edit_message

# Абсолютный импорт для доступа к функции просмотра списка
from handlers.admin.inventory.view import list_subs_in_region

router = Router()

# --- Удаление одного ключа ---
@router.callback_query(F.data.startswith("sub_delete_"))
async def delete_sub(callback: CallbackQuery):
    sub_id = int(callback.data.split("sub_delete_")[1])
    sub = await SubRepo.get_sub_by_id(sub_id)
    if sub:
        region = sub.region
        await SubRepo.delete_sub(sub_id)
        await callback.answer("✅ Ключ удален")
        
        # Возврат к списку
        callback.data = f"manage_region_{region}"
        await list_subs_in_region(callback)

# --- Удаление всех ключей ---
@router.callback_query(F.data == "admin_delete_all")
async def ask_delete_all(callback: CallbackQuery):
    await safe_edit_message(
        callback.message,
        "<blockquote>⚠️ <b>ОПАСНАЯ ЗОНА</b> ⚠️\n\n"
        "Вы собираетесь удалить <b>ВСЕ</b> ключи (подписки) из базы данных.\n"
        "Это действие необратимо!\n\n"
        "Вы точно уверены?</blockquote>",
        reply_markup=confirm_delete_all_kb(),
        parse_mode="HTML"
    )

@router.callback_query(F.data == "admin_delete_all_confirm")
async def execute_delete_all(callback: CallbackQuery):
    await SubRepo.delete_all_subs()
    await callback.answer("🗑 Все ключи успешно удалены!", show_alert=True)
    await safe_edit_message(callback.message, "<blockquote>✅ База данных очищена.</blockquote>", reply_markup=back_to_admin(), parse_mode="HTML")

# --- Удаление Unknown ---
@router.callback_query(F.data == "admin_delete_unknown")
async def ask_delete_unknown(callback: CallbackQuery):
    count = len(await SubRepo.get_unknown_regions_subs())
    if count == 0:
         await callback.answer("Нет ключей с Unknown регионом!", show_alert=True)
         return
         
    await safe_edit_message(
        callback.message,
        f"<blockquote>⚠️ <b>Удаление Unknown</b>\n\n"
        f"Найдено ключей: <b>{count}</b>\n"
        "Вы хотите удалить все конфигурации с неопределенным регионом?</blockquote>",
        reply_markup=confirm_delete_unknown_kb(),
        parse_mode="HTML"
    )

@router.callback_query(F.data == "admin_delete_unknown_confirm")
async def execute_delete_unknown(callback: CallbackQuery):
    await SubRepo.delete_unknown_subs()
    await callback.answer("🗑 Unknown ключи удалены!", show_alert=True)
    await safe_edit_message(callback.message, "<blockquote>✅ База очищена от Unknown регионов.</blockquote>", reply_markup=back_to_admin(), parse_mode="HTML")

# --- Удаление Страны ---
@router.callback_query(F.data.startswith("ask_delete_country_"))
async def ask_delete_country(callback: CallbackQuery):
    region = callback.data.split("ask_delete_country_")[1]
    count = await SubRepo.count_by_region(region)
    
    await safe_edit_message(
        callback.message,
        f"<blockquote>🗑 <b>Удаление страны: {region}</b>\n\n"
        f"В этой стране найдено ключей: <b>{count}</b>\n\n"
        "⚠️ Вы уверены, что хотите удалить ВСЕ ключи этого региона?</blockquote>",
        reply_markup=confirm_delete_country_kb(region),
        parse_mode="HTML"
    )

@router.callback_query(F.data.startswith("confirm_del_country_"))
async def execute_delete_country(callback: CallbackQuery):
    region = callback.data.split("confirm_del_country_")[1]
    
    await SubRepo.delete_subs_by_region(region)
    
    await callback.answer(f"🗑 Все ключи {region} удалены!", show_alert=True)
    
    regions = await SubRepo.get_regions()
    await safe_edit_message(
        callback.message,
        "<blockquote>📂 <b>Управление регионами</b>\n\n"
        "Список обновлен.</blockquote>",
        reply_markup=regions_kb(regions, "manage_region"),
        parse_mode="HTML"
    )

from aiogram import Router, F
from aiogram.types import CallbackQuery
from database.repo import SubRepo
from keyboards.admin import regions_kb

router = Router()

@router.callback_query(F.data == "admin_manage")
async def manage_regions(callback: CallbackQuery):
    regions = await SubRepo.get_regions()
    if not regions:
        await callback.answer("База пуста.", show_alert=True)
        await callback.message.edit_text(
            "<blockquote>📂 <b>Управление базой</b>\n\n"
            "База пуста. Загрузите ключи.</blockquote>", 
            reply_markup=regions_kb([], "manage_region"),
            parse_mode="HTML"
        )
        return
        
    await callback.message.edit_text(
        "<blockquote>📂 <b>Управление регионами</b>\n\n"
        "Выберите страну для просмотра ключей или удаления.</blockquote>",
        reply_markup=regions_kb(regions, "manage_region"),
        parse_mode="HTML"
    )
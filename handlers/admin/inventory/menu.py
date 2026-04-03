from aiogram import Router, F
from aiogram.types import CallbackQuery
from aiogram.fsm.context import FSMContext
from database.repo import SubRepo
from keyboards.admin import regions_kb
from handlers.admin.utils import admin_edit_or_answer

router = Router()

@router.callback_query(F.data == "admin_manage")
async def manage_regions(callback: CallbackQuery, state: FSMContext):
    regions = await SubRepo.get_regions()
    if not regions:
        await callback.answer("База пуста.", show_alert=True)
        await admin_edit_or_answer(
            callback,
            state,
            "<blockquote>📂 <b>Управление базой</b>\n\n"
            "База пуста. Загрузите ключи.</blockquote>",
            reply_markup=regions_kb([], "manage_region")
        )
        return
        
    await admin_edit_or_answer(
        callback,
        state,
        "<blockquote>📂 <b>Управление регионами</b>\n\n"
        "Выберите страну для просмотра ключей или удаления.\n"
        "Для массовой отправки в ЧС используйте кнопку «☑️ Массовый ЧС».</blockquote>",
        reply_markup=regions_kb(regions, "manage_region")
    )

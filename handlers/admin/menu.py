from aiogram import Router, F
from aiogram.types import CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.exceptions import TelegramBadRequest
from config import config
from keyboards.admin import main_admin_kb

router = Router()

@router.callback_query(F.data == "admin_home")
async def admin_dashboard(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id not in config.ADMIN_IDS:
        return
    await state.clear()
    
    text = (
        "🛠 <b>Control Panel</b>\n"
        "Управление ботом и серверами."
    )
    
    try:
        # Пытаемся отредактировать сообщение (сработает, если переход внутри админки: Текст -> Текст)
        await callback.message.edit_text(
            text,
            parse_mode="HTML",
            reply_markup=main_admin_kb()
        )
    except TelegramBadRequest:
        # Если ловим ошибку (например, переход из Юзер-меню: Видео -> Текст),
        # то удаляем старое медиа-сообщение и отправляем новое текстовое.
        try:
            await callback.message.delete()
        except:
            pass
        
        await callback.message.answer(
            text,
            parse_mode="HTML",
            reply_markup=main_admin_kb()
        )
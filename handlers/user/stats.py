from aiogram import Router, F
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.context import FSMContext
from database.repo import StatsRepo
from keyboards.user import back_to_home
from handlers.user.start import edit_or_answer

router = Router()

@router.callback_query(F.data == "public_stats")
async def show_public_network_stats(callback: CallbackQuery, state: FSMContext):
    if not isinstance(callback.message, Message):
        return
    stats = await StatsRepo.get_network_stats()
    
    regions_text = stats['regions_list']
    if isinstance(regions_text, str):
        if len(regions_text) > 800:
            regions_text = regions_text[:800] + "\n... и другие"
    else:
        regions_text = str(regions_text)

    text = (
        "<b>🌐 Статус сети</b>\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        f"🟢 Серверов онлайн: <b>{stats['active']}</b>  |  🌍 Локаций: <b>{stats['regions_count']}</b>\n\n"
        f"<b>Покрытие по странам:</b>\n"
        f"<pre>{regions_text}</pre>"
    )
    
    await edit_or_answer(callback.message, text, back_to_home(), state, media_url="video")
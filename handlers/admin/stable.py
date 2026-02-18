from aiogram import Router, F
from aiogram.types import CallbackQuery
from aiogram.fsm.context import FSMContext
from database.repo import SubRepo
from keyboards.admin import stable_list_kb
from handlers.admin.utils import admin_edit_or_answer

router = Router()

@router.callback_query(F.data == "admin_stable_list")
async def show_stable_list(callback: CallbackQuery, state: FSMContext):
    candidates = await SubRepo.get_candidates_for_stability(limit=20)
    
    if not candidates:
        await admin_edit_or_answer(
            callback,
            state,
            "<blockquote>🛡 <b>Stable List</b>\n\nНет кандидатов (проверок не было или все нестабильны).</blockquote>",
            reply_markup=stable_list_kb([])
        )
        return

    lines = []
    for i, sub in enumerate(candidates, 1):
        # Calculate time based on streak
        # 1 streak point = 10 minutes (approx check interval)
        total_mins = sub.stability_streak * 10
        hours = total_mins // 60
        mins = total_mins % 60
        
        # Region format: 🇫🇮 Fi
        region = sub.region if sub.region else "UNK"
        
        lines.append(f"{i}. {region} {sub.id} – {hours}ч. {mins}мин.")

    list_text = "\n".join(lines)
    
    text = (
        f"<blockquote>🛡 <b>Stable Candidates (TOP 20)</b>\n\n"
        f"{list_text}\n\n"
        f"ℹ️ <i>Тайминг рассчитывается на основе непрерывных проверок (1 тик ≈ 10 мин).</i></blockquote>"
    )

    await admin_edit_or_answer(
        callback,
        state,
        text,
        reply_markup=stable_list_kb(candidates)
    )
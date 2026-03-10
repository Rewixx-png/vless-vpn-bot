import json

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.filters import StateFilter
from aiogram.fsm.state import State, StatesGroup

from config import config
from database.repo import SourceRepo, SystemRepo
from keyboards.admin import back_to_admin, sources_list_kb
from handlers.admin.utils import admin_edit_or_answer
from tasks import run_collector_task

router = Router()


class SourceStates(StatesGroup):
    waiting_for_url = State()


@router.callback_query(F.data == "admin_sources")
async def show_sources_menu(callback: CallbackQuery, state: FSMContext):
    sources = await SourceRepo.get_all_sources()
    enabled_count = len([s for s in sources if s.is_enabled])

    last_run_raw = await SystemRepo.get_config("collector_last_run")
    last_run_block = ""
    if last_run_raw:
        try:
            last = json.loads(last_run_raw)
            last_run_block = (
                "\n\n<b>Последний запуск collector:</b>\n"
                f"• Sources: {last.get('sources_used', 0)} (custom: {last.get('custom_sources_used', 0)})\n"
                f"• Processed: {last.get('processed', 0)}\n"
                f"• Added: {last.get('added', 0)} | Rejected: {last.get('rejected', 0)}\n"
                f"• Cleaned(dead): {last.get('cleaned', 0)}"
            )
        except Exception:
            pass

    text = (
        "<b>🔗 Управление источниками</b>\n\n"
        "Здесь вы можете добавить ссылки на подписки (доноры).\n"
        "Бот будет автоматически скачивать оттуда ключи и проверять их.\n\n"
        f"Всего источников: {len(sources)}\n"
        f"Включено: {enabled_count}\n"
        "Базовые источники: 2 (встроенные)"
        f"{last_run_block}"
    )
    await admin_edit_or_answer(
        callback, state, text, reply_markup=sources_list_kb(sources)
    )


@router.callback_query(F.data == "src_add")
async def ask_source_url(callback: CallbackQuery, state: FSMContext):
    await admin_edit_or_answer(
        callback,
        state,
        "✍️ <b>Отправьте ссылку на подписку:</b>\n\nПример: <code>https://example.com/sub/123</code>",
        reply_markup=back_to_admin(),
    )
    await state.set_state(SourceStates.waiting_for_url)


@router.message(
    StateFilter(SourceStates.waiting_for_url), F.from_user.id.in_(config.ADMIN_IDS)
)
async def add_source(message: Message, state: FSMContext):
    url = message.text.strip()
    if not url.startswith("http"):
        await message.answer(
            "❌ Ссылка должна начинаться с http", reply_markup=back_to_admin()
        )
        return

    success = await SourceRepo.add_source(url, title=None)
    if success:
        await message.answer("✅ Источник добавлен!", reply_markup=back_to_admin())
        await state.clear()
        sources = await SourceRepo.get_all_sources()
        await message.answer("🔗 Источники", reply_markup=sources_list_kb(sources))
    else:
        await message.answer("⚠️ Такой источник уже есть.", reply_markup=back_to_admin())


@router.callback_query(F.data.startswith("src_toggle_"))
async def toggle_source(callback: CallbackQuery):
    src_id = int(callback.data.split("src_toggle_")[1])
    new_state = await SourceRepo.toggle_source(src_id)
    sources = await SourceRepo.get_all_sources()
    await callback.message.edit_reply_markup(reply_markup=sources_list_kb(sources))
    state_text = "включен" if new_state else "выключен"
    await callback.answer(f"Источник {state_text}")


@router.callback_query(F.data.startswith("src_del_"))
async def delete_source(callback: CallbackQuery):
    src_id = int(callback.data.split("src_del_")[1])
    await SourceRepo.delete_source(src_id)
    sources = await SourceRepo.get_all_sources()
    await callback.message.edit_reply_markup(reply_markup=sources_list_kb(sources))
    await callback.answer("Источник удален")


@router.callback_query(F.data == "src_force_run")
async def force_run_collector(callback: CallbackQuery):
    task = run_collector_task.delay()
    await callback.answer("✅ Collector запущен", show_alert=False)

    sources = await SourceRepo.get_all_sources()
    enabled_count = len([s for s in sources if s.is_enabled])

    text = (
        "<b>🚀 Collector запущен вручную</b>\n\n"
        f"Task ID: <code>{task.id}</code>\n"
        f"Включенных кастом-источников: {enabled_count}\n"
        "Базовых источников: 2\n\n"
        "Следите за итогом в этом меню (блок 'Последний запуск collector') и в топике INFO."
    )
    await admin_edit_or_answer(
        callback, None, text, reply_markup=sources_list_kb(sources)
    )

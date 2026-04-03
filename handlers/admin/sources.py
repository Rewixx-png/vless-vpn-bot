import json
from redis import Redis

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
from celery_app import app as celery_app
from utils.reporter import Reporter
from utils.collector import FIXED_SOURCE_URLS

router = Router()


class SourceStates(StatesGroup):
    waiting_for_url = State()


def _get_collector_runtime_status() -> dict:
    active_ids = []
    reserved_ids = []
    queue_len = 0

    try:
        inspector = celery_app.control.inspect(timeout=1)
        active_data = inspector.active() or {}
        reserved_data = inspector.reserved() or {}

        for tasks in active_data.values():
            for task in tasks:
                if task.get("name") == "tasks.run_collector_task":
                    active_ids.append(task.get("id", "unknown"))

        for tasks in reserved_data.values():
            for task in tasks:
                if task.get("name") == "tasks.run_collector_task":
                    reserved_ids.append(task.get("id", "unknown"))
    except Exception:
        pass

    try:
        redis_client = Redis.from_url(config.REDIS_URL, decode_responses=True)
        queue_len = int(redis_client.llen("low_priority"))
        redis_client.close()
    except Exception:
        queue_len = 0

    return {
        "active_ids": active_ids,
        "reserved_ids": reserved_ids,
        "queue_len": queue_len,
    }


@router.callback_query(F.data == "admin_sources")
async def show_sources_menu(callback: CallbackQuery, state: FSMContext):
    sources = await SourceRepo.get_all_sources()
    enabled_count = len([s for s in sources if s.is_enabled])
    fixed_total = len(FIXED_SOURCE_URLS)
    fixed_set = set(FIXED_SOURCE_URLS)
    enabled_urls = [s.url for s in sources if s.is_enabled]
    accepted_custom = len([url for url in enabled_urls if url in fixed_set])
    ignored_custom = max(enabled_count - accepted_custom, 0)
    runtime = _get_collector_runtime_status()

    last_run_raw = await SystemRepo.get_config("collector_last_run")
    last_run_block = ""
    if last_run_raw:
        try:
            last = json.loads(last_run_raw)

            last_sources_used = int(last.get("sources_used", 0) or 0)
            last_fixed_total = int(last.get("fixed_sources_total", fixed_total) or 0)
            last_custom_enabled = int(
                last.get("custom_sources_enabled", last.get("custom_sources_used", 0))
                or 0
            )
            last_custom_accepted = int(
                last.get("custom_sources_accepted", last.get("custom_sources_used", 0))
                or 0
            )
            last_custom_ignored = int(
                last.get(
                    "custom_sources_ignored",
                    max(last_custom_enabled - last_custom_accepted, 0),
                )
                or 0
            )

            last_run_block = (
                "\n\n<b>Последний запуск collector:</b>\n"
                f"• Fetch URL-ов: {last_sources_used}\n"
                f"• Fixed: {last_fixed_total} | custom enabled: {last_custom_enabled}\n"
                f"• Custom accepted: {last_custom_accepted} | ignored: {last_custom_ignored}\n"
                f"• Processed: {last.get('processed', 0)}\n"
                f"• Added: {last.get('added', 0)} | Rejected: {last.get('rejected', 0)}\n"
                f"• Cleaned(dead): {last.get('cleaned', 0)}"
            )
        except Exception:
            pass

    text = (
        "<b>🔗 Управление источниками</b>\n\n"
        "Здесь вы можете хранить кастомные ссылки (доноры).\n"
        "Collector берет встроенный fixed-список и дополнительно учитывает только совместимые кастомные URL.\n\n"
        f"Кастом в БД: {len(sources)}\n"
        f"Кастом включено: {enabled_count} (accepted: {accepted_custom}, ignored: {ignored_custom})\n"
        f"Fixed встроенные: {fixed_total} (используются всегда)\n"
        f"Итог базовых URL для сборки: {fixed_total}\n"
        f"Collector active: {len(runtime['active_ids'])} | reserved: {len(runtime['reserved_ids'])}\n"
        f"Очередь low_priority: {runtime['queue_len']}"
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
        "✍️ <b>Отправьте ссылку на подписку:</b>\n\n"
        "Пример: <code>https://example.com/sub/123</code>\n"
        "Или папку GitHub: <code>https://github.com/user/repo/tree/main/path</code>\n"
        "(бот автоматически найдет все <code>.txt</code> внутри и заберет vless)",
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
        is_accepted = url in set(FIXED_SOURCE_URLS)
        await Reporter.send_admin_action(
            message.bot,
            f"Source added by admin {message.from_user.id}: {url}",
        )
        if is_accepted:
            add_text = "✅ Источник добавлен и будет учитываться collector."
        else:
            add_text = (
                "⚠️ Источник добавлен в БД, но сейчас игнорируется collector "
                "(не в fixed-allowlist)."
            )
        await message.answer(add_text, reply_markup=back_to_admin())
        await state.clear()
        sources = await SourceRepo.get_all_sources()
        await message.answer("🔗 Источники", reply_markup=sources_list_kb(sources))
    else:
        await Reporter.send_admin_action(
            message.bot,
            f"Source add skipped (duplicate) by admin {message.from_user.id}: {url}",
        )
        await message.answer("⚠️ Такой источник уже есть.", reply_markup=back_to_admin())


@router.callback_query(F.data.startswith("src_toggle_"))
async def toggle_source(callback: CallbackQuery):
    src_id = int(callback.data.split("src_toggle_")[1])
    new_state = await SourceRepo.toggle_source(src_id)
    await Reporter.send_admin_action(
        callback.bot,
        f"Source toggle by admin {callback.from_user.id}: source_id={src_id}, enabled={new_state}",
    )
    sources = await SourceRepo.get_all_sources()
    await callback.message.edit_reply_markup(reply_markup=sources_list_kb(sources))
    state_text = "включен" if new_state else "выключен"
    await callback.answer(f"Источник {state_text}")


@router.callback_query(F.data.startswith("src_del_"))
async def delete_source(callback: CallbackQuery):
    src_id = int(callback.data.split("src_del_")[1])
    await SourceRepo.delete_source(src_id)
    await Reporter.send_admin_action(
        callback.bot,
        f"Source deleted by admin {callback.from_user.id}: source_id={src_id}",
    )
    sources = await SourceRepo.get_all_sources()
    await callback.message.edit_reply_markup(reply_markup=sources_list_kb(sources))
    await callback.answer("Источник удален")


@router.callback_query(F.data == "src_force_run")
async def force_run_collector(callback: CallbackQuery):
    runtime = _get_collector_runtime_status()
    task = run_collector_task.delay()
    await Reporter.send_admin_action(
        callback.bot,
        f"Collector manual run queued by admin {callback.from_user.id}: task_id={task.id}",
    )
    await callback.answer("✅ Collector поставлен в очередь", show_alert=False)

    sources = await SourceRepo.get_all_sources()
    enabled_count = len([s for s in sources if s.is_enabled])
    fixed_total = len(FIXED_SOURCE_URLS)
    fixed_set = set(FIXED_SOURCE_URLS)
    enabled_urls = [s.url for s in sources if s.is_enabled]
    accepted_custom = len([url for url in enabled_urls if url in fixed_set])
    ignored_custom = max(enabled_count - accepted_custom, 0)

    active_note = ""
    if runtime["active_ids"]:
        active_note = (
            "\n<b>Сейчас уже идет другой collector-task:</b>\n"
            f"<code>{runtime['active_ids'][0]}</code>\n"
            "Ваш запуск начнется после его завершения."
        )

    text = (
        "<b>🚀 Collector запущен вручную</b>\n\n"
        f"Task ID: <code>{task.id}</code>\n"
        f"Fixed встроенные: {fixed_total}\n"
        f"Кастом включено: {enabled_count} (accepted: {accepted_custom}, ignored: {ignored_custom})\n"
        f"Итог базовых URL для сборки: {fixed_total}\n\n"
        "Этот экран не обновляется автоматически.\n"
        "Нажмите '🔄 Обновить статус' внизу для актуальных данных."
        f"{active_note}\n\n"
        "Следите за итогом в блоке 'Последний запуск collector' и в топике INFO."
    )
    await admin_edit_or_answer(
        callback, None, text, reply_markup=sources_list_kb(sources)
    )

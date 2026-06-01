import shutil
import asyncio
import asyncpg
import urllib.parse
from aiogram import Router, F
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.context import FSMContext
from config import config
from database.repo.system import SystemRepo
from keyboards.admin import main_admin_kb
from handlers.admin.utils import admin_edit_or_answer
from tasks import run_collector_task

router = Router()


def _disk_info() -> tuple[str, str]:
    try:
        total, used, free = shutil.disk_usage("/")
        pct = used / total * 100
        free_gb = free / (1024 ** 3)
        warn = "🔴" if pct >= 90 else ("🟡" if pct >= 75 else "🟢")
        return f"{pct:.0f}% ({free_gb:.1f}GB free)", warn
    except Exception:
        return "N/A", "⚪"


async def _db_ping() -> str:
    try:
        _url = config.DB_URL.replace("postgresql+asyncpg://", "postgresql://", 1)
        _parsed = urllib.parse.urlparse(_url)
        conn = await asyncio.wait_for(
            asyncpg.connect(
                host=_parsed.hostname or "127.0.0.1",
                port=_parsed.port or 5432,
                user=urllib.parse.unquote(_parsed.username or ""),
                password=urllib.parse.unquote(_parsed.password or ""),
                database=(_parsed.path or "").lstrip("/"),
            ),
            timeout=2.0,
        )
        await conn.close()
        return "🟢 Online"
    except Exception:
        return "🔴 Offline"


@router.callback_query(F.data == "admin_home")
async def admin_dashboard(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id not in config.ADMIN_IDS:
        return

    enabled_str = await SystemRepo.get_config("collector_enabled")
    collector_active = enabled_str != "false"

    disk_str, disk_icon = _disk_info()
    db_status = await _db_ping()

    coll_status = "🟢 Активен" if collector_active else "🔴 Выключен"

    text = (
        "<b>⚙️ Панель Администратора</b>\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        "<b>🖥 Система:</b>\n"
        f"  💾 Диск: {disk_icon} {disk_str}\n"
        f"  🗄 PostgreSQL: {db_status}\n"
        f"  🔄 Коллектор: {coll_status}\n\n"
        "<i>Выберите раздел управления ниже.</i>"
    )

    await admin_edit_or_answer(callback, state, text, reply_markup=main_admin_kb(collector_active))


@router.callback_query(F.data == "toggle_collector")
async def toggle_collector(callback: CallbackQuery, state: FSMContext):
    if not callback.from_user or callback.from_user.id not in config.ADMIN_IDS:
        await callback.answer("⛔ Доступ запрещён", show_alert=True)
        return
    if not isinstance(callback.message, Message):
        return
    enabled_str = await SystemRepo.get_config("collector_enabled")
    is_enabled = enabled_str != "false"
    
    new_state = not is_enabled
    await SystemRepo.set_config("collector_enabled", "true" if new_state else "false")
    
    status_text = "🟢 ВКЛЮЧЕН" if new_state else "🔴 ВЫКЛЮЧЕН"
    await callback.answer(f"Сборщик серверов {status_text}", show_alert=True)
    
    if new_state:
        getattr(run_collector_task, "delay")()
        await callback.message.answer("🚀 <b>Коллектор запущен принудительно!</b>\nРезультаты появятся в логах.", parse_mode="HTML")
    
    await admin_dashboard(callback, state)

import io
import re
import asyncio
from typing import Any, cast
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext

from config import config
from database.repo import SubRepo
from utils.checker import VlessChecker
from keyboards.admin import back_to_admin
from handlers.admin.states import AdminStates
from utils.batch_processor import SmartBatchProcessor
from handlers.admin.utils import admin_edit_or_answer, safe_edit_message

router = Router()

@router.callback_query(F.data == "admin_add")
async def start_add_subs(callback: CallbackQuery, state: FSMContext):
    await admin_edit_or_answer(
        callback,
        state,
        "<blockquote>📝 <b>Массовая загрузка (ТОЛЬКО VLESS)</b>\n\n"
        "Отправьте .txt файл или список ссылок.\n"
        "Каждая ссылка будет проверена через Xray перед добавлением.</blockquote>",
        reply_markup=back_to_admin()
    )
    await state.set_state(AdminStates.waiting_for_subs)

@router.message(StateFilter(AdminStates.waiting_for_subs), F.fromuser.id.in_(config.ADMIN_IDS) if hasattr(F, 'fromuser') else F.from_user.id.in_(config.ADMIN_IDS))
async def process_batch(message: Message, state: FSMContext, bot: Bot):
    text_content = ""
    
    if message.document:
        if not message.document.file_name or not message.document.file_name.endswith('.txt'):
            await message.answer(
                "<blockquote>❌ Жду только .txt файл</blockquote>",
                reply_markup=back_to_admin(),
                parse_mode="HTML"
            )
            return
        
        status_msg = await message.answer(
            "<blockquote>📥 Скачиваю файл...</blockquote>",
            parse_mode="HTML"
        )
        
        file_io = io.BytesIO()
        await bot.download(message.document, destination=file_io)
        
        try:
            text_content = file_io.getvalue().decode('utf-8')
        except UnicodeDecodeError:
            await status_msg.edit_text(
                "<blockquote>❌ Ошибка кодировки файла.</blockquote>",
                parse_mode="HTML"
            )
            return
        
        await status_msg.delete()
        
    elif message.text:
        text_content = message.text
    else:
        await message.answer(
            "<blockquote>❌ Нужен текст или файл.</blockquote>",
            reply_markup=back_to_admin(),
            parse_mode="HTML"
        )
        return

    links = re.findall(r'(vless://[^\s\n<>"]+)', text_content)
    links = [link.strip() for link in links if link.strip()]

    if not links:
        await message.answer(
            "<blockquote>⚠️ VLESS ссылки не найдены.</blockquote>",
            reply_markup=back_to_admin(),
            parse_mode="HTML"
        )
        return

    msg = await message.answer(
        f"<blockquote>🔍 <b>Анализ ссылок...</b>\n\n"
        f"📋 Найдено: <b>{len(links)}</b>\n"
        f"⏳ Запускаю проверку...</blockquote>",
        parse_mode="HTML"
    )

    results_log =[]
    
    start_time = asyncio.get_event_loop().time()
    
    processor = SmartBatchProcessor(
        worker_count=20,
        progress_interval=3.0,
        rate_limit=50
    )

    async def process_link(link: str):
        try:
            is_alive, region, latency, speed_mbps, ai_avail, no_ads, err, updated_link = await VlessChecker.process_subscription(link)
            
            if not is_alive and err and str(err).startswith("SYS_ERR"):
                return (False, {"status": "failed", "error": "System Overload. Try again later."})
                
            if is_alive:
                parsed = VlessChecker.parse_config(updated_link if updated_link else link)
                if not parsed:
                    return (False, {"status": "failed", "error": "Invalid config format"})

                jitter_host = str(parsed.get("server", "") or "").strip()
                jitter_port = int(parsed.get("port", 0) or 0)
                if not jitter_host or jitter_port < 1 or jitter_port > 65535:
                    return (False, {"status": "failed", "error": "Invalid host/port"})

                jitter_ok, jitter_ms, _ = await VlessChecker.measure_tcp_jitter(
                    host=jitter_host,
                    port=jitter_port,
                )

                if not jitter_ok:
                    return (False, {"status": "failed", "error": "Jitter check failed"})

                if int(jitter_ms) > 20:
                    return (
                        False,
                        {
                            "status": "failed",
                            "error": f"High jitter: {int(jitter_ms)}ms",
                        },
                    )

                if float(speed_mbps or 0.0) < 10.0:
                    return (
                        False,
                        {
                            "status": "failed",
                            "error": f"Low speed: {float(speed_mbps or 0.0):.2f} Mbps",
                        },
                    )

                added = await SubRepo.smart_add_subscription(
                    vless_key=updated_link,
                    region=region,
                    latency=latency,
                    speed_mbps=speed_mbps,
                    ai_available=ai_avail,
                    no_ads=no_ads
                )
                if added:
                    return (True, {"status": "added", "region": region, "speed_mbps": speed_mbps})
                else:
                    return (True, {"status": "limited", "region": region})
            else:
                return (False, {"status": "failed", "error": err})
        except Exception as e:
            return (False, {"status": "error", "error": str(e)})

    async def on_progress(completed: int, total: int, success: int, failed: int, workers: int):
        percent = int((completed / total) * 100)
        
        await safe_edit_message(
            msg,
            f"<blockquote>⚡ <b>Массовая проверка</b>\n\n"
            f"📊 <b>{completed} / {total}</b> | <b>{percent}%</b>\n"
            f"✅ Добавлено: <b>{success}</b>\n"
            f"❌ Отклонено: <b>{failed}</b>\n"
            f"🔄 Проверяю...</blockquote>"
        )

    result = await processor.process(
        items=links,
        process_func=cast(Any, process_link),
        on_progress=cast(Any, on_progress)
    )

    added_count = 0
    failed_count = result.failed
    
    for item in result.items:
        res = item.get("result", {})
        if isinstance(res, dict):
            status = res.get("status")
            if status == "added":
                added_count += 1
                results_log.append(f"✅ {res.get('region')} ({res.get('speed_mbps')}Mb/s)")
            elif status == "failed":
                if len(links) < 50:
                    results_log.append(f"❌ {res.get('error')}")

    final_text = (
        f"<blockquote>🏁 <b>Импорт завершён!</b>\n\n"
        f"📊 <b>Итоговый отчёт:</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"✅ Успешно добавлено: <b>{added_count}</b>\n"
        f"❌ Отклонено/Недействительно: <b>{failed_count}</b>\n"
        f"📋 Всего обработано: <b>{len(links)}</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"<b>🔝 Лог (последние 10):</b>\n" + "\n".join(results_log[-10:]) + "</blockquote>"
    )
    
    if len(final_text) > 4000:
        final_text = final_text[:4000] + "..." + "</blockquote>"
    
    await safe_edit_message(msg, final_text, reply_markup=back_to_admin())
    await state.clear()

"""
Optimized batch add handler with progress tracking and batch updates.
"""
import io
import re
import asyncio
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
from handlers.admin.utils import safe_edit_message

router = Router()


@router.callback_query(F.data == "admin_add")
async def start_add_subs(callback: CallbackQuery, state: FSMContext):
    await safe_edit_message(
        callback.message,
        "<blockquote>📝 <b>Массовая загрузка (ТОЛЬКО VLESS)</b>\n\n"
        "Отправьте .txt файл или список ссылок.\n"
        "Каждая ссылка будет проверена через Xray перед добавлением.</blockquote>",
        reply_markup=back_to_admin(),
        parse_mode="HTML"
    )
    await state.set_state(AdminStates.waiting_for_subs)


@router.message(StateFilter(AdminStates.waiting_for_subs), F.from_user.id.in_(config.ADMIN_IDS))
async def process_batch(message: Message, state: FSMContext, bot: Bot):
    text_content = ""
    
    if message.document:
        if not message.document.file_name.endswith('.txt'):
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

    # Extract VLESS links
    links = re.findall(r'(vless://\S+)', text_content)
    links = [link.strip() for link in links if link.strip()]

    if not links:
        await message.answer(
            "<blockquote>⚠️ VLESS ссылки не найдены.</blockquote>",
            reply_markup=back_to_admin(),
            parse_mode="HTML"
        )
        return

    # Start processing
    msg = await message.answer(
        f"<blockquote>⏳ Xray Check: {len(links)} links...</blockquote>",
        parse_mode="HTML"
    )

    # Use SmartBatchProcessor for optimized processing
    processor = SmartBatchProcessor(
        worker_count=15,
        progress_interval=3.0,
        rate_limit=50  # Max 50 checks per second
    )

    results_log = []

    async def process_link(link: str):
        """Process single link"""
        try:
            is_alive, region, latency, ai_avail, err = await VlessChecker.process_subscription(link)

            if is_alive:
                added = await SubRepo.smart_add_subscription(
                    vless_key=link,
                    region=region,
                    latency=latency,
                    ai_available=ai_avail
                )

                if added:
                    results_log.append(f"✅ {region} ({latency}ms)")
                    return {"status": "added", "region": region, "latency": latency}
                else:
                    results_log.append(f"⚠️ Limit/Unknown: {region}")
                    return {"status": "limited", "region": region}
            else:
                results_log.append(f"❌ {err}")
                return {"status": "failed", "error": err}
                
        except Exception as e:
            results_log.append(f"❌ Error: {str(e)[:50]}")
            return {"status": "error", "error": str(e)}

    # Progress callback
    async def on_progress(completed: int, total: int, success: int, failed: int):
        percent = int((completed / total) * 100)
        await safe_edit_message(
            msg,
            f"<blockquote>🔄 Импорт и проверка: {completed}/{total} ({percent}%)\n"
            f"✅ Добавлено/Заменено: {success}\n"
            f"❌ Отклонено: {failed}</blockquote>"
        )

    # Process batch
    result = await processor.process(
        items=links,
        process_func=process_link,
        on_progress=on_progress
    )

    # Count results
    added_count = sum(1 for item in result.items if item["result"] and item["result"].get("status") == "added")
    failed_count = result.failed

    # Final message
    final_text = (
        f"<blockquote>🏁 <b>Импорт завершен</b>\n\n"
        f"✅ Добавлено: <b>{added_count}</b>\n"
        f"❌ Отклонено: <b>{failed_count}</b>\n"
        f"ℹ️ <i>Unknown регионы и лимит >100 отфильтрованы.</i>\n\n"
        f"<i>Последние добавленные:</i>\n" + "\n".join(results_log[-10:]) + "</blockquote>"
    )
    
    if len(final_text) > 4000:
        final_text = final_text[:4000] + "..." + "</blockquote>"
    
    await safe_edit_message(msg, final_text, reply_markup=back_to_admin())
    await state.clear()

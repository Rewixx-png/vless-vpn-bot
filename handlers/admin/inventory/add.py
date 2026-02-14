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

router = Router()

async def safe_edit_text(message: Message, text: str, reply_markup=None, parse_mode="HTML"):
    try:
        await message.edit_text(text, reply_markup=reply_markup, parse_mode=parse_mode)
    except: pass

@router.callback_query(F.data == "admin_add")
async def start_add_subs(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        "<blockquote>📝 <b>Массовая загрузка (ТОЛЬКО VLESS)</b>\n\n"
        "Отправьте .txt файл или список ссылок.\n"
        "Каждая ссылка будет проверена через Xray перед добавлением.</blockquote>",
        parse_mode="HTML",
        reply_markup=back_to_admin()
    )
    await state.set_state(AdminStates.waiting_for_subs)

@router.message(StateFilter(AdminStates.waiting_for_subs), F.from_user.id.in_(config.ADMIN_IDS))
async def process_batch(message: Message, state: FSMContext, bot: Bot):
    text_content = ""
    if message.document:
        if not message.document.file_name.endswith('.txt'):
            await message.answer("<blockquote>❌ Жду только .txt файл</blockquote>", reply_markup=back_to_admin(), parse_mode="HTML")
            return
        status_msg = await message.answer("<blockquote>📥 Скачиваю файл...</blockquote>", parse_mode="HTML")
        file_io = io.BytesIO()
        await bot.download(message.document, destination=file_io)
        try:
            text_content = file_io.getvalue().decode('utf-8')
        except UnicodeDecodeError:
            await status_msg.edit_text("<blockquote>❌ Ошибка кодировки файла.</blockquote>", parse_mode="HTML")
            return
        await status_msg.delete()
    elif message.text:
        text_content = message.text
    else:
        await message.answer("<blockquote>❌ Нужен текст или файл.</blockquote>", reply_markup=back_to_admin(), parse_mode="HTML")
        return

    links = re.findall(r'(vless://\S+)', text_content)
    links = [link.strip() for link in links if link.strip()]

    if not links:
        await message.answer("<blockquote>⚠️ VLESS ссылки не найдены.</blockquote>", reply_markup=back_to_admin(), parse_mode="HTML")
        return

    msg = await message.answer(f"<blockquote>⏳ Xray Check: {len(links)} links...</blockquote>", parse_mode="HTML")

    stats = {"added": 0, "err": 0, "checked": 0, "total": len(links), "is_finished": False}
    report = []

    queue = asyncio.Queue()
    for link in links:
        queue.put_nowait(link)

    async def worker():
        while True:
            try:
                link = queue.get_nowait()
            except asyncio.QueueEmpty:
                break

            try:
                success, region, latency, ai_avail, err = await VlessChecker.process_subscription(link)

                if success:
                    added = await SubRepo.smart_add_subscription(
                        vless_key=link, 
                        region=region, 
                        latency=latency, 
                        ai_available=ai_avail
                    )
                    
                    if added:
                        stats["added"] += 1
                        report.append(f"✅ {region} ({latency}ms)")
                    else:
                        stats["err"] += 1
                        report.append(f"⚠️ Limit/Unknown: {region}")
                else:
                    stats["err"] += 1
                    report.append(f"❌ {err}")
            except Exception:
                stats["err"] += 1
            finally:
                stats["checked"] += 1
                queue.task_done()

    async def ui_updater():
        while not stats["is_finished"]:
            percent = int((stats["checked"] / stats["total"]) * 100)
            text = (
                f"<blockquote>🔄 Импорт и проверка: {stats['checked']}/{stats['total']} ({percent}%)\n"
                f"✅ Добавлено/Заменено: {stats['added']}\n"
                f"❌ Отклонено: {stats['err']}</blockquote>"
            )
            await safe_edit_text(msg, text)
            await asyncio.sleep(3.0)

    updater_task = asyncio.create_task(ui_updater())
    workers = [asyncio.create_task(worker()) for _ in range(15)] 
    await asyncio.gather(*workers)

    stats["is_finished"] = True
    updater_task.cancel()

    final_text = (
        f"<blockquote>🏁 <b>Импорт завершен</b>\n\n"
        f"✅ Добавлено: <b>{stats['added']}</b>\n"
        f"❌ Отклонено: <b>{stats['err']}</b>\n"
        f"ℹ️ <i>Unknown регионы и лимит >100 отфильтрованы.</i>\n\n"
        f"<i>Последние добавленные:</i>\n" + "\n".join(report[-10:]) + "</blockquote>"
    )
    if len(final_text) > 4000: final_text = final_text[:4000] + "..." + "</blockquote>"
    await safe_edit_text(msg, final_text, reply_markup=back_to_admin())
    await state.clear()
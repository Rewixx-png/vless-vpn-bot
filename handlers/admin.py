import asyncio
import re
import io
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy.exc import IntegrityError
from aiogram.exceptions import TelegramRetryAfter

from config import config
from database.core import async_session_factory
from database.models import Subscription
from database.methods import DB
from utils.vless_checker import VlessChecker
from keyboards.builders import main_admin_kb, back_to_admin, regions_kb, subs_list_kb, sub_control_kb

router = Router()

class AdminStates(StatesGroup):
    waiting_for_subs = State()
    waiting_for_broadcast = State()

# --- Главное меню ---
@router.callback_query(F.data == "admin_home")
async def admin_dashboard(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id not in config.ADMIN_IDS:
        return
    await state.clear()
    await callback.message.edit_text(
        "🛠 <b>Панель Администратора</b>\n"
        "Выберите действие:",
        parse_mode="HTML",
        reply_markup=main_admin_kb()
    )

# --- Статистика ---
@router.callback_query(F.data == "admin_stats")
async def show_stats(callback: CallbackQuery):
    stats = await DB.get_stats()
    text = (
        f"📊 <b>Статистика Сервиса</b>\n\n"
        f"👥 Пользователей: {stats['users']}\n"
        f"🔑 Всего ключей: {stats['total_subs']}\n"
        f"🟢 Активных ключей: {stats['active_subs']}\n\n"
        f"<b>🌍 По регионам:</b>\n{stats['regions']}"
    )
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=back_to_admin())

# --- БЫСТРАЯ ПЕРЕПРОВЕРКА БАЗЫ (UI DECOUPLED) ---
@router.callback_query(F.data == "admin_recheck")
async def recheck_all_subs(callback: CallbackQuery):
    # 1. Готовим сообщение
    msg = await callback.message.edit_text("🚀 Инициализация проверки...")
    
    subs = await DB.get_all_subscriptions_for_check()
    if not subs:
        await msg.edit_text("⚠️ В базе нет подписок.", reply_markup=back_to_admin())
        return

    # 2. Переменные статистики (общие для всех потоков)
    stats = {
        "ok": 0, 
        "died": 0, 
        "revived": 0, 
        "checked": 0, 
        "total": len(subs),
        "is_finished": False
    }

    # 3. Воркер проверки (НЕ ТРОГАЕТ UI)
    sem = asyncio.Semaphore(50) # 50 одновременных проверок
    
    async def check_worker(sub):
        async with sem:
            try:
                parsed = VlessChecker.parse_config(sub.vless_key)
                is_alive = False
                latency = 9999
                
                if parsed:
                    # Таймаут 2.5 сек на проверку одного
                    latency_check = await VlessChecker.check_connection(parsed)
                    if latency_check != -1:
                        is_alive = True
                        latency = latency_check
                
                # Обновляем статистику атомарно (в Python GIL это безопасно для словарей)
                if sub.is_active and not is_alive: stats["died"] += 1
                elif not sub.is_active and is_alive: stats["revived"] += 1
                elif is_alive: stats["ok"] += 1
                
                await DB.update_sub_status(sub.id, is_active=is_alive, latency=latency)
            except Exception:
                pass
            finally:
                stats["checked"] += 1

    # 4. Фоновая задача обновления UI (раз в 2 секунды)
    async def ui_updater():
        while not stats["is_finished"]:
            try:
                percent = int((stats["checked"] / stats["total"]) * 100)
                await msg.edit_text(
                    f"🚀 Проверка: {stats['checked']}/{stats['total']} ({percent}%)\n"
                    f"====================\n"
                    f"✅ Живых: {stats['ok']}\n"
                    f"💀 Умерло: {stats['died']}\n"
                    f"🆙 Воскресло: {stats['revived']}"
                )
            except Exception:
                pass # Игнорируем ошибки (например, сообщение не изменилось)
            await asyncio.sleep(2.0)

    # 5. Запуск
    updater_task = asyncio.create_task(ui_updater())
    
    tasks = [check_worker(sub) for sub in subs]
    await asyncio.gather(*tasks) # Ждем завершения всех проверок
    
    stats["is_finished"] = True
    updater_task.cancel() # Останавливаем обновлялку

    # 6. Финальный отчет
    try:
        await msg.edit_text(
            f"🏁 <b>Проверка завершена!</b>\n\n"
            f"Всего: {stats['total']}\n"
            f"✅ Активных: {stats['ok'] + stats['revived']}\n"
            f"💀 Отключено: {stats['died']}\n",
            parse_mode="HTML",
            reply_markup=back_to_admin()
        )
    except:
        await callback.message.answer("🏁 Проверка завершена!", reply_markup=back_to_admin())


# --- Добавление подписок (UI DECOUPLED) ---
@router.callback_query(F.data == "admin_add")
async def start_add_subs(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        "📝 <b>Загрузка подписок</b>\n\n"
        "Отправьте .txt файл или список ссылок.\n",
        parse_mode="HTML",
        reply_markup=back_to_admin()
    )
    await state.set_state(AdminStates.waiting_for_subs)

@router.message(StateFilter(AdminStates.waiting_for_subs), F.from_user.id.in_(config.ADMIN_IDS))
async def process_batch(message: Message, state: FSMContext, bot: Bot):
    text_content = ""
    if message.document:
        if not message.document.file_name.endswith('.txt'):
            await message.answer("❌ Нужен .txt файл", reply_markup=back_to_admin())
            return
        status_msg = await message.answer("📥 Скачиваю...")
        file_io = io.BytesIO()
        await bot.download(message.document, destination=file_io)
        try:
            text_content = file_io.getvalue().decode('utf-8')
        except UnicodeDecodeError:
            await status_msg.edit_text("❌ Ошибка кодировки.")
            return
        await status_msg.delete()
    elif message.text:
        text_content = message.text
    else:
        await message.answer("❌ Пришлите текст или файл.")
        return

    links = re.findall(r'(vless://\S+|vmess://\S+|trojan://\S+)', text_content)
    links = [link.strip() for link in links if link.strip()]
    
    if not links:
        await message.answer("⚠️ Ссылки не найдены.", reply_markup=back_to_admin())
        return

    msg = await message.answer(f"⏳ Найдено: {len(links)}. Запускаю проверку...")
    
    # Структура статистики
    stats = {"added": 0, "err": 0, "checked": 0, "total": len(links), "is_finished": False}
    report = []
    
    sem = asyncio.Semaphore(30) 

    async def add_worker(link):
        async with sem:
            try:
                success, region, latency, err = await VlessChecker.process_subscription(link)
                if success:
                    try:
                        async with async_session_factory() as session:
                            session.add(Subscription(vless_key=link, region=region, latency_ms=latency))
                            await session.commit()
                        stats["added"] += 1
                        report.append(f"✅ {region} ({latency}ms)")
                    except IntegrityError:
                        report.append(f"⚠️ Дубль")
                else:
                    stats["err"] += 1
                    report.append(f"❌ {err}")
            finally:
                stats["checked"] += 1

    # Фоновый обновляльщик UI
    async def ui_updater():
        while not stats["is_finished"]:
            try:
                percent = int((stats["checked"] / stats["total"]) * 100)
                await msg.edit_text(
                    f"🔄 Добавление: {stats['checked']}/{stats['total']} ({percent}%)...\n"
                    f"✅ Живых: {stats['added']}\n"
                    f"❌ Брак: {stats['err']}"
                )
            except: pass
            await asyncio.sleep(2.0)

    updater_task = asyncio.create_task(ui_updater())
    
    tasks = [add_worker(link) for link in links]
    await asyncio.gather(*tasks)
    
    stats["is_finished"] = True
    updater_task.cancel()

    final_text = f"🏁 <b>Загрузка завершена</b>\n\n✅ Добавлено: {stats['added']}\n❌ Отбраковано: {stats['err']}\n\n" + "\n".join(report[-15:])
    if len(final_text) > 4000: final_text = final_text[:4000] + "..."
    await msg.edit_text(final_text, parse_mode="HTML", reply_markup=back_to_admin())
    await state.clear()

# --- Управление подписками ---
@router.callback_query(F.data == "admin_manage")
async def manage_regions(callback: CallbackQuery):
    regions = await DB.get_regions()
    if not regions:
        await callback.answer("База пуста или все подписки отключены.", show_alert=True)
        return
    await callback.message.edit_text("📂 Выберите регион:", reply_markup=regions_kb(regions, "manage_region"))

@router.callback_query(F.data.startswith("manage_region_"))
async def list_subs_in_region(callback: CallbackQuery):
    region = callback.data.split("manage_region_")[1]
    subs = await DB.get_subs_by_region(region)
    await callback.message.edit_text(f"📂 Регион: {region}\nВыберите подписку:", reply_markup=subs_list_kb(subs, region))

@router.callback_query(F.data.startswith("sub_detail_"))
async def show_sub_details(callback: CallbackQuery):
    sub_id = int(callback.data.split("sub_detail_")[1])
    sub = await DB.get_sub_by_id(sub_id)
    if not sub:
        await callback.answer("Не найдено", show_alert=True)
        return
    
    status_emoji = "🟢 РАБОТАЕТ" if sub.is_active else "🔴 ОТКЛЮЧЕНА"
    text = (
        f"🆔 ID: <code>{sub.id}</code>\n"
        f"Статус: {status_emoji}\n"
        f"🌍 {sub.region}\n"
        f"⚡️ Ping: {sub.latency_ms} ms\n\n"
        f"🔑 Ключ:\n<code>{sub.vless_key[:50]}...</code>"
    )
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=sub_control_kb(sub.id, sub.is_active, sub.region))

@router.callback_query(F.data.startswith("sub_toggle_"))
async def toggle_sub(callback: CallbackQuery):
    sub_id = int(callback.data.split("sub_toggle_")[1])
    sub = await DB.get_sub_by_id(sub_id)
    if sub:
        await DB.toggle_active(sub_id, sub.is_active)
        await show_sub_details(callback)

@router.callback_query(F.data.startswith("sub_delete_"))
async def delete_sub(callback: CallbackQuery):
    sub_id = int(callback.data.split("sub_delete_")[1])
    sub = await DB.get_sub_by_id(sub_id)
    if sub:
        region = sub.region
        await DB.delete_sub(sub_id)
        await callback.answer("Удалено!")
        callback.data = f"manage_region_{region}"
        await list_subs_in_region(callback)

# --- Рассылка ---
@router.callback_query(F.data == "admin_broadcast")
async def ask_broadcast(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text("📢 Отправьте сообщение для рассылки:", reply_markup=back_to_admin())
    await state.set_state(AdminStates.waiting_for_broadcast)

@router.message(StateFilter(AdminStates.waiting_for_broadcast), F.from_user.id.in_(config.ADMIN_IDS))
async def do_broadcast(message: Message, state: FSMContext):
    users = await DB.get_all_users()
    count = 0
    await message.answer(f"🚀 Рассылка на {len(users)}...")
    for user_id in users:
        try:
            await message.copy_to(chat_id=user_id)
            count += 1
            await asyncio.sleep(0.05)
        except Exception: pass
    await message.answer(f"✅ Доставлено: {count}", reply_markup=back_to_admin())
    await state.clear()
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from config import config
from database.repo import SystemRepo
from utils.checker import VlessChecker
from keyboards.admin import back_to_admin, domain_error_kb

router = Router()

class DomainStates(StatesGroup):
    waiting_for_domain = State()

def settings_domain_kb(current_domain: str | None):
    kb = [
        [InlineKeyboardButton(text="✍️ Указать домен", callback_data="set_domain_input")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="admin_home")]
    ]
    if current_domain:
        kb.insert(1, [InlineKeyboardButton(text="🗑 Удалить домен", callback_data="delete_domain")])
    return InlineKeyboardMarkup(inline_keyboard=kb)

@router.callback_query(F.data == "admin_domain")
async def show_domain_settings(callback: CallbackQuery):
    current_domain = await SystemRepo.get_config("public_domain")
    
    text = "<blockquote>⚙️ <b>Настройка домена</b>\n\n"
    if current_domain:
        text += f"✅ Текущий домен: <code>{current_domain}</code>\n\n"
        text += "Ссылки на подписку генерируются через <b>HTTPS</b> с этим доменом."
    else:
        text += "❌ Домен не настроен.\n"
        text += "Используется <code>IP:PORT</code> (HTTP).\n\n"
        text += "Чтобы включить HTTPS ссылки, добавьте домен, который направлен на этот сервер."
    text += "</blockquote>"

    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=settings_domain_kb(current_domain))

@router.callback_query(F.data == "set_domain_input")
async def ask_domain(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        "<blockquote>"
        "✍️ <b>Отправьте доменное имя:</b>\n\n"
        "Пример: <code>vpn.example.com</code>\n\n"
        "❗️ Домен должен иметь А-запись на IP этого сервера."
        "</blockquote>",
        parse_mode="HTML",
        reply_markup=back_to_admin()
    )
    await state.set_state(DomainStates.waiting_for_domain)

@router.message(StateFilter(DomainStates.waiting_for_domain), F.from_user.id.in_(config.ADMIN_IDS))
async def process_domain_input(message: Message, state: FSMContext):
    domain = message.text.strip().lower().replace("https://", "").replace("http://", "").split("/")[0]
    
    msg = await message.answer(
        "<blockquote>🔍 Проверяю домен <code>{domain}</code>...\n1. DNS Resolve\n2. SSL Check (443)</blockquote>", 
        parse_mode="HTML"
    )
    
    is_valid, error = await VlessChecker.verify_domain(domain)
    
    if is_valid:
        await SystemRepo.set_config("public_domain", domain)
        await msg.edit_text(
            f"<blockquote>✅ <b>Домен сохранен!</b>\n\n"
            f"Теперь ссылки подписки будут вида:\n"
            f"<code>https://{domain}/sub?id=...</code></blockquote>",
            parse_mode="HTML",
            reply_markup=back_to_admin()
        )
        await state.clear()
    else:
        await msg.edit_text(
            f"<blockquote>❌ <b>Ошибка проверки:</b>\n\n"
            f"{error}\n\n"
            f"Если вы используете Cloudflare или уверены в настройках, нажмите кнопку ниже.</blockquote>",
            parse_mode="HTML",
            reply_markup=domain_error_kb(domain)
        )

@router.callback_query(F.data.startswith("force_save_domain:"))
async def force_save_domain(callback: CallbackQuery, state: FSMContext):
    domain = callback.data.split("force_save_domain:")[1]
    
    await SystemRepo.set_config("public_domain", domain)
    
    await callback.message.edit_text(
        f"<blockquote>✅ <b>Домен сохранен (Принудительно)!</b>\n\n"
        f"🔗 Ссылки обновлены:\n"
        f"<code>https://{domain}/sub?id=...</code>\n\n"
        f"⚠️ <i>Убедитесь, что ваш обратный прокси (Nginx/Cloudflare) настроен верно и пересылает запросы на порт {config.WEB_PORT} бота.</i></blockquote>",
        parse_mode="HTML",
        reply_markup=back_to_admin()
    )
    await state.clear()

@router.callback_query(F.data == "delete_domain")
async def delete_domain(callback: CallbackQuery):
    await SystemRepo.delete_config("public_domain")
    await callback.answer("🗑 Домен удален", show_alert=True)
    await show_domain_settings(callback)
import asyncio
import json
import re
import time
import logging
from typing import Any

from aiogram import Router, F, Bot
from aiogram.types import (
    Message, CallbackQuery,
    InlineKeyboardMarkup, InlineKeyboardButton,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.exceptions import TelegramRetryAfter, TelegramForbiddenError, TelegramBadRequest

from config import config
from database.repo import UserRepo
from handlers.admin.states import AdminStates
from handlers.admin.utils import safe_edit_message

router = Router()
logger = logging.getLogger(__name__)


def _parse_buttons(raw: str) -> list[list[dict[str, Any]]]:
    rows = []
    for line in raw.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        row = []
        for cell in line.split("||"):
            cell = cell.strip()
            if "|" not in cell:
                continue
            parts = cell.split("|", 1)
            text = parts[0].strip()
            url = parts[1].strip()
            if text and url.startswith("http"):
                row.append({"text": text, "url": url})
        if row:
            rows.append(row)
    return rows


def _build_inline_kb(buttons: list[list[dict[str, Any]]]) -> InlineKeyboardMarkup | None:
    if not buttons:
        return None
    kb = InlineKeyboardBuilder()
    for row in buttons:
        kb.row(*[InlineKeyboardButton(text=b["text"], url=b["url"]) for b in row])
    return kb.as_markup()


def _buttons_preview_text(buttons: list[list[dict[str, Any]]]) -> str:
    if not buttons:
        return ""
    lines = []
    for row in buttons:
        lines.append("  ".join(f"[{b['text']}]" for b in row))
    return "\n".join(lines)


def _broadcast_editor_kb(has_buttons: bool = False) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="➕ Добавить кнопку", callback_data="bc_add_button")
    if has_buttons:
        kb.button(text="🗑 Очистить кнопки", callback_data="bc_clear_buttons")
    kb.button(text="👁 Превью", callback_data="bc_preview")
    kb.adjust(2 if has_buttons else 1, 1)
    kb.row(
        InlineKeyboardButton(text="👥 Всем", callback_data="bc_send_all"),
        InlineKeyboardButton(text="✅ Активным", callback_data="bc_send_active"),
    )
    kb.row(InlineKeyboardButton(text="❌ Отмена", callback_data="admin_menu"))
    return kb.as_markup()


def _confirm_kb(audience: str) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="🚀 Подтвердить и отправить", callback_data=f"bc_confirm_{audience}")
    kb.button(text="✏️ Редактировать", callback_data="bc_back_edit")
    kb.button(text="❌ Отмена", callback_data="admin_menu")
    kb.adjust(1)
    return kb.as_markup()


async def _show_editor(target: Message | CallbackQuery, state: FSMContext, bot: Bot):
    data = await state.get_data()
    buttons: list[list[dict[str, Any]]] = data.get("bc_buttons", [])
    btn_text = _buttons_preview_text(buttons)

    info = (
        "<b>📢 Редактор рассылки</b>\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        "✅ Сообщение получено.\n"
    )
    if btn_text:
        info += f"\n<b>Кнопки:</b>\n<code>{btn_text}</code>\n"

    info += (
        "\n<b>Что дальше?</b>\n"
        "• Добавь кнопки с ссылками\n"
        "• Посмотри превью перед отправкой\n"
        "• Выбери аудиторию"
    )

    kb = _broadcast_editor_kb(has_buttons=bool(buttons))
    msg = target if isinstance(target, Message) else target.message
    if not isinstance(msg, Message):
        return
    try:
        await msg.edit_text(info, parse_mode="HTML", reply_markup=kb)
    except Exception:
        await msg.answer(info, parse_mode="HTML", reply_markup=kb)


@router.callback_query(F.data == "admin_broadcast")
async def ask_broadcast(callback: CallbackQuery, state: FSMContext):
    if not callback.from_user or callback.from_user.id not in config.ADMIN_IDS:
        await callback.answer("⛔ Доступ запрещён", show_alert=True)
        return
    if not isinstance(callback.message, Message):
        return
    await state.clear()
    text = (
        "<b>📢 Новая рассылка</b>\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        "Отправь сообщение которое хочешь разослать:\n"
        "• Текст (с форматированием)\n"
        "• Фото / видео / гифка\n"
        "• Любой медиатип\n\n"
        "<i>Просто отправь сообщение сюда ↓</i>"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="❌ Отмена", callback_data="admin_menu")
    ]])
    try:
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
    except Exception:
        try:
            await callback.message.edit_caption(caption=text, parse_mode="HTML", reply_markup=kb)
        except Exception:
            await callback.message.answer(text, parse_mode="HTML", reply_markup=kb)
    await state.set_state(AdminStates.waiting_for_broadcast)


@router.message(StateFilter(AdminStates.waiting_for_broadcast), F.from_user.id.in_(config.ADMIN_IDS))
async def got_broadcast_message(message: Message, state: FSMContext):
    await state.update_data(
        bc_from_chat=message.chat.id,
        bc_message_id=message.message_id,
        bc_buttons=[],
    )
    info_msg = await message.answer("⏳ Загружаю редактор...")
    await state.update_data(bc_editor_msg_id=info_msg.message_id)

    buttons: list[list[dict[str, Any]]] = []
    btn_text = _buttons_preview_text(buttons)

    info = (
        "<b>📢 Редактор рассылки</b>\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        "✅ Сообщение получено.\n\n"
        "<b>Что дальше?</b>\n"
        "• Добавь кнопки с ссылками\n"
        "• Посмотри превью перед отправкой\n"
        "• Выбери аудиторию"
    )
    await info_msg.edit_text(info, parse_mode="HTML", reply_markup=_broadcast_editor_kb(False))


@router.callback_query(F.data == "bc_add_button")
async def ask_add_button(callback: CallbackQuery, state: FSMContext):
    if not callback.from_user or callback.from_user.id not in config.ADMIN_IDS:
        await callback.answer("⛔ Доступ запрещён", show_alert=True)
        return
    if not isinstance(callback.message, Message):
        return
    await callback.message.edit_text(
        "<b>➕ Добавить кнопку</b>\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        "Отправь кнопку в формате:\n"
        "<code>Текст кнопки | https://ссылка.ru</code>\n\n"
        "Несколько кнопок <b>в один ряд</b> — разделяй <code>||</code>:\n"
        "<code>Кнопка 1 | https://site.ru || Кнопка 2 | https://t.me/bot</code>\n\n"
        "Несколько <b>рядов</b> — каждый с новой строки.\n\n"
        "<i>Пример (2 ряда по 1-2 кнопки):</i>\n"
        "<code>Подписаться | https://t.me/channel\n"
        "Сайт | https://site.ru || Бот | https://t.me/bot</code>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="◀️ Назад", callback_data="bc_back_edit")
        ]])
    )
    await state.set_state(AdminStates.broadcast_adding_button)


@router.message(StateFilter(AdminStates.broadcast_adding_button), F.from_user.id.in_(config.ADMIN_IDS))
async def got_button_text(message: Message, state: FSMContext):
    if not message.bot:
        return
    raw = message.text or ""
    new_rows = _parse_buttons(raw)

    if not new_rows:
        await message.answer(
            "⚠️ Не смог распознать кнопку.\n"
            "Формат: <code>Текст | https://url.com</code>",
            parse_mode="HTML",
        )
        return

    data = await state.get_data()
    existing: list[list[dict[str, Any]]] = data.get("bc_buttons", [])
    existing.extend(new_rows)
    await state.update_data(bc_buttons=existing)

    try:
        await message.delete()
    except Exception:
        pass

    btn_preview = _buttons_preview_text(existing)
    info = (
        "<b>📢 Редактор рассылки</b>\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        f"✅ Добавлено {sum(len(r) for r in new_rows)} кнопок.\n\n"
        f"<b>Все кнопки ({sum(len(r) for r in existing)}):</b>\n"
        f"<code>{btn_preview}</code>\n\n"
        "<b>Что дальше?</b>\n"
        "• Добавь ещё кнопки\n"
        "• Посмотри превью\n"
        "• Выбери аудиторию"
    )
    editor_msg_id = data.get("bc_editor_msg_id")
    if editor_msg_id:
        try:
            await message.bot.edit_message_text(
                chat_id=message.chat.id,
                message_id=editor_msg_id,
                text=info,
                parse_mode="HTML",
                reply_markup=_broadcast_editor_kb(True),
            )
        except Exception:
            new_msg = await message.answer(info, parse_mode="HTML", reply_markup=_broadcast_editor_kb(True))
            await state.update_data(bc_editor_msg_id=new_msg.message_id)
    else:
        new_msg = await message.answer(info, parse_mode="HTML", reply_markup=_broadcast_editor_kb(True))
        await state.update_data(bc_editor_msg_id=new_msg.message_id)

    await state.set_state(AdminStates.waiting_for_broadcast)


@router.callback_query(F.data == "bc_clear_buttons")
async def clear_buttons(callback: CallbackQuery, state: FSMContext):
    if not callback.from_user or callback.from_user.id not in config.ADMIN_IDS:
        await callback.answer("⛔ Доступ запрещён", show_alert=True)
        return
    if not isinstance(callback.message, Message):
        return
    await state.update_data(bc_buttons=[])
    info = (
        "<b>📢 Редактор рассылки</b>\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        "✅ Сообщение готово.\n"
        "🗑 Все кнопки удалены.\n\n"
        "<b>Что дальше?</b>\n"
        "• Добавь кнопки с ссылками\n"
        "• Посмотри превью перед отправкой\n"
        "• Выбери аудиторию"
    )
    await callback.message.edit_text(info, parse_mode="HTML", reply_markup=_broadcast_editor_kb(False))


@router.callback_query(F.data == "bc_back_edit")
async def back_to_editor(callback: CallbackQuery, state: FSMContext):
    if not callback.from_user or callback.from_user.id not in config.ADMIN_IDS:
        await callback.answer("⛔ Доступ запрещён", show_alert=True)
        return
    if not isinstance(callback.message, Message):
        return
    data = await state.get_data()
    buttons: list[list[dict[str, Any]]] = data.get("bc_buttons", [])
    btn_text = _buttons_preview_text(buttons)
    info = (
        "<b>📢 Редактор рассылки</b>\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        "✅ Сообщение готово.\n"
    )
    if btn_text:
        info += f"\n<b>Кнопки:</b>\n<code>{btn_text}</code>\n"
    info += (
        "\n<b>Что дальше?</b>\n"
        "• Добавь кнопки с ссылками\n"
        "• Посмотри превью перед отправкой\n"
        "• Выбери аудиторию"
    )
    await state.set_state(AdminStates.waiting_for_broadcast)
    await callback.message.edit_text(info, parse_mode="HTML", reply_markup=_broadcast_editor_kb(bool(buttons)))


@router.callback_query(F.data == "bc_preview")
async def show_preview(callback: CallbackQuery, state: FSMContext):
    if not callback.from_user or callback.from_user.id not in config.ADMIN_IDS:
        await callback.answer("⛔ Доступ запрещён", show_alert=True)
        return
    if not isinstance(callback.message, Message):
        return
    if not callback.bot:
        return
    data = await state.get_data()
    from_chat = data.get("bc_from_chat")
    message_id = data.get("bc_message_id")
    assert from_chat is not None
    assert message_id is not None
    buttons: list[list[dict[str, Any]]] = data.get("bc_buttons", [])
    kb = _build_inline_kb(buttons)

    await callback.answer("Отправляю превью...", show_alert=False)

    try:
        await callback.message.answer(
            "👁 <b>Так увидят пользователи:</b>",
            parse_mode="HTML",
        )
        await callback.bot.copy_message(
            chat_id=callback.from_user.id,
            from_chat_id=from_chat,
            message_id=message_id,
            reply_markup=kb,
        )
    except Exception as e:
        await callback.message.answer(f"⚠️ Ошибка превью: {e}")


@router.callback_query(F.data.in_({"bc_send_all", "bc_send_active"}))
async def choose_audience(callback: CallbackQuery, state: FSMContext):
    if not callback.from_user or callback.from_user.id not in config.ADMIN_IDS:
        await callback.answer("⛔ Доступ запрещён", show_alert=True)
        return
    if not isinstance(callback.message, Message):
        return
    audience = "all" if callback.data == "bc_send_all" else "active"
    data = await state.get_data()
    buttons: list[list[dict[str, Any]]] = data.get("bc_buttons", [])
    btn_text = _buttons_preview_text(buttons)

    users = await UserRepo.get_all_users()
    total = len(users)

    audience_label = "всем пользователям" if audience == "all" else "активным пользователям"
    info = (
        f"<b>📢 Подтверждение рассылки</b>\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        f"👥 Получатели: <b>{audience_label}</b>\n"
        f"📊 Количество: <b>{total}</b>\n"
    )
    if btn_text:
        info += f"\n🔘 <b>Кнопки:</b>\n<code>{btn_text}</code>\n"
    info += "\n⚠️ <b>После запуска остановить нельзя.</b>\nПодтверждаешь?"

    await state.update_data(bc_audience=audience)
    await state.set_state(AdminStates.broadcast_confirm)
    await callback.message.edit_text(
        info, parse_mode="HTML",
        reply_markup=_confirm_kb(audience)
    )


@router.callback_query(F.data.startswith("bc_confirm_"))
async def do_broadcast(callback: CallbackQuery, state: FSMContext):
    if not callback.from_user or callback.from_user.id not in config.ADMIN_IDS:
        await callback.answer("⛔ Доступ запрещён", show_alert=True)
        return
    if not isinstance(callback.message, Message):
        return
    if not callback.bot:
        return
    data = await state.get_data()
    from_chat = data.get("bc_from_chat")
    message_id = data.get("bc_message_id")
    assert from_chat is not None
    assert message_id is not None
    buttons: list[list[dict[str, Any]]] = data.get("bc_buttons", [])
    audience = data.get("bc_audience", "all")
    kb = _build_inline_kb(buttons)

    await state.clear()

    users = await UserRepo.get_all_users()
    total = len(users)

    if total == 0:
        await callback.message.edit_text("⚠️ Нет пользователей.")
        return

    start_time = time.time()
    sent = failed = blocked = 0
    last_update = time.time()

    status_msg = await callback.message.edit_text(
        f"<b>🚀 Рассылка запущена</b>\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        f"📊 Прогресс: <code>0/{total}</code>  (0%)\n"
        f"✅ Доставлено: <b>0</b>\n"
        f"🚫 Заблокировали: <b>0</b>\n"
        f"❌ Ошибок: <b>0</b>",
        parse_mode="HTML",
    )

    for index, user in enumerate(users, 1):
        user_id = user.id if hasattr(user, "id") else user
        try:
            await asyncio.wait_for(
                callback.bot.copy_message(
                    chat_id=user_id,
                    from_chat_id=from_chat,
                    message_id=message_id,
                    reply_markup=kb,
                ),
                timeout=6.0,
            )
            sent += 1
            await asyncio.sleep(0.04)
        except TelegramForbiddenError:
            blocked += 1
        except TelegramRetryAfter as e:
            await asyncio.sleep(e.retry_after + 0.5)
            try:
                await callback.bot.copy_message(
                    chat_id=user_id,
                    from_chat_id=from_chat,
                    message_id=message_id,
                    reply_markup=kb,
                )
                sent += 1
            except Exception:
                failed += 1
        except (TelegramBadRequest, asyncio.TimeoutError, Exception):
            failed += 1

        if (time.time() - last_update > 2.0) or index == total:
            pct = int(index / total * 100)
            bar_done = int(pct / 10)
            bar = "█" * bar_done + "░" * (10 - bar_done)
            try:
                if isinstance(status_msg, Message):
                    await status_msg.edit_text(
                        f"<b>🚀 Рассылка в процессе</b>\n"
                        "━━━━━━━━━━━━━━━━━━\n\n"
                        f"<code>{bar}</code> {pct}%\n"
                        f"📊 Прогресс: <code>{index}/{total}</code>\n\n"
                        f"✅ Доставлено: <b>{sent}</b>\n"
                        f"🚫 Заблокировали: <b>{blocked}</b>\n"
                        f"❌ Ошибок: <b>{failed}</b>",
                        parse_mode="HTML",
                    )
            except Exception:
                pass
            last_update = time.time()

    elapsed = int(time.time() - start_time)
    mins, secs = divmod(elapsed, 60)
    deliver_pct = int(sent / total * 100) if total else 0

    from keyboards.admin import back_to_admin
    if isinstance(status_msg, Message):
        await safe_edit_message(
            status_msg,
            f"<b>✅ Рассылка завершена!</b>\n"
            "━━━━━━━━━━━━━━━━━━\n\n"
            f"👥 Всего получателей: <b>{total}</b>\n"
            f"✅ Доставлено: <b>{sent}</b>\n"
            f"🚫 Заблокировали бота: <b>{blocked}</b>\n"
            f"❌ Ошибок: <b>{failed}</b>\n"
            f"📈 Доставляемость: <b>{deliver_pct}%</b>\n"
            f"⏱ Время: <b>{mins}м {secs}с</b>",
            parse_mode="HTML",
            reply_markup=back_to_admin(),
        )

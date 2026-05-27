from typing import Any
import urllib.parse
from datetime import datetime
import time
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from database.repo.subs import SubRepo
from database.repo.users import UserRepo
from database.repo.system import SystemRepo
from keyboards.user import (
    settings_countries_kb,
    back_to_home,
    settings_main_kb,
    settings_limit_kb,
    sub_action_kb,
    settings_tags_kb,
    tg_proxy_kb,
    _protocol_label,  # type: ignore[reportPrivateUsage]
    settings_protocols_kb,
)
from handlers.user.states import UserStates
from handlers.user.start import edit_or_answer
from config import config
from utils.qr import QRGenerator
from utils.tg_proxy import TelegramProxyService

router = Router()


async def _build_subscription_url(user_id: str | int, protocol_filter: str | None = None) -> str:
    encoded_id = urllib.parse.quote(str(user_id), safe="/")

    db_domain = await SystemRepo.get_config("public_domain")
    domain = str(db_domain if db_domain else config.public_domain or "").strip()

    if domain.startswith("http://") or domain.startswith("https://"):
        base = domain.rstrip("/")
    elif domain and ":" in domain.split("/")[0]:
        base = f"http://{domain}"
    elif domain:
        base = f"https://{domain}"
    else:
        public_ip = config.PUBLIC_IP
        base = f"http://{public_ip}:{config.WEB_PORT}"

    url = f"{base}/sub64?id={encoded_id}"
    if protocol_filter == "vless":
        url += "&types=vless"
    elif protocol_filter == "hy2":
        url += "&types=hy2,hysteria2,tuic"
    elif protocol_filter == "trojan":
        url += "&types=trojan"
    return url


def _extract_proxy_items(data: Any) -> list[dict[str, Any]]:
    if not isinstance(data, dict):
        return []

    raw_items = data.get("proxy_items")
    if isinstance(raw_items, list) and raw_items:
        cleaned = []
        for item in raw_items:
            if not isinstance(item, dict):
                continue
            link = str(item.get("link", "") or "").strip()
            if not link:
                continue
            latency_raw = item.get("latency_ms")
            try:
                latency_ms = int(latency_raw) if latency_raw is not None else 0
            except Exception:
                latency_ms = 0
            kind = str(item.get("kind", "mtproto") or "mtproto").strip().lower()
            if kind != "mtproto":
                continue
            cleaned.append(
                {
                    "link": link,
                    "latency_ms": latency_ms,
                    "kind": kind,
                }
            )
        if cleaned:
            return cleaned

    proxies = data.get("proxies", [])
    if not isinstance(proxies, list):
        return []
    return [
        {"link": str(link).strip(), "latency_ms": 0, "kind": "mtproto"}
        for link in proxies
        if str(link).strip()
    ]


def _build_tg_proxy_text(
    data: Any,
    proxy_items: list[dict[str, Any]],
    is_stale: bool,
    offset: int,
    page_size: int,
) -> str:
    checked_at = int(data.get("checked_at", 0) or 0) if isinstance(data, dict) else 0

    checked_at_text = "—"
    if checked_at > 0:
        checked_at_text = datetime.fromtimestamp(checked_at).strftime("%d.%m.%Y %H:%M")

    if not proxy_items:
        return (
            "<b>🧩 TG Proxy (MTProto)</b>\n"
            "━━━━━━━━━━━━━━━━━━\n\n"
            "Сейчас нет рабочих прокси в кэше.\n"
            "Нажмите «Обновить список», чтобы запустить проверку в фоне.\n\n"
            "⚠️ <b>Важно:</b> проверяйте и подключайте прокси через <b>официальный Telegram</b>.\n"
            "В неофициальных клиентах (fork) бывает бесконечная проверка."
        )

    total = len(proxy_items)
    alive_total = int(data.get("alive", total) or total) if isinstance(data, dict) else total
    alive_shown = int(data.get("alive_shown", total) or total) if isinstance(data, dict) else total
    output_limit = int(data.get("output_limit", 0) or 0) if isinstance(data, dict) else 0

    if alive_total < 0:
        alive_total = total
    if alive_shown < 0:
        alive_shown = total

    mtproto_total = sum(1 for item in proxy_items if item.get("kind") == "mtproto")
    safe_offset = max(0, min(offset, max(0, total - 1))) if total else 0
    start_idx = safe_offset + 1
    end_idx = min(total, safe_offset + page_size)

    lines = [
        "<b>🧩 TG Proxy (MTProto)</b>",
        "━━━━━━━━━━━━━━━━━━",
        "",
        f"<b>Обновлено:</b> {checked_at_text}",
        f"<b>Проверено:</b> {int(data.get('checked', 0) or 0)}",
        f"<b>Рабочих (всего):</b> {alive_total}",
        f"<b>В списке:</b> {total}",
        f"<b>Показано:</b> {start_idx}-{end_idx}",
    ]

    if alive_total > total:
        if output_limit > 0:
            lines.append(
                f"<i>Показываю топ-{total} из {alive_total} (лимит выдачи: {output_limit}).</i>"
            )
        elif alive_shown > 0:
            lines.append(
                f"<i>Показываю топ-{total} из {alive_total} проверенных прокси.</i>"
            )

    if is_stale:
        lines.append("<i>Показываю кэш; обновление уже запущено в фоне.</i>")

    lines.append(
        "⚠️ <b>Важно:</b> проверяйте и подключайте прокси через <b>официальный Telegram</b>."
    )
    lines.append(
        "В неофициальных клиентах (fork) бывает бесконечная проверка."
    )

    lines.append("")
    lines.append("<i>Выберите прокси кнопкой ниже — у каждой кнопки есть тип и пинг (ms).</i>")
    lines.append("<i>Нажимайте аккуратно: одна кнопка = один прокси.</i>")
    return "\n".join(lines)


def _queue_tg_proxy_refresh() -> bool:
    try:
        from tasks import update_tg_proxy_task

        getattr(update_tg_proxy_task, "delay")()
        return True
    except Exception:
        return False


async def _render_tg_proxy(callback: CallbackQuery, state: FSMContext, offset: int = 0):
    if not isinstance(callback.message, Message):
        return
    data = await TelegramProxyService.get_cached()

    if not data:
        queued = _queue_tg_proxy_refresh()
        if queued:
            text = (
                "<b>🧩 TG Proxy (MTProto)</b>\n"
                "━━━━━━━━━━━━━━━━━━\n\n"
                "⏳ Первый список еще готовится.\n"
                "Я запустил проверку в фоне — нажмите «Обновить список» через 20-40 секунд.\n\n"
                "⚠️ <b>Важно:</b> проверяйте и подключайте прокси через <b>официальный Telegram</b>.\n"
                "В неофициальных клиентах (fork) бывает бесконечная проверка."
            )
        else:
            text = (
                "<b>🧩 TG Proxy (MTProto)</b>\n"
                "━━━━━━━━━━━━━━━━━━\n\n"
                "⚠️ Не удалось запустить фоновое обновление. Попробуйте еще раз.\n\n"
                "⚠️ <b>Важно:</b> проверяйте и подключайте прокси через <b>официальный Telegram</b>.\n"
                "В неофициальных клиентах (fork) бывает бесконечная проверка."
            )

        await edit_or_answer(
            callback.message,
            text,
            tg_proxy_kb(),
            state,
            media_url="video",
        )
        return

    checked_at = int(data.get("checked_at", 0) or 0)
    is_stale = checked_at <= 0 or (int(time.time()) - checked_at) > 3600
    if is_stale:
        _ = _queue_tg_proxy_refresh()

    proxy_items = _extract_proxy_items(data)
    page_size = 16
    text = _build_tg_proxy_text(
        data,
        proxy_items=proxy_items,
        is_stale=is_stale,
        offset=offset,
        page_size=page_size,
    )
    await edit_or_answer(
        callback.message,
        text,
        tg_proxy_kb(proxy_items=proxy_items, offset=offset, page_size=page_size),
        state,
        media_url="video",
    )


@router.callback_query(F.data == "tg_proxy_list")
async def show_tg_proxy_list(callback: CallbackQuery, state: FSMContext):
    if not isinstance(callback.message, Message):
        return
    _ = await callback.answer("🧩 Открываю список прокси...", show_alert=False)
    await _render_tg_proxy(callback, state, offset=0)


@router.callback_query(F.data == "tg_proxy_refresh")
async def refresh_tg_proxy_list(callback: CallbackQuery, state: FSMContext):
    if not isinstance(callback.message, Message):
        return
    queued = _queue_tg_proxy_refresh()
    if queued:
        _ = await callback.answer("🔄 Запустил обновление в фоне", show_alert=True)
    else:
        _ = await callback.answer("⚠️ Не удалось запустить обновление", show_alert=True)
    await _render_tg_proxy(callback, state, offset=0)


@router.callback_query(F.data.startswith("tg_proxy_page_"))
async def tg_proxy_page(callback: CallbackQuery, state: FSMContext):
    if not callback.data:
        return
    if not isinstance(callback.message, Message):
        return
    try:
        offset = int(callback.data.split("tg_proxy_page_")[1])
    except Exception:
        offset = 0

    _ = await callback.answer("", show_alert=False)
    await _render_tg_proxy(callback, state, offset=max(0, offset))


@router.callback_query(F.data == "my_subscription")
async def give_subscription_menu(callback: CallbackQuery, state: FSMContext):
    if not isinstance(callback.message, Message):
        return
    user_id = callback.from_user.id
    user = await UserRepo.get_user(user_id)
    protocol_filter: str | None = str(getattr(user, "protocol_filter")) if user and getattr(user, "protocol_filter") is not None else None
    sub_url = await _build_subscription_url(user_id, protocol_filter)

    limit = int(getattr(user, "subscription_limit")) if user else 0
    limit_txt = "Все доступные (∞)"
    if limit > 0:
        limit_txt = f"{limit} лучших"

    links_block = f"<code>{sub_url}</code>"

    text = (
        "<b>🔑 Ваша подписка</b>\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        f"<b>Ссылка:</b>\n{links_block}\n\n"
        f"📦 Серверов: <b>{limit_txt}</b>  |  🔄 Обновление: авто\n\n"
        "<i>Нажмите кнопку ниже, чтобы открыть в приложении или скопировать.</i>"
    )

    await edit_or_answer(
        callback.message, text, sub_action_kb(sub_url), state, media_url="video"
    )


@router.callback_query(F.data == "sub_qr_main")
async def show_main_qr(callback: CallbackQuery):
    if not isinstance(callback.message, Message):
        return
    user_id = callback.from_user.id
    sub_url = await _build_subscription_url(user_id)
    qr_file = QRGenerator.generate(sub_url)

    _ = await callback.message.answer_photo(
        photo=qr_file,
        caption="<b>📱 Ваш QR-код для подключения</b>\nОтсканируйте его в приложении (v2rayNG, V2Box, FlClash и др.)",
        parse_mode="HTML",
    )
    _ = await callback.answer()


@router.callback_query(F.data == "settings_main")
async def open_settings_main(callback: CallbackQuery, state: FSMContext):
    if not isinstance(callback.message, Message):
        return
    data = await state.get_data()
    last_msg_id = data.get("last_msg_id")
    _ = await state.clear()
    if last_msg_id:
        _ = await state.update_data(last_msg_id=last_msg_id)

    user = await UserRepo.get_user(callback.from_user.id)
    limit = int(getattr(user, "subscription_limit")) if user else 0
    use_fragment = bool(getattr(user, "use_fragment")) if user else False
    protocol_filter: str | None = str(getattr(user, "protocol_filter")) if user and getattr(user, "protocol_filter") is not None else None

    text = (
        "<b>⚙️ CONFIGURATION | НАСТРОЙКИ</b>\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        "Здесь вы можете настроить параметры вашей подписки.\n"
        "Изменения применяются мгновенно при следующем обновлении в приложении.\n\n"
        "<b>Доступные опции:</b>\n"
        "🌍 <b>Страны:</b> Выберите конкретные регионы.\n"
        "⚡ <b>Теги:</b> AI, скорость, Reality, Wi-Fi/Mobile и операторы.\n"
        "🔢 <b>Лимит:</b> Ограничить кол-во серверов (для старых телефонов).\n"
        "🛡 <b>Фрагментация:</b> Обход жесткого DPI (в РФ/Иране).\n"
        "🔀 <b>Протокол:</b> VLESS, Hysteria2 или оба сразу."
    )

    await edit_or_answer(
        callback.message,
        text,
        settings_main_kb(limit, use_fragment, protocol_filter),
        state,
        media_url="video",
    )


@router.callback_query(F.data == "toggle_fragment")
async def toggle_fragment_action(callback: CallbackQuery, state: FSMContext):
    if not isinstance(callback.message, Message):
        return
    user = await UserRepo.get_user(callback.from_user.id)
    if user:
        new_state = not bool(getattr(user, "use_fragment"))
        await UserRepo.update_fragment_setting(int(getattr(user, "id")), new_state)
    await open_settings_main(callback, state)


@router.callback_query(F.data == "settings_protocols")
async def open_settings_protocols(callback: CallbackQuery, state: FSMContext):
    if not isinstance(callback.message, Message):
        return
    user = await UserRepo.get_user(callback.from_user.id)
    protocol: str | None = str(getattr(user, "protocol_filter")) if user and getattr(user, "protocol_filter") is not None else None
    
    text = (
        "<b>🔀 CHOOSE PROTOCOL | ВЫБОР ПРОТОКОЛА</b>\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        "Выберите протокол подключения для вашей подписки:\n\n"
        "▫️ <b>Все вместе:</b> Автоматически комбинирует все доступные протоколы (Рекомендуется).\n"
        "▫️ <b>Только VLESS:</b> Классический, стабильный протокол на базе TCP/Reality.\n"
        "▫️ <b>Только Hysteria2:</b> Сверхбыстрый QUIC-протокол (отлично подходит для мобильного интернета и обхода глушилок).\n"
        "▫️ <b>Только Trojan:</b> Легковесный и быстрый протокол с шифрованием TLS."
    )
    await edit_or_answer(
        callback.message, text, settings_protocols_kb(protocol), state, media_url="video"
    )


@router.callback_query(F.data.startswith("set_protocol_"))
async def set_protocol_action(callback: CallbackQuery, state: FSMContext):
    if not callback.data:
        return
    if not isinstance(callback.message, Message):
        return
    proto_val = callback.data.split("set_protocol_")[1]
    protocol = None if proto_val == "all" else proto_val
    
    await UserRepo.update_user_protocol_filter(callback.from_user.id, protocol)
    _ = await callback.answer(f"✅ Установлен протокол: {_protocol_label(protocol)}", show_alert=False)
    await open_settings_protocols(callback, state)


@router.callback_query(F.data == "settings_tags")
async def open_settings_tags(callback: CallbackQuery, state: FSMContext):
    if not isinstance(callback.message, Message):
        return
    user_tags = await UserRepo.get_user_tags(callback.from_user.id)

    text = (
        "<b>⚡ CONNECTION TYPES | ТЕГИ</b>\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        "Выберите типы серверов, которые вам нужны:\n\n"
        "🛡 <b>Stable (Elite):</b> Серверы с аптаймом 24ч+ без единого сбоя.\n"
        "▫️ <b>AI Ready:</b> Проверено на доступ к ChatGPT и AI Studio. Ограничения Google по аккаунту/возрасту могут влиять отдельно.\n"
        "▫️ <b>High Speed:</b> Серверы со скоростью &gt; 100 Mbps.\n"
        "▫️ <b>Mobile/LTE:</b> Конфиги под мобильные сети (4G/5G).\n"
        "▫️ <b>Wi-Fi/Home:</b> Конфиги под домашний интернет/роутер.\n"
        "▫️ <b>MTS / Beeline / MegaFon / Tele2:</b> Профили под конкретного оператора.\n"
        "▫️ <b>Reality/Vision:</b> Высокая скрытность от блокировок.\n"
        "▫️ <b>gRPC:</b> Только конфиги с транспортом gRPC (type=grpc).\n"
        "🚫 <b>No-Ads:</b> Встроенная блокировка рекламы (DNS).\n\n"
        "<i>✅ - Включено в подписку\n⬜️ - Обычные серверы</i>"
    )

    await edit_or_answer(
        callback.message, text, settings_tags_kb(user_tags), state, media_url="video"
    )


@router.callback_query(F.data.startswith("toggle_tag_"))
async def toggle_tag(callback: CallbackQuery):
    if not callback.data:
        return
    if not isinstance(callback.message, Message):
        return
    tag = callback.data.split("toggle_tag_")[1]
    user_id = callback.from_user.id

    current_tags = await UserRepo.get_user_tags(user_id)

    if tag in current_tags:
        current_tags.remove(tag)
    else:
        current_tags.append(tag)

    await UserRepo.update_user_tags(user_id, current_tags)
    _ = await callback.message.edit_reply_markup(
        reply_markup=settings_tags_kb(current_tags)
    )


@router.callback_query(F.data == "settings_limit")
async def open_settings_limit(callback: CallbackQuery, state: FSMContext):
    if not isinstance(callback.message, Message):
        return
    user = await UserRepo.get_user(callback.from_user.id)
    limit = int(getattr(user, "subscription_limit")) if user else 0


    text = (
        "<b>🔢 SERVER LIMIT | ЛИМИТЫ</b>\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        "Ограничьте количество серверов в подписке, если ваше приложение тормозит от большого списка.\n\n"
        f"<b>Текущий лимит:</b> {'♾️ Безлимит' if limit == 0 else str(limit)}\n\n"
        "<i>Бот автоматически подберет лучшие серверы по скорости.</i>"
    )

    await edit_or_answer(
        callback.message, text, settings_limit_kb(limit), state, media_url="video"
    )


@router.callback_query(F.data.startswith("set_limit_"))
async def set_limit_value(callback: CallbackQuery, state: FSMContext):
    if not callback.data:
        return
    if not isinstance(callback.message, Message):
        return
    val = callback.data.split("set_limit_")[1]

    if val == "custom":
        await edit_or_answer(
            callback.message,
            "<b>✍️ ВВОД ЧИСЛА</b>\n━━━━━━━━━━━━━━━━━━\n\nВведите желаемое количество серверов (числом):\n<i>0 - для снятия лимита</i>",
            back_to_home(),
            state,
            media_url="video",
        )
        _ = await state.set_state(UserStates.waiting_for_custom_limit)
        return

    limit = int(val)
    await UserRepo.update_subscription_limit(callback.from_user.id, limit)
    await open_settings_main(callback, state)


@router.message(StateFilter(UserStates.waiting_for_custom_limit))
async def process_custom_limit_input(message: Message, state: FSMContext):
    if not message.from_user:
        return
    try:
        _ = await message.delete()
    except:
        pass

    try:
        if not message.text:
            raise ValueError
        limit = int(message.text.strip())
        if limit < 0:
            raise ValueError

        await UserRepo.update_subscription_limit(message.from_user.id, limit)
        _ = await state.clear()

        user = await UserRepo.get_user(message.from_user.id)
        protocol_filter: str | None = str(getattr(user, "protocol_filter")) if user and getattr(user, "protocol_filter") is not None else None
        await edit_or_answer(
            message,
            f"✅ Лимит установлен: <b>{limit}</b>",
            settings_main_kb(limit, True, protocol_filter),
            state,
            media_url="video",
        )

    except ValueError:
        _ = await state.clear()
        await edit_or_answer(
            message,
            "⚠️ Ошибка. Введите целое число.",
            back_to_home(),
            state,
            media_url="video",
        )


@router.callback_query(F.data == "settings_countries")
async def open_settings_countries(callback: CallbackQuery, state: FSMContext):
    if not isinstance(callback.message, Message):
        return
    all_regions = await SubRepo.get_regions()
    user_filter = await UserRepo.get_user_filter(callback.from_user.id)

    text = (
        "<b>🌍 REGIONS FILTER | СТРАНЫ</b>\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        "Отметьте страны, которые вы хотите видеть в подписке.\n"
        "☑️ - Страна включена\n⬜️ - Страна скрыта\n\n"
        "<i>Изменения сохраняются автоматически.</i>"
    )

    await edit_or_answer(
        callback.message,
        text,
        settings_countries_kb(all_regions, user_filter),
        state,
        media_url="video",
    )


@router.callback_query(F.data.startswith("toggle_country_"))
async def toggle_country(callback: CallbackQuery):
    if not callback.data:
        return
    if not isinstance(callback.message, Message):
        return
    region = callback.data.split("toggle_country_")[1]
    user_id = callback.from_user.id

    all_regions = await SubRepo.get_regions()
    user_filter = await UserRepo.get_user_filter(user_id)

    if user_filter is None:
        new_filter = [r for r in all_regions if r != region]
    else:
        new_filter = user_filter.copy()
        if region in new_filter:
            new_filter.remove(region)
        else:
            new_filter.append(region)

    if not new_filter:
        new_filter = ["__EMPTY__"]
    elif set(new_filter) == set(all_regions):
        new_filter = None

    await UserRepo.update_user_filter(user_id, new_filter)
    _ = await callback.message.edit_reply_markup(
        reply_markup=settings_countries_kb(all_regions, new_filter)
    )


@router.callback_query(F.data == "set_all_on")
async def set_all_on(callback: CallbackQuery):
    if not isinstance(callback.message, Message):
        return
    all_regions = await SubRepo.get_regions()
    await UserRepo.update_user_filter(callback.from_user.id, None)
    _ = await callback.message.edit_reply_markup(
        reply_markup=settings_countries_kb(all_regions, None)
    )


@router.callback_query(F.data == "set_all_off")
async def set_all_off(callback: CallbackQuery):
    if not isinstance(callback.message, Message):
        return
    all_regions = await SubRepo.get_regions()
    empty_filter = ["__EMPTY__"]
    await UserRepo.update_user_filter(callback.from_user.id, empty_filter)
    _ = await callback.message.edit_reply_markup(
        reply_markup=settings_countries_kb(all_regions, empty_filter)
    )

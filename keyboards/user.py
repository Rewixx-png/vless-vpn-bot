from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder


def user_main_kb(is_admin: bool = False):
    kb = InlineKeyboardBuilder()

    kb.button(
        text="Подключиться",
        icon_custom_emoji_id="5364130646207772829",
        callback_data="my_subscription",
    )
    kb.button(
        text="Профили",
        icon_custom_emoji_id="6039630677182254664",
        callback_data="groups_list",
    )

    kb.button(
        text="Статус сети",
        icon_custom_emoji_id="6037397706505195857",
        callback_data="public_stats",
    )
    kb.button(
        text="Фильтры и лимит",
        icon_custom_emoji_id="6032742198179532882",
        callback_data="settings_main",
    )

    kb.button(
        text="Как подключить",
        icon_custom_emoji_id="6030848053177486888",
        callback_data="user_instruction",
    )
    kb.button(
        text="TG Прокси",
        icon_custom_emoji_id="5890925363067886150",
        callback_data="tg_proxy_list",
    )

    kb.button(
        text="Поддержать проект",
        icon_custom_emoji_id="6037083366438737901",
        callback_data="donate_info",
    )

    if is_admin:
        kb.button(
            text="Панель Админа",
            icon_custom_emoji_id="5884097155341226387",
            callback_data="admin_home",
        )

    kb.adjust(2, 2, 1, 1, 1)
    return kb.as_markup()


def sub_action_kb(url: str):
    kb = InlineKeyboardBuilder()
    kb.button(
        text="QR-Код",
        icon_custom_emoji_id="5766975922620076409",
        callback_data="sub_qr_main",
    )
    kb.button(
        text="TG Прокси",
        icon_custom_emoji_id="5890925363067886150",
        callback_data="tg_proxy_list",
    )
    kb.button(
        text="Фильтры",
        icon_custom_emoji_id="6032742198179532882",
        callback_data="settings_main",
    )
    kb.button(
        text="Главное меню",
        icon_custom_emoji_id="5938537205847822613",
        callback_data="home",
    )
    kb.adjust(1, 1, 1, 1)
    return kb.as_markup()


def settings_main_kb(current_limit: int, use_fragment: bool = False):
    kb = InlineKeyboardBuilder()
    limit_text = "♾️ Безлимит" if current_limit == 0 else f"{current_limit} шт."
    frag_text = "✅ Вкл" if use_fragment else "❌ Выкл"

    kb.button(
        text="Фильтр стран",
        icon_custom_emoji_id="5776233299424843260",
        callback_data="settings_countries",
    )
    kb.button(
        text="Тип серверов",
        icon_custom_emoji_id="5881806211195605908",
        callback_data="settings_tags",
    )
    kb.button(
        text=f"Лимит: {limit_text}",
        icon_custom_emoji_id="5794164805065514131",
        callback_data="settings_limit",
    )
    kb.button(
        text=f"Фрагментация (DPI): {frag_text}",
        icon_custom_emoji_id="6030445631921721471",
        callback_data="toggle_fragment",
    )
    kb.button(text="🔙 Назад", callback_data="home")
    kb.adjust(2, 2, 1)
    return kb.as_markup()


def settings_tags_kb(selected_tags: list, group_id: int | None = None):
    kb = InlineKeyboardBuilder()

    prefix = "toggle_tag" if group_id is None else f"g_toggle_tag_{group_id}"

    def get_btn(tag, label):
        status = "✅" if tag in selected_tags else "⬜️"
        return f"{status} {label}"

    kb.button(
        text=get_btn("stable", "🛡 Stable (24h Uptime)"),
        callback_data=f"{prefix}_stable",
    )
    kb.button(text=get_btn("ai", "🤖 AI Ready (ChatGPT)"), callback_data=f"{prefix}_ai")
    kb.button(
        text=get_btn("fast", "⚡ High Speed (>100Mbps)"), callback_data=f"{prefix}_fast"
    )
    kb.button(
        text=get_btn("wl", "🔐 Reality / Vision (Stealth)"),
        callback_data=f"{prefix}_wl",
    )
    kb.button(
        text=get_btn("no_ads", "🚫 No-Ads (AdBlock)"), callback_data=f"{prefix}_no_ads"
    )

    kb.adjust(1)

    if group_id is None:
        kb.button(text="💾 Сохранить", callback_data="settings_main")
    else:
        kb.button(text="💾 Сохранить", callback_data=f"group_view_{group_id}")

    return kb.as_markup()


def settings_limit_kb(current: int):
    kb = InlineKeyboardBuilder()
    options = [10, 50, 100, 200, 0]

    for opt in options:
        text = "♾️ MAX" if opt == 0 else f"{opt}"
        if opt == current:
            text = f"✅ {text}"
        kb.button(text=text, callback_data=f"set_limit_{opt}")

    kb.button(text="✏️ Своё число", callback_data="set_limit_custom")
    kb.adjust(3)
    kb.button(text="🔙 Назад", callback_data="settings_main")
    return kb.as_markup()


def settings_countries_kb(
    all_regions: list, selected_regions: list | None, group_id: int | None = None
):
    kb = InlineKeyboardBuilder()

    prefix = "toggle_country" if group_id is None else f"g_toggle_country_{group_id}"

    real_selection = selected_regions
    if selected_regions == ["__EMPTY__"]:
        real_selection = []

    is_all_on = real_selection is None

    for reg in all_regions:
        is_selected = True if is_all_on else (reg in real_selection)
        status = "☑️" if is_selected else "⬜️"
        clean_reg = reg
        kb.button(text=f"{status} {clean_reg}", callback_data=f"{prefix}_{reg}")

    kb.adjust(3)

    if group_id is None:
        if is_all_on:
            kb.row(
                InlineKeyboardButton(
                    text="🧹 Отключить все", callback_data="set_all_off"
                )
            )
        else:
            kb.row(
                InlineKeyboardButton(text="✅ Включить все", callback_data="set_all_on")
            )
        kb.row(InlineKeyboardButton(text="🔙 Назад", callback_data="settings_main"))
    else:
        if is_all_on:
            kb.row(
                InlineKeyboardButton(
                    text="🧹 Отключить все", callback_data=f"g_set_all_off_{group_id}"
                )
            )
        else:
            kb.row(
                InlineKeyboardButton(
                    text="✅ Включить все", callback_data=f"g_set_all_on_{group_id}"
                )
            )
        kb.row(
            InlineKeyboardButton(
                text="💾 Готово", callback_data=f"group_view_{group_id}"
            )
        )

    return kb.as_markup()


def groups_list_kb(groups: list):
    kb = InlineKeyboardBuilder()
    for g in groups:
        kb.button(text=f"📂 {g.name}", callback_data=f"group_view_{g.id}")
    kb.button(
        text="Новая группа",
        icon_custom_emoji_id="5886473311637999700",
        callback_data="group_create",
    )
    kb.button(
        text="Главное меню",
        icon_custom_emoji_id="5938537205847822613",
        callback_data="home",
    )
    kb.adjust(1)
    return kb.as_markup()


def group_view_kb(group_id: int, url: str):
    kb = InlineKeyboardBuilder()
    kb.button(text="📱 QR-Код", callback_data=f"group_qr_{group_id}")
    kb.button(text="🌍 Выбор стран", callback_data=f"group_edit_countries_{group_id}")
    kb.button(text="⚡ Настройка тегов", callback_data=f"group_edit_tags_{group_id}")
    kb.button(text="🗑 Удалить", callback_data=f"group_delete_{group_id}")
    kb.button(text="🔙 Назад", callback_data="groups_list")
    kb.adjust(2, 2, 1)
    return kb.as_markup()


def donate_selection_kb():
    kb = InlineKeyboardBuilder()
    kb.button(text="💎 Crypto Pay", callback_data="crypto_selection")
    kb.button(text="🔙 Отмена", callback_data="home")
    kb.adjust(1)
    return kb.as_markup()


def crypto_amount_kb():
    kb = InlineKeyboardBuilder()
    amounts = [1, 3, 5, 10, 25, 50]
    for amt in amounts:
        kb.button(text=f"{amt} $", callback_data=f"pay_create_{amt}")
    kb.button(text="✏️ Своя сумма", callback_data="pay_custom")
    kb.adjust(3)
    kb.button(text="🔙 Назад", callback_data="donate_info")
    return kb.as_markup()


def pay_link_kb(url: str):
    kb = InlineKeyboardBuilder()
    kb.button(text="💳 К оплате", url=url)
    kb.button(text="🔙 Назад", callback_data="donate_info")
    kb.adjust(1)
    return kb.as_markup()


def back_to_home():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Главное меню",
                    icon_custom_emoji_id="5938537205847822613",
                    callback_data="home",
                )
            ]
        ]
    )


def tg_proxy_kb(proxy_items: list | None = None, offset: int = 0, page_size: int = 16):
    kb = InlineKeyboardBuilder()

    items = proxy_items or []
    total = len(items)
    safe_offset = max(0, min(offset, max(0, total - 1))) if total else 0

    if total > 0:
        page = items[safe_offset : safe_offset + page_size]
        for idx, item in enumerate(page, start=safe_offset + 1):
            link = str(item.get("link", "") or "").strip()
            latency_raw = item.get("latency_ms")
            kind_raw = str(item.get("kind", "mtproto") or "mtproto").strip().lower()
            kind_text = "SOCKS5" if kind_raw == "socks5" else "MTProto"
            try:
                latency_ms = int(latency_raw)
                latency_text = f"{latency_ms}ms"
            except Exception:
                latency_text = "~"

            if not link:
                continue

            button_text = f"{idx}. {kind_text} - {latency_text}"
            if len(button_text) > 64:
                button_text = f"#{idx} {kind_text} {latency_text}"
            kb.button(text=button_text, url=link)

        kb.adjust(2)

        nav_row = []
        prev_offset = safe_offset - page_size
        next_offset = safe_offset + page_size

        if prev_offset >= 0:
            nav_row.append(
                InlineKeyboardButton(
                    text="⬅️ Назад", callback_data=f"tg_proxy_page_{prev_offset}"
                )
            )
        if next_offset < total:
            nav_row.append(
                InlineKeyboardButton(
                    text="➡️ Дальше", callback_data=f"tg_proxy_page_{next_offset}"
                )
            )

        if nav_row:
            kb.row(*nav_row)

    kb.row(
        InlineKeyboardButton(
            text="🔄 Обновить список", callback_data="tg_proxy_refresh"
        ),
        InlineKeyboardButton(
            text="Главное меню",
            icon_custom_emoji_id="5938537205847822613",
            callback_data="home",
        ),
    )
    return kb.as_markup()

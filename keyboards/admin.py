from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

def _short_text(value: str, max_len: int) -> str:
    text = " ".join(str(value or "").split()).strip()
    if len(text) <= max_len:
        return text
    if max_len <= 1:
        return text[:max_len]
    return text[: max_len - 1] + "…"


_ADMIN_REGION_MAP = {
    "unk": "Неизвестно",
    "unknown": "Неизвестно",
    "russia": "Россия",
    "germany": "Германия",
    "netherlands": "Нидерланды",
    "italy": "Италия",
    "sweden": "Швеция",
    "poland": "Польша",
    "france": "Франция",
    "usa": "США",
    "united states": "США",
    "uk": "Великобритания",
    "united kingdom": "Великобритания",
    "lt": "Литва",
    "lithuania": "Литва",
}


def _format_admin_region_name(region_raw: str) -> str:
    raw = str(region_raw or "").strip()
    if not raw:
        return "Неизвестно"

    country_part = raw
    parts = raw.split(" ", 1)
    if len(parts) == 2 and any(ord(ch) > 127 for ch in parts[0]):
        country_part = parts[1].strip()

    key = country_part.lower().strip()
    mapped = _ADMIN_REGION_MAP.get(key)
    if mapped:
        return mapped

    if key in {"", "none", "null"}:
        return "Неизвестно"

    if "unk" in key or "unknown" in key:
        return "Неизвестно"

    return _short_text(country_part, 18)


def _sub_display_name(sub, display_index: int) -> str:
    region_name = _format_admin_region_name(getattr(sub, "region", ""))
    safe_index = max(int(display_index or 1), 1)
    return f"{region_name} {safe_index}"


def _sub_button_text(prefix: str, sub, speed: float, display_index: int) -> str:
    speed_suffix = f" | ⚡️{float(speed):.1f}Mb/s"
    max_total_len = 64
    min_name_len = 6

    name = _sub_display_name(sub, display_index)
    free_space = max_total_len - len(prefix) - len(speed_suffix)
    name_len = max(min_name_len, free_space)
    name = _short_text(name, name_len)

    text = f"{prefix}{name}{speed_suffix}"
    if len(text) > max_total_len:
        overflow = len(text) - max_total_len
        name = _short_text(name, max(min_name_len, len(name) - overflow))
        text = f"{prefix}{name}{speed_suffix}"
    return text


def _bulk_submit_text(
    mode: str,
    selected_count: int,
    total_in_region: int | None = None,
) -> str:
    if mode == "exclude":
        if total_in_region is None:
            return "🚫 В ЧС всё, кроме выбранного"
        to_blacklist = max(int(total_in_region) - int(selected_count), 0)
        return f"🚫 В ЧС всё, кроме выбранного ({to_blacklist})"
    return f"🚫 Отправить в ЧС ({selected_count})"


def main_admin_kb(collector_active: bool = True):
    kb = InlineKeyboardBuilder()

    kb.button(text="➕ Добавить конфиги", callback_data="admin_add")
    kb.button(text="🗂 Инвентарь БД", callback_data="admin_manage")

    kb.button(text="🔗 Источники", callback_data="admin_sources")

    kb.button(text="🔄 Быстрый recheck", callback_data="admin_recheck_menu")
    kb.button(text="🌍 Исправить регионы", callback_data="admin_fix_regions")

    kb.button(text="👥 Пользователи", callback_data="admin_users_list_0")
    kb.button(text="📊 Статистика", callback_data="admin_stats")

    kb.button(text="🛡 Stable-лист", callback_data="admin_stable_list")

    coll_text = "🟢 Коллектор: ON" if collector_active else "🔴 Коллектор: OFF"
    kb.button(text=coll_text, callback_data="toggle_collector")

    kb.button(text="🌐 Домен/URL", callback_data="admin_domain")
    kb.button(text="📢 Рассылка", callback_data="admin_broadcast")

    kb.button(text="↩️ Выход", callback_data="user_mode")

    kb.adjust(2, 2, 2, 2, 2, 1)
    return kb.as_markup()


def sources_list_kb(sources: list):
    kb = InlineKeyboardBuilder()

    for s in sources:
        status = "✅" if s.is_enabled else "❌"
        title = s.title if s.title else s.url.split("//")[1][:20]
        kb.button(text=f"{status} {title}", callback_data=f"src_toggle_{s.id}")
        kb.button(text="🗑", callback_data=f"src_del_{s.id}")

    kb.adjust(2)

    kb.row(InlineKeyboardButton(text="➕ Добавить источник", callback_data="src_add"))
    kb.row(
        InlineKeyboardButton(
            text="⚡ Запустить Collector", callback_data="src_force_run"
        )
    )
    kb.row(InlineKeyboardButton(text="🔄 Обновить статус", callback_data="admin_sources"))
    kb.row(InlineKeyboardButton(text="🔙 Назад", callback_data="admin_home"))

    return kb.as_markup()


def recheck_menu_kb():
    kb = InlineKeyboardBuilder()
    kb.button(text="♻️ Full recheck (1 проход)", callback_data="admin_recheck_run_all_1")
    kb.button(text="⚡ Active (1 проход)", callback_data="admin_recheck_run_active_1")
    kb.button(text="💀 Dead recheck", callback_data="admin_recheck_run_dead_1")
    kb.button(text="🛑 Завершить активную", callback_data="admin_recheck_stop_active")
    kb.button(text="🌍 Обновить GeoIP", callback_data="admin_recheck_regions_force")
    kb.button(text="🔙 Назад", callback_data="admin_home")
    kb.adjust(1, 1, 1, 1, 1, 1)
    return kb.as_markup()


def users_list_kb(users: list, offset: int, total: int):
    kb = InlineKeyboardBuilder()
    limit = 10

    for u in users:
        username = f"@{u.username}" if u.username else str(u.id)
        kb.button(
            text=f"👤 {username}", callback_data=f"admin_user_view_{u.id}_{offset}"
        )

    nav_row = []
    if offset > 0:
        nav_row.append(
            InlineKeyboardButton(
                text="⬅️", callback_data=f"admin_users_list_{offset - limit}"
            )
        )
    if offset + limit < total:
        nav_row.append(
            InlineKeyboardButton(
                text="➡️", callback_data=f"admin_users_list_{offset + limit}"
            )
        )

    kb.adjust(2)

    if nav_row:
        kb.row(*nav_row)

    kb.row(InlineKeyboardButton(text="🔙 Назад", callback_data="admin_home"))
    return kb.as_markup()


def user_detail_kb(user_id: int, back_offset: int):
    kb = InlineKeyboardBuilder()
    kb.button(text="🔙 Назад к списку", callback_data=f"admin_users_list_{back_offset}")
    return kb.as_markup()


def stable_list_kb(candidates: list):
    kb = InlineKeyboardBuilder()
    kb.button(text="🔄 Обновить", callback_data="admin_stable_list")
    kb.button(text="🔙 Назад", callback_data="admin_home")
    kb.adjust(1)
    return kb.as_markup()


def back_to_admin():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔙 В админку", callback_data="admin_home")]
        ]
    )


def regions_kb(regions: list, prefix: str):
    kb = InlineKeyboardBuilder()

    for reg in regions:
        kb.button(text=f"{reg}", callback_data=f"{prefix}_{reg}")

    kb.adjust(3)

    if "manage" in prefix:
        kb.row(
            InlineKeyboardButton(
                text="☑️ Массовый ЧС", callback_data="admin_bulk_blacklist_menu"
            )
        )
        kb.row(
            InlineKeyboardButton(
                text="🚫 Blacklist Unknown", callback_data="admin_delete_unknown"
            )
        )
        kb.row(
            InlineKeyboardButton(
                text="🔥 ОЧИСТИТЬ ВСЮ БАЗУ", callback_data="admin_delete_all"
            )
        )

    back_callback = "admin_home" if "manage" in prefix else "home"
    kb.row(InlineKeyboardButton(text="🔙 Назад", callback_data=back_callback))
    return kb.as_markup()


def bulk_blacklist_regions_kb(regions: list, selected_count: int, mode: str = "include"):
    kb = InlineKeyboardBuilder()

    include_active = mode == "include"
    include_text = f"{'✅' if include_active else '☑️'} В ЧС выбранное"
    exclude_text = f"{'✅' if not include_active else '☑️'} Не в ЧС выбранное"

    for region in regions:
        kb.button(text=str(region), callback_data=f"bulk_bl_region_{region}")

    kb.adjust(3)
    kb.row(
        InlineKeyboardButton(text=include_text, callback_data="bulk_bl_mode_include"),
        InlineKeyboardButton(text=exclude_text, callback_data="bulk_bl_mode_exclude"),
    )
    kb.row(
        InlineKeyboardButton(
            text=_bulk_submit_text(mode, selected_count),
            callback_data="bulk_bl_submit",
        )
    )
    kb.row(
        InlineKeyboardButton(
            text="🧹 Очистить выбор",
            callback_data="bulk_bl_clear",
        )
    )
    kb.row(InlineKeyboardButton(text="🔙 Назад", callback_data="admin_manage"))
    return kb.as_markup()


def bulk_blacklist_subs_kb(
    subs: list,
    page: int,
    total_pages: int,
    selected_ids: set[int],
    index_offset: int = 0,
    mode: str = "include",
    total_in_region: int | None = None,
    selected_count_override: int | None = None,
):
    kb = InlineKeyboardBuilder()

    selected_count = (
        int(selected_count_override)
        if selected_count_override is not None
        else len(selected_ids)
    )

    include_active = mode == "include"
    include_text = f"{'✅' if include_active else '☑️'} В ЧС выбранное"
    exclude_text = f"{'✅' if not include_active else '☑️'} Не в ЧС выбранное"

    for idx, sub in enumerate(subs, start=1):
        is_selected = sub.id in selected_ids
        if mode == "exclude":
            marker = "🛡" if is_selected else "⬜️"
        else:
            marker = "✅" if is_selected else "⬜️"
        speed = float(sub.speed_mbps or 0.0)
        text = _sub_button_text(
            f"{marker} #{sub.id} ",
            sub,
            speed,
            display_index=index_offset + idx,
        )
        kb.button(text=text, callback_data=f"bulk_bl_toggle_{sub.id}")

    kb.adjust(1)

    nav_buttons = []
    if page > 0:
        nav_buttons.append(
            InlineKeyboardButton(
                text="⬅️",
                callback_data=f"bulk_bl_page_{page - 1}",
            )
        )
    nav_buttons.append(
        InlineKeyboardButton(text=f"{page + 1}/{total_pages}", callback_data="noop")
    )
    if page < total_pages - 1:
        nav_buttons.append(
            InlineKeyboardButton(
                text="➡️",
                callback_data=f"bulk_bl_page_{page + 1}",
            )
        )

    kb.row(*nav_buttons)
    kb.row(
        InlineKeyboardButton(text=include_text, callback_data="bulk_bl_mode_include"),
        InlineKeyboardButton(text=exclude_text, callback_data="bulk_bl_mode_exclude"),
    )
    kb.row(
        InlineKeyboardButton(
            text=_bulk_submit_text(mode, selected_count, total_in_region),
            callback_data="bulk_bl_submit",
        )
    )
    kb.row(
        InlineKeyboardButton(
            text="🧹 Очистить выбор",
            callback_data="bulk_bl_clear",
        )
    )
    kb.row(
        InlineKeyboardButton(
            text="🌍 Сменить регион",
            callback_data="admin_bulk_blacklist_menu",
        )
    )
    kb.row(InlineKeyboardButton(text="🔙 Назад", callback_data="admin_manage"))
    return kb.as_markup()


def confirm_delete_all_kb():
    kb = InlineKeyboardBuilder()
    kb.button(text="🔥 ДА, УДАЛИТЬ ВСЕ", callback_data="admin_delete_all_confirm")
    kb.button(text="🔙 ОТМЕНА", callback_data="admin_manage")
    kb.adjust(1)
    return kb.as_markup()


def confirm_delete_unknown_kb():
    kb = InlineKeyboardBuilder()
    kb.button(text="🚫 В ЧЕРНЫЙ СПИСОК", callback_data="admin_delete_unknown_confirm")
    kb.button(text="🔙 ОТМЕНА", callback_data="admin_manage")
    kb.adjust(1)
    return kb.as_markup()


def confirm_delete_country_kb(region: str):
    kb = InlineKeyboardBuilder()
    kb.button(text=f"🗑 УДАЛИТЬ {region}", callback_data=f"confirm_del_country_{region}")
    kb.button(text="🔙 ОТМЕНА", callback_data=f"manage_region_{region}")
    kb.adjust(1)
    return kb.as_markup()


def subs_list_kb(
    subs: list,
    region: str,
    page: int,
    total_pages: int,
    index_offset: int = 0,
):
    kb = InlineKeyboardBuilder()

    kb.row(
        InlineKeyboardButton(
            text=f"🗑 Удалить ВСЕ ({region})",
            callback_data=f"ask_delete_country_{region}",
        )
    )

    for idx, sub in enumerate(subs, start=1):
        status_icon = "🟢" if sub.is_active else "🔴"
        lat = sub.speed_mbps if hasattr(sub, "speed_mbps") and sub.speed_mbps > 0 else 0
        text = _sub_button_text(
            f"{status_icon} #{sub.id} ",
            sub,
            float(lat),
            display_index=index_offset + idx,
        )
        kb.button(text=text, callback_data=f"sub_detail_{sub.id}")

    kb.adjust(1, 2)

    nav_buttons = []
    if page > 0:
        nav_buttons.append(
            InlineKeyboardButton(
                text="⬅️", callback_data=f"manage_region_{region}:{page - 1}"
            )
        )

    nav_buttons.append(
        InlineKeyboardButton(text=f"{page + 1}/{total_pages}", callback_data="noop")
    )

    if page < total_pages - 1:
        nav_buttons.append(
            InlineKeyboardButton(
                text="➡️", callback_data=f"manage_region_{region}:{page + 1}"
            )
        )

    kb.row(*nav_buttons)
    kb.row(InlineKeyboardButton(text="🔙 К регионам", callback_data="admin_manage"))

    return kb.as_markup()


def sub_control_kb(sub_id: int, is_active: bool, region: str):
    kb = InlineKeyboardBuilder()
    active_text = "⏸ Отключить" if is_active else "▶️ Включить"
    kb.button(text=active_text, callback_data=f"sub_toggle_{sub_id}")
    kb.button(text="❌ УДАЛИТЬ", callback_data=f"sub_delete_{sub_id}")
    kb.button(text="🔙 Назад", callback_data=f"manage_region_{region}")
    kb.adjust(2, 1)
    return kb.as_markup()


def domain_error_kb(domain: str):
    kb = InlineKeyboardBuilder()
    safe_domain = domain[:40]
    kb.button(
        text="⚠️ Всё равно сохранить", callback_data=f"force_save_domain:{safe_domain}"
    )
    kb.button(text="🔙 Отмена", callback_data="admin_domain")
    kb.adjust(1)
    return kb.as_markup()


def stats_kb():
    kb = InlineKeyboardBuilder()
    kb.button(text="📥 Список Юзеров (.txt)", callback_data="admin_dl_users")
    kb.button(text="🗑 Очистить ЧС", callback_data="admin_clear_blacklist_confirm")
    kb.button(text="🔄 Обновить", callback_data="admin_stats")
    kb.button(text="🔙 Назад", callback_data="admin_home")
    kb.adjust(2, 2)
    return kb.as_markup()

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

def user_main_kb(is_admin: bool = False):
    kb = InlineKeyboardBuilder()
    kb.button(text="📥 Моя Подписка", callback_data="my_subscription")
    kb.button(text="📂 Мои Группы", callback_data="groups_list")
    kb.button(text="⚙️ Настройки", callback_data="settings_main")
    kb.button(text="📊 Статус сети", callback_data="public_stats")
    kb.button(text="📱 Приложения", callback_data="apps_menu")
    kb.button(text="ℹ️ Инструкция", callback_data="user_instruction") 
    kb.button(text="💜 Поддержать", callback_data="donate_info")

    if is_admin:
        kb.button(text="🛠 Админ Панель", callback_data="admin_home")

    kb.adjust(1, 1, 1, 2, 2, 1) 
    return kb.as_markup()

def sub_action_kb(url: str, deep_link: str = None):
    kb = InlineKeyboardBuilder()
    kb.button(text="⚙️ Настройки фильтров", callback_data="settings_main")
    kb.button(text="🔙 Главное меню", callback_data="home")
    kb.adjust(1)
    return kb.as_markup()

def settings_main_kb(current_limit: int):
    kb = InlineKeyboardBuilder()
    limit_text = "♾️ Все" if current_limit == 0 else f"{current_limit} шт."
    kb.button(text="🌍 Выбор стран (Общий)", callback_data="settings_countries")
    kb.button(text="🏷 Теги (AI, Fast)", callback_data="settings_tags")
    kb.button(text=f"🔢 Лимит: {limit_text}", callback_data="settings_limit")
    kb.button(text="🔙 В главное меню", callback_data="home")
    kb.adjust(1)
    return kb.as_markup()

def settings_tags_kb(selected_tags: list, group_id: int = None):
    kb = InlineKeyboardBuilder()
    
    prefix = "toggle_tag" if group_id is None else f"g_toggle_tag_{group_id}"
    
    ai_status = "🟢" if "ai" in selected_tags else "🔴"
    kb.button(text=f"{ai_status} [AI] (ChatGPT/Gemini)", callback_data=f"{prefix}_ai")
    
    fast_status = "🟢" if "fast" in selected_tags else "🔴"
    kb.button(text=f"{fast_status} [Fast] (<100ms)", callback_data=f"{prefix}_fast")
    
    wl_status = "🟢" if "wl" in selected_tags else "🔴"
    kb.button(text=f"{wl_status} [WL] (Reality)", callback_data=f"{prefix}_wl")
    
    kb.adjust(1)
    
    if group_id is None:
        kb.button(text="🔙 Назад", callback_data="settings_main")
    else:
        kb.button(text="💾 Сохранить и выйти", callback_data=f"group_view_{group_id}")
        
    return kb.as_markup()

def settings_limit_kb(current: int):
    kb = InlineKeyboardBuilder()
    options = [10, 50, 100, 200, 0]
    for opt in options:
        text = "♾️ Безлимит" if opt == 0 else f"{opt} шт."
        if opt == current: text = f"✅ {text}"
        kb.button(text=text, callback_data=f"set_limit_{opt}")
    kb.button(text="✍️ Свой вариант", callback_data="set_limit_custom")
    kb.adjust(2)
    kb.button(text="🔙 Назад", callback_data="settings_main")
    return kb.as_markup()

def settings_countries_kb(all_regions: list, selected_regions: list | None, group_id: int = None):
    kb = InlineKeyboardBuilder()

    prefix = "toggle_country" if group_id is None else f"g_toggle_country_{group_id}"

    # Если selected_regions содержит специальный маркер пустоты, показываем всё выключенным
    # Если None - показываем всё включенным (по умолчанию)
    # Если список - показываем выбор
    
    real_selection = selected_regions
    if selected_regions == ["__EMPTY__"]:
        real_selection = []
    
    is_all_on = real_selection is None

    for reg in all_regions:
        is_selected = True if is_all_on else (reg in real_selection)
        status = "🟢" if is_selected else "🔴"
        text = f"{status} {reg}"
        kb.button(text=text, callback_data=f"{prefix}_{reg}")

    kb.adjust(3)

    if group_id is None:
        if is_all_on:
            kb.row(InlineKeyboardButton(text="🧹 Снять все", callback_data="set_all_off"))
        else:
            kb.row(InlineKeyboardButton(text="✅ Выбрать все", callback_data="set_all_on"))
        kb.row(InlineKeyboardButton(text="🔙 Назад", callback_data="settings_main"))
    else:
        # Для групп кнопки управления
        if is_all_on:
            kb.row(InlineKeyboardButton(text="🧹 Снять все", callback_data=f"g_set_all_off_{group_id}"))
        else:
            kb.row(InlineKeyboardButton(text="✅ Выбрать все", callback_data=f"g_set_all_on_{group_id}"))
        kb.row(InlineKeyboardButton(text="💾 Сохранить и выйти", callback_data=f"group_view_{group_id}"))

    return kb.as_markup()

def groups_list_kb(groups: list):
    kb = InlineKeyboardBuilder()
    for g in groups:
        kb.button(text=f"📂 {g.name}", callback_data=f"group_view_{g.id}")
    kb.button(text="➕ Создать группу", callback_data="group_create")
    kb.button(text="🔙 Назад", callback_data="home")
    kb.adjust(1)
    return kb.as_markup()

def group_view_kb(group_id: int, url: str):
    kb = InlineKeyboardBuilder()
    kb.button(text="🌍 Изменить страны", callback_data=f"group_edit_countries_{group_id}")
    kb.button(text="🏷 Изменить теги", callback_data=f"group_edit_tags_{group_id}")
    kb.button(text="🗑 Удалить группу", callback_data=f"group_delete_{group_id}")
    kb.button(text="🔙 К списку групп", callback_data="groups_list")
    kb.adjust(1)
    return kb.as_markup()

def apps_os_kb():
    kb = InlineKeyboardBuilder()
    kb.button(text="🤖 Android", callback_data="apps_os_android")
    kb.button(text="🍏 iOS (iPhone)", callback_data="apps_os_ios")
    kb.button(text="💻 Windows", callback_data="apps_os_windows")
    kb.button(text="🍎 macOS", callback_data="apps_os_macos")
    kb.button(text="🐧 Linux", callback_data="apps_os_linux")
    kb.button(text="🔙 Главное меню", callback_data="home")
    kb.adjust(2, 2, 1, 1)
    return kb.as_markup()

def apps_links_kb(apps_list: list):
    kb = InlineKeyboardBuilder()
    for app in apps_list:
        kb.button(text=f"⬇️ {app['name']}", url=app["url"])
    kb.adjust(1)
    kb.button(text="🔙 К выбору ОС", callback_data="apps_menu")
    return kb.as_markup()

def donate_selection_kb():
    kb = InlineKeyboardBuilder()
    kb.button(text="💎 Crypto Pay (USDT/TON)", callback_data="crypto_selection")
    kb.button(text="🔙 Назад в меню", callback_data="home")
    kb.adjust(1)
    return kb.as_markup()

def crypto_amount_kb():
    kb = InlineKeyboardBuilder()
    amounts = [1, 3, 5, 10]
    for amt in amounts:
        kb.button(text=f"💎 {amt} USDT", callback_data=f"pay_create_{amt}")
    kb.button(text="✍️ Своя сумма", callback_data="pay_custom")
    kb.adjust(2)
    kb.button(text="🔙 Назад", callback_data="donate_info")
    return kb.as_markup()

def pay_link_kb(url: str):
    kb = InlineKeyboardBuilder()
    kb.button(text="👉 Оплатить счет", url=url)
    kb.button(text="🔙 В меню", callback_data="donate_info")
    kb.adjust(1)
    return kb.as_markup()

def back_to_home():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Главное меню", callback_data="home")]
    ])
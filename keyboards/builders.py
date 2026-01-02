from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

# --- KEYBOARDS ДЛЯ ЮЗЕРА ---

def user_main_kb(is_admin: bool = False):
    kb = InlineKeyboardBuilder()
    
    kb.button(text="📥 Получить подписку", callback_data="get_sub_menu")
    kb.button(text="💸 Поддержать автора", callback_data="donate_info")
    
    if is_admin:
        kb.button(text="🛠 Админ Панель", callback_data="admin_home")
        
    kb.adjust(1)
    return kb.as_markup()

def donate_selection_kb():
    kb = InlineKeyboardBuilder()
    kb.button(text="💎 Crypto Pay (Автоматически)", callback_data="crypto_selection")
    kb.button(text="🔙 В главное меню", callback_data="home")
    kb.adjust(1)
    return kb.as_markup()

def crypto_amount_kb():
    kb = InlineKeyboardBuilder()
    amounts = [1, 3, 5, 10]
    for amt in amounts:
        kb.button(text=f"{amt} USDT", callback_data=f"pay_create_{amt}")
    kb.button(text="✍️ Другая сумма", callback_data="pay_custom")
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
        [InlineKeyboardButton(text="🔙 В главное меню", callback_data="home")]
    ])

# --- KEYBOARDS ДЛЯ АДМИНА ---

def main_admin_kb():
    kb = InlineKeyboardBuilder()
    kb.button(text="➕ Добавить подписки", callback_data="admin_add")
    kb.button(text="🗑 Управление", callback_data="admin_manage")
    kb.button(text="♻️ Перепроверить базу", callback_data="admin_recheck") # НОВАЯ КНОПКА
    kb.button(text="📊 Статистика", callback_data="admin_stats")
    kb.button(text="📢 Рассылка", callback_data="admin_broadcast")
    kb.button(text="👤 Режим Юзера", callback_data="user_mode")
    kb.adjust(1, 2, 1, 1, 1)
    return kb.as_markup()

def back_to_admin():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 В админку", callback_data="admin_home")]
    ])

def regions_kb(regions: list, prefix: str):
    kb = InlineKeyboardBuilder()
    for reg in regions:
        kb.button(text=f"{reg}", callback_data=f"{prefix}_{reg}")
    kb.adjust(2)
    back_callback = "admin_home" if "manage" in prefix else "home"
    kb.button(text="🔙 Назад", callback_data=back_callback)
    return kb.as_markup()

def subs_list_kb(subs: list, region: str):
    kb = InlineKeyboardBuilder()
    for sub in subs:
        status_icon = "🟢" if sub.is_active else "🔴"
        text = f"{status_icon} {sub.latency_ms}ms | ID:{sub.id}"
        kb.button(text=text, callback_data=f"sub_detail_{sub.id}")
    kb.adjust(1)
    kb.button(text="🔙 Назад к регионам", callback_data="admin_manage")
    return kb.as_markup()

def sub_control_kb(sub_id: int, is_active: bool, region: str):
    kb = InlineKeyboardBuilder()
    active_text = "⏸ Выключить" if is_active else "▶️ Включить"
    kb.button(text=active_text, callback_data=f"sub_toggle_{sub_id}")
    kb.button(text="❌ УДАЛИТЬ НАВСЕГДА", callback_data=f"sub_delete_{sub_id}")
    kb.button(text="🔙 К списку", callback_data=f"manage_region_{region}")
    kb.adjust(1)
    return kb.as_markup()
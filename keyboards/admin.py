from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

def main_admin_kb():
    kb = InlineKeyboardBuilder()
    kb.button(text="➕ Загрузить ключи", callback_data="admin_add")
    kb.button(text="🗑 Управление базой", callback_data="admin_manage")
    kb.button(text="♻️ Force Recheck", callback_data="admin_recheck")
    kb.button(text="🌍 Fix Unknowns", callback_data="admin_fix_regions")
    kb.button(text="📊 Статистика", callback_data="admin_stats")
    kb.button(text="📢 Рассылка", callback_data="admin_broadcast")
    kb.button(text="👤 Выйти в режим Юзера", callback_data="user_mode")
    kb.adjust(2, 2, 1, 1, 1)
    return kb.as_markup()

def back_to_admin():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 В админку", callback_data="admin_home")]
    ])

def regions_kb(regions: list, prefix: str):
    kb = InlineKeyboardBuilder()
    for reg in regions:
        kb.button(text=f"{reg}", callback_data=f"{prefix}_{reg}")
    
    # Делаем 3 кнопки в ряд для компактности
    kb.adjust(3)
    
    back_callback = "admin_home" if "manage" in prefix else "home"
    kb.row(InlineKeyboardButton(text="🔙 Назад", callback_data=back_callback))
    return kb.as_markup()

def subs_list_kb(subs: list, region: str):
    kb = InlineKeyboardBuilder()
    for sub in subs:
        status_icon = "🟢" if sub.is_active else "🔴"
        text = f"{status_icon} #{sub.id} | ⚡️{sub.latency_ms}ms"
        kb.button(text=text, callback_data=f"sub_detail_{sub.id}")
    kb.adjust(2)
    kb.button(text="🔙 К регионам", callback_data="admin_manage")
    return kb.as_markup()

def sub_control_kb(sub_id: int, is_active: bool, region: str):
    kb = InlineKeyboardBuilder()
    active_text = "⏸ Отключить" if is_active else "▶️ Включить"
    kb.button(text=active_text, callback_data=f"sub_toggle_{sub_id}")
    kb.button(text="❌ УДАЛИТЬ", callback_data=f"sub_delete_{sub_id}")
    kb.button(text="🔙 Назад", callback_data=f"manage_region_{region}")
    kb.adjust(2, 1)
    return kb.as_markup()
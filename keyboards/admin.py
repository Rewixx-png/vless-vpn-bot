from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

def main_admin_kb(collector_active: bool = True):
    kb = InlineKeyboardBuilder()
    
    # 1. Manage & Inventory
    kb.button(text="➕ Добавить ключи", callback_data="admin_add")
    kb.button(text="📂 Управление базой", callback_data="admin_manage")
    
    # 2. Checks & Maintenance (Grouped)
    kb.button(text="📡 Menu Recheck", callback_data="admin_recheck_menu")
    kb.button(text="🌍 Fix Unknowns", callback_data="admin_fix_regions")
    
    # 3. Users & Stats
    kb.button(text="👥 Меню Юзеров", callback_data="admin_users_list_0")
    kb.button(text="📊 Статистика", callback_data="admin_stats")
    
    # 4. Special Features
    kb.button(text="🛡 Stable List", callback_data="admin_stable_list")
    
    # Collector Toggle
    coll_text = "🟢 Collector ON" if collector_active else "🔴 Collector OFF"
    kb.button(text=coll_text, callback_data="toggle_collector")
    
    # Misc
    kb.button(text="⚙️ Домен", callback_data="admin_domain")
    kb.button(text="📢 Рассылка", callback_data="admin_broadcast")
    
    kb.button(text="↩️ Режим Юзера", callback_data="user_mode")
    
    kb.adjust(2, 2, 2, 1, 1, 2, 1)
    return kb.as_markup()

def recheck_menu_kb():
    kb = InlineKeyboardBuilder()
    kb.button(text="♻️ Full Recheck (Все)", callback_data="admin_recheck_run_all")
    kb.button(text="⚡ Active Recheck (Живые)", callback_data="admin_recheck_run_active")
    kb.button(text="💀 Dead Recheck (Мертвые)", callback_data="admin_recheck_run_dead")
    kb.button(text="🔙 Назад", callback_data="admin_home")
    kb.adjust(1)
    return kb.as_markup()

def users_list_kb(users: list, offset: int, total: int):
    kb = InlineKeyboardBuilder()
    limit = 10
    
    for u in users:
        username = f"@{u.username}" if u.username else str(u.id)
        kb.button(text=f"👤 {username}", callback_data=f"admin_user_view_{u.id}_{offset}")
    
    nav_row = []
    if offset > 0:
        nav_row.append(InlineKeyboardButton(text="⬅️", callback_data=f"admin_users_list_{offset - limit}"))
    if offset + limit < total:
        nav_row.append(InlineKeyboardButton(text="➡️", callback_data=f"admin_users_list_{offset + limit}"))
        
    kb.adjust(2) # User buttons 2 per row
    
    if nav_row:
        kb.row(*nav_row)
        
    kb.row(InlineKeyboardButton(text="🔙 Назад", callback_data="admin_home"))
    return kb.as_markup()

def user_detail_kb(user_id: int, back_offset: int):
    kb = InlineKeyboardBuilder()
    # Add actions if needed later (e.g., Ban)
    kb.button(text="🔙 Назад к списку", callback_data=f"admin_users_list_{back_offset}")
    return kb.as_markup()

def stable_list_kb(candidates: list):
    kb = InlineKeyboardBuilder()
    # No interaction needed for now, just view
    kb.button(text="🔄 Обновить", callback_data="admin_stable_list")
    kb.button(text="🔙 Назад", callback_data="admin_home")
    kb.adjust(1)
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
    
    if "manage" in prefix:
        kb.row(InlineKeyboardButton(text="🚫 Blacklist Unknown", callback_data="admin_delete_unknown"))
        kb.row(InlineKeyboardButton(text="🔥 ОЧИСТИТЬ ВСЮ БАЗУ", callback_data="admin_delete_all"))
    
    back_callback = "admin_home" if "manage" in prefix else "home"
    kb.row(InlineKeyboardButton(text="🔙 Назад", callback_data=back_callback))
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

def subs_list_kb(subs: list, region: str):
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text=f"🗑 Удалить все ({region})", callback_data=f"ask_delete_country_{region}"))

    for sub in subs:
        status_icon = "🟢" if sub.is_active else "🔴"
        text = f"{status_icon} #{sub.id} | ⚡️{sub.latency_ms}ms"
        kb.button(text=text, callback_data=f"sub_detail_{sub.id}")
    
    kb.adjust(1, 2)
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
    kb.button(text="⚠️ Всё равно сохранить", callback_data=f"force_save_domain:{safe_domain}")
    kb.button(text="🔙 Отмена", callback_data="admin_domain")
    kb.adjust(1)
    return kb.as_markup()
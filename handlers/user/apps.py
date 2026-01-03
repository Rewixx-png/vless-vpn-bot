from aiogram import Router, F
from aiogram.types import CallbackQuery
from aiogram.fsm.context import FSMContext
from keyboards.user import apps_os_kb, apps_links_kb

router = Router()

APPS_DATA = {
    "android": [
        {"name": "🤖 v2rayNG (Рекомендуем)", "url": "https://play.google.com/store/apps/details?id=com.v2ray.ang"},
        {"name": "🐱 NekoBox (Мощный)", "url": "https://github.com/MatsuriDayo/NekoBoxForAndroid/releases"},
        {"name": "🔥 Hiddify (Красивый UI)", "url": "https://play.google.com/store/apps/details?id=app.hiddify.com"},
        {"name": "⚙️ Clash Meta (Для профи)", "url": "https://github.com/MetaCubeX/ClashMetaForAndroid/releases"},
        {"name": "📦 Sing-box (Официальный)", "url": "https://play.google.com/store/apps/details?id=io.nekohasekai.sfa"}
    ],
    "ios": [
        {"name": "🍏 V2Box (Бесплатно)", "url": "https://apps.apple.com/us/app/v2box-v2ray-client/id6446814690"},
        {"name": "🚀 Streisand (Бесплатно)", "url": "https://apps.apple.com/us/app/streisand/id6450534064"},
        {"name": "🚀 Shadowrocket ($2.99)", "url": "https://apps.apple.com/us/app/shadowrocket/id932747118"}
    ],
    "windows": [
        {"name": "💻 v2rayN (GitHub)", "url": "https://github.com/2dust/v2rayN/releases"},
        {"name": "🔥 Hiddify (Windows)", "url": "https://github.com/hiddify/hiddify-next/releases"},
        {"name": "🐱 NekoRay", "url": "https://github.com/MatsuriDayo/nekoray/releases"}
    ],
    "macos": [
        {"name": "🍏 V2Box (Mac AppStore)", "url": "https://apps.apple.com/us/app/v2box-v2ray-client/id6446814690"},
        {"name": "🦊 FoXray", "url": "https://apps.apple.com/us/app/foxray/id6448898396"},
        {"name": "🔥 Hiddify (MacOS)", "url": "https://github.com/hiddify/hiddify-next/releases"}
    ],
    "linux": [
        {"name": "🐧 NekoRay (AppImage)", "url": "https://github.com/MatsuriDayo/nekoray/releases"},
        {"name": "🔥 Hiddify (Linux)", "url": "https://github.com/hiddify/hiddify-next/releases"}
    ]
}

@router.callback_query(F.data == "apps_menu")
async def show_apps_os_selection(callback: CallbackQuery, state: FSMContext):
    await state.update_data(last_msg_id=callback.message.message_id)
    await callback.message.edit_text(
        "📱 <b>Выберите ваше устройство:</b>\n\n"
        "Мы подобрали лучшие клиенты с поддержкой X-Ray (VLESS/Reality).",
        parse_mode="HTML",
        reply_markup=apps_os_kb()
    )

@router.callback_query(F.data.startswith("apps_os_"))
async def show_apps_list(callback: CallbackQuery, state: FSMContext):
    os_key = callback.data.split("apps_os_")[1]
    apps = APPS_DATA.get(os_key, [])
    
    os_names = {
        "android": "Android 🤖",
        "ios": "iOS (iPhone/iPad) 🍏",
        "windows": "Windows 💻",
        "macos": "macOS 🍎",
        "linux": "Linux 🐧"
    }
    
    os_title = os_names.get(os_key, os_key.title())

    await callback.message.edit_text(
        f"📂 <b>Приложения для {os_title}</b>\n\n"
        f"Выберите клиент для скачивания (рекомендуем верхний):",
        parse_mode="HTML",
        reply_markup=apps_links_kb(apps)
    )
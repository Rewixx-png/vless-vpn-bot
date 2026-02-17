from aiogram import Router, F
from aiogram.types import CallbackQuery
from aiogram.fsm.context import FSMContext
from keyboards.user import apps_os_kb, apps_links_kb, apps_cores_kb
from handlers.user.start import edit_or_answer

router = Router()

APPS_DB = {
    "android": {
        "singbox": [
            {"name": "⚡ HAPP (Recommended)", "url": "https://github.com/Happ-Proxy/HAPP/releases"},
            {"name": "🐈 NekoBox", "url": "https://github.com/MatsuriDayo/NekoBoxForAndroid/releases"},
            {"name": "🌊 V2RayTun", "url": "https://github.com/V2rayTun/V2rayTun/releases"},
            {"name": "🔥 Hiddify", "url": "https://play.google.com/store/apps/details?id=app.hiddify.com"},
        ],
        "xray": [
            {"name": "🤖 v2rayNG", "url": "https://play.google.com/store/apps/details?id=com.v2ray.ang"}
        ],
        "clash": [
            {"name": "🚀 FlClash (Top)", "url": "https://github.com/chen08209/FlClash/releases"},
            {"name": "⚙️ Clash Meta", "url": "https://github.com/MetaCubeX/ClashMetaForAndroid/releases"},
        ]
    },
    "ios": {
        "singbox": [
            {"name": "🔥 Hiddify", "url": "https://apps.apple.com/us/app/hiddify-proxy-vpn/id6596588138"},
            {"name": "🛠 Karing", "url": "https://apps.apple.com/us/app/karing/id6472431552"},
        ],
        "xray": [
            {"name": "🦊 FoXray", "url": "https://apps.apple.com/us/app/foxray/id6448898396"},
            {"name": "🚀 Streisand", "url": "https://apps.apple.com/us/app/streisand/id6450534064"},
            {"name": "🍏 V2Box", "url": "https://apps.apple.com/us/app/v2box-v2ray-client/id6446814690"}
        ],
        "clash": [
            {"name": "🚀 Shadowrocket ($)", "url": "https://apps.apple.com/us/app/shadowrocket/id932747118"},
        ]
    },
    "windows": {
        "singbox": [
            {"name": "🐈 NekoRay (Best)", "url": "https://github.com/MatsuriDayo/nekoray/releases"},
            {"name": "🔥 Hiddify", "url": "https://github.com/hiddify/hiddify-next/releases"},
        ],
        "xray": [
            {"name": "💻 v2rayN", "url": "https://github.com/2dust/v2rayN/releases"}
        ],
        "clash": [
            {"name": "🚀 FlClash", "url": "https://github.com/chen08209/FlClash/releases"},
            {"name": "⚡ Clash Verge", "url": "https://github.com/clash-verge-rev/clash-verge-rev/releases"},
        ]
    },
    "macos": {
        "singbox": [
            {"name": "🔥 Hiddify", "url": "https://apps.apple.com/us/app/hiddify-proxy-vpn/id6596588138"},
        ],
        "xray": [
            {"name": "🦊 FoXray", "url": "https://apps.apple.com/us/app/foxray/id6448898396"},
        ],
        "clash": [
            {"name": "🚀 FlClash", "url": "https://github.com/chen08209/FlClash/releases"},
        ]
    },
    "linux": {
        "singbox": [
            {"name": "🐈 NekoRay", "url": "https://github.com/MatsuriDayo/nekoray/releases"},
        ],
        "xray": [
             {"name": "💻 v2rayA", "url": "https://github.com/v2rayA/v2rayA/releases"}
        ],
        "clash": [
            {"name": "🚀 FlClash", "url": "https://github.com/chen08209/FlClash/releases"},
        ]
    }
}

OS_NAMES = {
    "android": "Android 🤖",
    "ios": "iOS 🍏",
    "windows": "Windows 💻",
    "macos": "macOS 🍎",
    "linux": "Linux 🐧"
}

@router.callback_query(F.data == "apps_menu")
async def show_apps_os_selection(callback: CallbackQuery, state: FSMContext):
    text = (
        "<b>📱 APP CATALOG | ПРИЛОЖЕНИЯ</b>\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        "Мы собрали лучшие VPN-клиенты для всех платформ.\n"
        "Пожалуйста, выберите ваше устройство:"
    )
    await edit_or_answer(callback.message, text, apps_os_kb(), state, media_url="video")

@router.callback_query(F.data.startswith("apps_os_"))
async def show_cores_list(callback: CallbackQuery, state: FSMContext):
    os_key = callback.data.split("apps_os_")[1]
    os_title = OS_NAMES.get(os_key, os_key.title())
    
    text = (
        f"<b>📂 {os_title} | ВЫБОР ЯДРА</b>\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        "Для этой системы доступны разные типы клиентов:\n\n"
        "📦 <b>Sing-Box:</b> Современные, быстрые, красивые.\n"
        "☢️ <b>Xray:</b> Классические, стабильные клиенты.\n"
        "🐝 <b>Clash:</b> Продвинутая маршрутизация (TUN).\n\n"
        "<i>Выберите категорию:</i>"
    )
    
    await edit_or_answer(callback.message, text, apps_cores_kb(os_key), state, media_url="video")

@router.callback_query(F.data.startswith("apps_c_"))
async def show_final_apps(callback: CallbackQuery, state: FSMContext):
    try:
        parts = callback.data.split("_")
        os_key = parts[2]
        core_key = parts[3]
    except ValueError:
        return

    apps_list = APPS_DB.get(os_key, {}).get(core_key, [])
    os_title = OS_NAMES.get(os_key, os_key)

    text = (
        f"<b>⬇️ DOWNLOAD | СКАЧАТЬ</b>\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"💻 <b>ОС:</b> {os_title}\n"
        f"⚙️ <b>Тип:</b> {core_key.upper()}\n\n"
        "Нажмите кнопку ниже для перехода к скачиванию:"
    )

    await edit_or_answer(callback.message, text, apps_links_kb(apps_list, os_key), state, media_url="video")
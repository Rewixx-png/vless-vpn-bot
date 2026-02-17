from aiogram import Router, F
from aiogram.types import CallbackQuery
from aiogram.fsm.context import FSMContext
from keyboards.user import apps_os_kb, apps_links_kb, apps_cores_kb
from handlers.user.start import edit_or_answer

router = Router()

APPS_DB = {
    "android": {
        "singbox": [
            {"name": "⚡ HAPP (Топ новинка)", "url": "https://github.com/Happ-Proxy/HAPP/releases"},
            {"name": "🐈 NekoBox (Мощный)", "url": "https://github.com/MatsuriDayo/NekoBoxForAndroid/releases"},
            {"name": "🌊 V2RayTun (Простой)", "url": "https://github.com/V2rayTun/V2rayTun/releases"},
            {"name": "🔥 Hiddify (Красивый)", "url": "https://play.google.com/store/apps/details?id=app.hiddify.com"},
            {"name": "📦 Sing-Box Official", "url": "https://play.google.com/store/apps/details?id=io.nekohasekai.sfa"},
            {"name": "🛠 Karing (Комбайн)", "url": "https://github.com/KaringX/karing/releases"}
        ],
        "xray": [
            {"name": "🤖 v2rayNG (Классика)", "url": "https://play.google.com/store/apps/details?id=com.v2ray.ang"}
        ],
        "clash": [
            {"name": "🚀 FlClash (Советуем)", "url": "https://github.com/chen08209/FlClash/releases"},
            {"name": "⚙️ Clash Meta", "url": "https://github.com/MetaCubeX/ClashMetaForAndroid/releases"},
            {"name": "🏄‍♂️ Surfboard", "url": "https://play.google.com/store/apps/details?id=com.getsurfboard"}
        ]
    },
    "ios": {
        "singbox": [
            {"name": "🔥 Hiddify (Топ)", "url": "https://apps.apple.com/us/app/hiddify-proxy-vpn/id6596588138"},
            {"name": "🛠 Karing (Новинка)", "url": "https://apps.apple.com/us/app/karing/id6472431552"},
            {"name": "📦 Sing-Box", "url": "https://apps.apple.com/us/app/sing-box/id6451272673"}
        ],
        "xray": [
            {"name": "🦊 FoXray (Рекомендуем)", "url": "https://apps.apple.com/us/app/foxray/id6448898396"},
            {"name": "🚀 Streisand", "url": "https://apps.apple.com/us/app/streisand/id6450534064"},
            {"name": "🍏 V2Box", "url": "https://apps.apple.com/us/app/v2box-v2ray-client/id6446814690"}
        ],
        "clash": [
            {"name": "🚀 Shadowrocket ($2.99)", "url": "https://apps.apple.com/us/app/shadowrocket/id932747118"},
            {"name": "📈 Stash ($3.99)", "url": "https://apps.apple.com/us/app/stash-rule-based-proxy/id1596063349"}
        ]
    },
    "windows": {
        "singbox": [
            {"name": "🐈 NekoRay (Топ выбор)", "url": "https://github.com/MatsuriDayo/nekoray/releases"},
            {"name": "🔥 Hiddify (Красивый)", "url": "https://github.com/hiddify/hiddify-next/releases"},
            {"name": "🛠 Karing (Новый)", "url": "https://karing.app/download"}
        ],
        "xray": [
            {"name": "💻 v2rayN (Классика)", "url": "https://github.com/2dust/v2rayN/releases"}
        ],
        "clash": [
            {"name": "🚀 FlClash (Быстрый)", "url": "https://github.com/chen08209/FlClash/releases"},
            {"name": "⚡ Clash Verge Rev", "url": "https://github.com/clash-verge-rev/clash-verge-rev/releases"},
            {"name": "🐱 Clash Nyanpasu", "url": "https://github.com/keiko233/clash-nyanpasu/releases"}
        ]
    },
    "macos": {
        "singbox": [
            {"name": "🔥 Hiddify (AppStore)", "url": "https://apps.apple.com/us/app/hiddify-proxy-vpn/id6596588138"},
            {"name": "🛠 Karing (Новинка)", "url": "https://apps.apple.com/us/app/karing/id6472431552"}
        ],
        "xray": [
            {"name": "🦊 FoXray (Лучший)", "url": "https://apps.apple.com/us/app/foxray/id6448898396"},
            {"name": "🍏 V2Box", "url": "https://apps.apple.com/us/app/v2box-v2ray-client/id6446814690"}
        ],
        "clash": [
            {"name": "🚀 FlClash", "url": "https://github.com/chen08209/FlClash/releases"},
            {"name": "⚡ Clash Verge Rev", "url": "https://github.com/clash-verge-rev/clash-verge-rev/releases"},
            {"name": "🐱 Clash Nyanpasu", "url": "https://github.com/keiko233/clash-nyanpasu/releases"}
        ]
    },
    "linux": {
        "singbox": [
            {"name": "🐈 NekoRay", "url": "https://github.com/MatsuriDayo/nekoray/releases"},
            {"name": "🔥 Hiddify", "url": "https://github.com/hiddify/hiddify-next/releases"},
            {"name": "🛠 Karing", "url": "https://karing.app/download"}
        ],
        "xray": [
             {"name": "💻 v2rayA (WebUI)", "url": "https://github.com/v2rayA/v2rayA/releases"}
        ],
        "clash": [
            {"name": "🚀 FlClash", "url": "https://github.com/chen08209/FlClash/releases"},
            {"name": "⚡ Clash Verge Rev", "url": "https://github.com/clash-verge-rev/clash-verge-rev/releases"}
        ]
    }
}

OS_NAMES = {
    "android": "Android 🤖",
    "ios": "iOS (iPhone/iPad) 🍏",
    "windows": "Windows 💻",
    "macos": "macOS 🍎",
    "linux": "Linux 🐧"
}

CORE_NAMES = {
    "singbox": "📦 Sing-Box / Universal",
    "xray": "☢️ Xray (V2Ray) Standard",
    "clash": "🐝 Clash / Meta / TUN"
}

CORE_DESCRIPTIONS = {
    "singbox": "Современные ядра. Поддерживают Reality, Hy2, VLESS. Высокая производительность.",
    "xray": "Классическое ядро Project X. Эталонная поддержка VLESS и XTLS-Reality.",
    "clash": "Продвинутая маршрутизация (Rule-based). Режим TUN, поддержка YAML-профилей."
}

@router.callback_query(F.data == "apps_menu")
async def show_apps_os_selection(callback: CallbackQuery, state: FSMContext):
    await edit_or_answer(
        callback.message,
        "📱 <b>Каталог приложений V2.0</b>\n\n"
        "Мы собрали лучшие клиенты для всех платформ.\n"
        "Выберите вашу операционную систему:",
        apps_os_kb(),
        state,
        media_url="video"
    )

@router.callback_query(F.data.startswith("apps_os_"))
async def show_cores_list(callback: CallbackQuery, state: FSMContext):
    os_key = callback.data.split("apps_os_")[1]
    
    if os_key not in APPS_DB:
        await callback.answer("Раздел в разработке", show_alert=True)
        return

    os_title = OS_NAMES.get(os_key, os_key.title())
    
    await edit_or_answer(
        callback.message,
        f"📂 <b>{os_title}: Выбор ядра</b>\n\n"
        "Для этой системы доступны клиенты на разных ядрах:\n\n"
        "📦 <b>Sing-Box:</b> Модно, стильно, быстро (HAPP, Neko, Hiddify).\n"
        "☢️ <b>Xray:</b> Надежная классика (v2rayNG, v2rayN).\n"
        "🐝 <b>Clash:</b> Гибкая настройка правил (FlClash, Meta).",
        apps_cores_kb(os_key),
        state,
        media_url="video"
    )

@router.callback_query(F.data.startswith("apps_c_"))
async def show_final_apps(callback: CallbackQuery, state: FSMContext):
    # format: apps_c_{os}_{core}
    try:
        parts = callback.data.split("_")
        if len(parts) != 4: raise ValueError
        os_key = parts[2]
        core_key = parts[3]
    except ValueError:
        await callback.answer("Ошибка данных", show_alert=True)
        return

    apps_list = APPS_DB.get(os_key, {}).get(core_key, [])
    
    if not apps_list:
        await callback.answer("Нет приложений в этой категории", show_alert=True)
        return

    os_title = OS_NAMES.get(os_key, os_key)
    core_title = CORE_NAMES.get(core_key, core_key)
    desc = CORE_DESCRIPTIONS.get(core_key, "")

    await edit_or_answer(
        callback.message,
        f"⬇️ <b>Скачивание клиентов</b>\n"
        f"💻 ОС: {os_title}\n"
        f"⚙️ Ядро: {core_title}\n\n"
        f"<i>{desc}</i>\n\n"
        "👇 Нажмите кнопку для перехода к скачиванию:",
        apps_links_kb(apps_list, os_key),
        state,
        media_url="video"
    )
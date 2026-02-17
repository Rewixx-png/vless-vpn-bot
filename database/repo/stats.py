from sqlalchemy import select, func, distinct
from database.core import async_session_factory
from database.models import User, Subscription, BlacklistedItem
import math
import logging

class StatsRepo:
    # Mapping for normalizing legacy full names to 2-letter codes
    COUNTRY_MAP = {
        "germany": "De", "deutschland": "De", "de": "De",
        "netherlands": "Nl", "the netherlands": "Nl", "nl": "Nl",
        "united states": "Us", "usa": "Us", "us": "Us", "america": "Us",
        "united kingdom": "Gb", "uk": "Gb", "great britain": "Gb", "gb": "Gb",
        "russia": "Ru", "russian federation": "Ru", "ru": "Ru",
        "finland": "Fi", "fi": "Fi",
        "france": "Fr", "fr": "Fr",
        "turkey": "Tr", "türkiye": "Tr", "tr": "Tr",
        "poland": "Pl", "pl": "Pl",
        "ukraine": "Ua", "ua": "Ua",
        "kazakhstan": "Kz", "kz": "Kz",
        "sweden": "Se", "se": "Se",
        "switzerland": "Ch", "ch": "Ch",
        "italy": "It", "it": "It",
        "spain": "Es", "es": "Es",
        "austria": "At", "at": "At",
        "canada": "Ca", "ca": "Ca",
        "japan": "Jp", "jp": "Jp",
        "singapore": "Sg", "sg": "Sg",
        "united arab emirates": "Ae", "uae": "Ae", "ae": "Ae",
        "hungary": "Hu", "hu": "Hu",
        "latvia": "Lv", "lv": "Lv",
        "estonia": "Ee", "ee": "Ee",
        "lithuania": "Lt", "lt": "Lt",
        "moldova": "Md", "md": "Md", "republic of moldova": "Md",
        "romania": "Ro", "ro": "Ro",
        "bulgaria": "Bg", "bg": "Bg",
        "czechia": "Cz", "czech republic": "Cz", "cz": "Cz",
        "slovakia": "Sk", "sk": "Sk",
        "norway": "No", "no": "No",
        "denmark": "Dk", "dk": "Dk",
        "ireland": "Ie", "ie": "Ie",
        "belgium": "Be", "be": "Be",
        "luxembourg": "Lu", "lu": "Lu",
        "portugal": "Pt", "pt": "Pt",
        "greece": "Gr", "gr": "Gr",
        "cyprus": "Cy", "cy": "Cy",
        "malta": "Mt", "mt": "Mt",
        "iceland": "Is", "is": "Is",
        "australia": "Au", "au": "Au",
        "new zealand": "Nz", "nz": "Nz",
        "south korea": "Kr", "korea": "Kr", "kr": "Kr",
        "china": "Cn", "cn": "Cn",
        "hong kong": "Hk", "hk": "Hk",
        "taiwan": "Tw", "tw": "Tw",
        "india": "In", "in": "In",
        "indonesia": "Id", "id": "Id",
        "malaysia": "My", "my": "My",
        "thailand": "Th", "th": "Th",
        "vietnam": "Vn", "vn": "Vn",
        "philippines": "Ph", "ph": "Ph",
        "israel": "Il", "il": "Il",
        "saudi arabia": "Sa", "sa": "Sa",
        "south africa": "Za", "za": "Za",
        "brazil": "Br", "br": "Br",
        "argentina": "Ar", "ar": "Ar",
        "mexico": "Mx", "mx": "Mx",
        "chile": "Cl", "cl": "Cl",
        "colombia": "Co", "co": "Co",
        "armenia": "Am", "am": "Am",
        "georgia": "Ge", "ge": "Ge",
        "azerbaijan": "Az", "az": "Az",
        "belarus": "By", "by": "By",
        "uzbekistan": "Uz", "uz": "Uz",
        "kyrgyzstan": "Kg", "kg": "Kg",
        "serbia": "Rs", "rs": "Rs",
        "croatia": "Hr", "hr": "Hr",
        "bosnia": "Ba", "ba": "Ba", "bosnia and herzegovina": "Ba",
        "slovenia": "Si", "si": "Si",
        "montenegro": "Me", "me": "Me",
        "macedonia": "Mk", "mk": "Mk", "north macedonia": "Mk",
        "albania": "Al", "al": "Al",
        "unk": "Unk", "unknown": "Unk"
    }

    @staticmethod
    async def get_full_stats():
        """Полная статистика для Админа (включая юзеров и ЧС)"""
        async with async_session_factory() as session:
            users_count = await session.scalar(select(func.count(User.id)))
            subs_count = await session.scalar(select(func.count(Subscription.id)))
            active_subs = await session.scalar(select(func.count(Subscription.id)).where(Subscription.is_active == True))
            blacklist_count = await session.scalar(select(func.count(BlacklistedItem.id)))

            regions_stat = await StatsRepo._get_formatted_regions(session)

            return {
                "users": users_count or 0,
                "total_subs": subs_count or 0,
                "active_subs": active_subs or 0,
                "blacklist": blacklist_count or 0,
                "regions": regions_stat
            }

    @staticmethod
    async def get_all_users_detailed():
        """Get list of all users for export"""
        async with async_session_factory() as session:
            stmt = select(User).order_by(User.id)
            result = await session.execute(stmt)
            return result.scalars().all()

    @staticmethod
    async def get_network_stats():
        """Публичная статистика для Юзеров"""
        async with async_session_factory() as session:
            active_subs = await session.scalar(select(func.count(Subscription.id)).where(Subscription.is_active == True))
            regions_count = await session.scalar(select(func.count(distinct(Subscription.region))).where(Subscription.is_active == True))
            
            regions_stat = await StatsRepo._get_formatted_regions(session)

            return {
                "active": active_subs or 0,
                "regions_count": regions_count or 0,
                "regions_list": regions_stat
            }

    @staticmethod
    async def get_public_stats():
        """Краткая статистика для главного меню"""
        async with async_session_factory() as session:
            active_subs = await session.scalar(select(func.count(Subscription.id)).where(Subscription.is_active == True))
            regions_count = await session.scalar(select(func.count(distinct(Subscription.region))).where(Subscription.is_active == True))
            return {
                "active": active_subs or 0,
                "regions": regions_count or 0
            }

    @staticmethod
    async def _get_formatted_regions(session):
        """Вспомогательный метод для форматирования списка стран в 2 колонки"""
        regions_data = await session.execute(
            select(Subscription.region, func.count(Subscription.id))
            .where(Subscription.is_active == True)
            .group_by(Subscription.region)
        )
        
        aggregated = {}
        
        for region_raw, count in regions_data.all():
            if not region_raw:
                continue
                
            parts = region_raw.split(" ", 1)
            if len(parts) == 2:
                flag, name = parts
            else:
                flag, name = "🌍", parts[0]
            
            name_clean = name.lower().strip()
            short_code = StatsRepo.COUNTRY_MAP.get(name_clean)
            
            if short_code:
                final_name = f"{flag} {short_code}"
            else:
                # Fallback logic for unmapped countries
                if len(name) == 2:
                     final_name = f"{flag} {name.title()}"
                elif len(name) > 15:
                    # If very long and not in map, try to take first 2 chars
                    # This is risky but better than breaking layout
                    final_name = f"{flag} {name[:2].title()}"
                else:
                     final_name = f"{flag} {name.title()}"
            
            if final_name in aggregated:
                aggregated[final_name] += count
            else:
                aggregated[final_name] = count
        
        sorted_regions = sorted(aggregated.items(), key=lambda x: x[1], reverse=True)
        
        rows = [f"{r}: {c}" for r, c in sorted_regions]
        
        if not rows:
            return "Нет данных"

        total_rows = len(rows)
        mid_index = math.ceil(total_rows / 2)
        
        col1 = rows[:mid_index]
        col2 = rows[mid_index:]

        # Minimal padding
        max_width = max(len(s) for s in col1) + 2 if col1 else 0

        lines = []
        for i in range(len(col1)):
            left = col1[i].ljust(max_width)
            right = col2[i] if i < len(col2) else ""
            
            if right:
                lines.append(f"{left}{right}")
            else:
                lines.append(left)

        return "\n".join(lines)
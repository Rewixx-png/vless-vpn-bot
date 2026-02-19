import os
import re
import aiohttp
import asyncio
import logging
import socket
import geoip2.database
from typing import Optional, List

logger = logging.getLogger("GeoIP")

class GeoIP:
    MMDB_URL = "https://github.com/P3TERX/GeoLite.mmdb/raw/download/GeoLite2-Country.mmdb"
    DB_PATH = "utils/checker/mmdb/Country.mmdb"
    
    _reader: Optional[geoip2.database.Reader] = None
    _cache = {}
    _dns_cache = {}
    
    PROVIDERS = [
        {
            "name": "ip-api.com",
            "url": "http://ip-api.com/json/{ip}",
            "key": "countryCode",
            "headers": {}
        },
        {
            "name": "ipwho.is",
            "url": "http://ipwho.is/{ip}",
            "key": "country_code",
            "headers": {"User-Agent": "Mozilla/5.0"}
        },
        {
            "name": "api.ip.sb",
            "url": "https://api.ip.sb/geoip/{ip}",
            "key": "country_code",
            "headers": {"User-Agent": "Mozilla/5.0"}
        },
        {
            "name": "ipapi.co",
            "url": "https://ipapi.co/{ip}/json/",
            "key": "country_code",
            "headers": {"User-Agent": "Mozilla/5.0"}
        },
        {
            "name": "ipinfo.io",
            "url": "https://ipinfo.io/{ip}/json",
            "key": "country",
            "headers": {}
        },
        {
            "name": "freeipapi.com",
            "url": "https://freeipapi.com/api/json/{ip}",
            "key": "countryCode",
            "headers": {}
        }
    ]

    FLAGS = {
        'AD': '🇦🇩', 'AE': '🇦🇪', 'AF': '🇦🇫', 'AG': '🇦🇬', 'AI': '🇦🇮', 'AL': '🇦🇱', 'AM': '🇦🇲', 'AO': '🇦🇴',
        'AQ': '🇦🇶', 'AR': '🇦🇷', 'AS': '🇦🇸', 'AT': '🇦🇹', 'AU': '🇦🇺', 'AW': '🇦🇼', 'AX': '🇦🇽', 'AZ': '🇦🇿',
        'BA': '🇧🇦', 'BB': '🇧🇧', 'BD': '🇧🇩', 'BE': '🇧🇪', 'BF': '🇧🇫', 'BG': '🇧🇬', 'BH': '🇧🇭', 'BI': '🇧🇮',
        'BJ': '🇧🇯', 'BL': '🇧🇱', 'BM': '🇧🇲', 'BN': '🇧🇳', 'BO': '🇧🇴', 'BQ': '🇧🇶', 'BR': '🇧🇷', 'BS': '🇧🇸',
        'BT': '🇧🇹', 'BV': '🇧🇻', 'BW': '🇧🇼', 'BY': '🇧🇾', 'BZ': '🇧🇿', 'CA': '🇨🇦', 'CC': '🇨🇨', 'CD': '🇨🇩',
        'CF': '🇨🇫', 'CG': '🇨🇬', 'CH': '🇨🇭', 'CI': '🇨🇮', 'CK': '🇨🇰', 'CL': '🇨🇱', 'CM': '🇨🇲', 'CN': '🇨🇳',
        'CO': '🇨🇴', 'CR': '🇨🇷', 'CU': '🇨🇺', 'CV': '🇨🇻', 'CW': '🇨🇼', 'CX': '🇨🇽', 'CY': '🇨🇾', 'CZ': '🇨🇿',
        'DE': '🇩🇪', 'DJ': '🇩🇯', 'DK': '🇩🇰', 'DM': '🇩🇲', 'DO': '🇩🇴', 'DZ': '🇩🇿', 'EC': '🇪🇨', 'EE': '🇪🇪',
        'EG': '🇪🇬', 'EH': '🇪🇭', 'ER': '🇪🇷', 'ES': '🇪🇸', 'ET': '🇪🇹', 'EU': '🇪🇺', 'FI': '🇫🇮', 'FJ': '🇫🇯',
        'FK': '🇫🇰', 'FM': '🇫🇲', 'FO': '🇫🇴', 'FR': '🇫🇷', 'GA': '🇬🇦', 'GB': '🇬🇧', 'GD': '🇬🇩', 'GE': '🇬🇪',
        'GF': '🇬🇫', 'GG': '🇬🇬', 'GH': '🇬🇭', 'GI': '🇬🇮', 'GL': '🇬🇱', 'GM': '🇬🇲', 'GN': '🇬🇳', 'GP': '🇬🇵',
        'GQ': '🇬🇶', 'GR': '🇬🇷', 'GS': '🇬🇸', 'GT': '🇬🇹', 'GU': '🇬🇺', 'GW': '🇬🇼', 'GY': '🇬🇾', 'HK': '🇭🇰',
        'HM': '🇭🇲', 'HN': '🇭🇳', 'HR': '🇭🇷', 'HT': '🇭🇹', 'HU': '🇭🇺', 'ID': '🇮🇩', 'IE': '🇮🇪', 'IL': '🇮🇱',
        'IM': '🇮🇲', 'IN': '🇮🇳', 'IO': '🇮🇴', 'IQ': '🇮🇶', 'IR': '🇮🇷', 'IS': '🇮🇸', 'IT': '🇮🇹', 'JE': '🇯🇪',
        'JM': '🇯🇲', 'JO': '🇯🇴', 'JP': '🇯🇵', 'KE': '🇰🇪', 'KG': '🇰🇬', 'KH': '🇰🇭', 'KI': '🇰🇮', 'KM': '🇰🇲',
        'KN': '🇰🇳', 'KP': '🇰🇵', 'KR': '🇰🇷', 'KW': '🇰🇼', 'KY': '🇰🇾', 'KZ': '🇰🇿', 'LA': '🇱🇦', 'LB': '🇱🇧',
        'LC': '🇱🇨', 'LI': '🇱🇮', 'LK': '🇱🇰', 'LR': '🇱🇷', 'LS': '🇱🇸', 'LT': '🇱🇹', 'LU': '🇱🇺', 'LV': '🇱🇻',
        'LY': '🇱🇾', 'MA': '🇲🇦', 'MC': '🇲🇨', 'MD': '🇲🇩', 'ME': '🇲🇪', 'MF': '🇲🇫', 'MG': '🇲🇬', 'MH': '🇲🇭',
        'MK': '🇲🇰', 'ML': '🇲🇱', 'MM': '🇲🇲', 'MN': '🇲🇳', 'MO': '🇲🇴', 'MP': '🇲🇵', 'MQ': '🇲🇶', 'MR': '🇲🇷',
        'MS': '🇲🇸', 'MT': '🇲🇹', 'MU': '🇲🇺', 'MV': '🇲🇻', 'MW': '🇲🇼', 'MX': '🇲🇽', 'MY': '🇲🇾', 'MZ': '🇲🇿',
        'NA': '🇳🇦', 'NC': '🇳🇨', 'NE': '🇳🇪', 'NF': '🇳🇫', 'NG': '🇳🇬', 'NI': '🇳🇮', 'NL': '🇳🇱', 'NO': '🇳🇴',
        'NP': '🇳🇵', 'NR': '🇳🇷', 'NU': '🇳🇺', 'NZ': '🇳🇿', 'OM': '🇴🇲', 'PA': '🇵🇦', 'PE': '🇵🇪', 'PF': '🇵🇫',
        'PG': '🇵🇬', 'PH': '🇵🇭', 'PK': '🇵🇰', 'PL': '🇵🇱', 'PM': '🇵🇲', 'PN': '🇵🇳', 'PR': '🇵🇷', 'PS': '🇵🇸',
        'PT': '🇵🇹', 'PW': '🇵🇼', 'PY': '🇵🇾', 'QA': '🇶🇦', 'RE': '🇷🇪', 'RO': '🇷🇴', 'RS': '🇷🇸', 'RU': '🇷🇺',
        'RW': '🇷🇼', 'SA': '🇸🇦', 'SB': '🇸🇧', 'SC': '🇸🇨', 'SD': '🇸🇩', 'SE': '🇸🇪', 'SG': '🇸🇬', 'SH': '🇸🇭',
        'SI': '🇸🇮', 'SJ': '🇸🇯', 'SK': '🇸🇰', 'SL': '🇸🇱', 'SM': '🇸🇲', 'SN': '🇸🇳', 'SO': '🇸🇴', 'SR': '🇸🇷',
        'SS': '🇸🇸', 'ST': '🇸🇹', 'SV': '🇸🇻', 'SX': '🇸🇽', 'SY': '🇸🇾', 'SZ': '🇸🇿', 'TC': '🇹🇨', 'TD': '🇹🇩',
        'TF': '🇹🇫', 'TG': '🇹🇬', 'TH': '🇹🇭', 'TJ': '🇹🇯', 'TK': '🇹🇰', 'TL': '🇹🇱', 'TM': '🇹🇲', 'TN': '🇹🇳',
        'TO': '🇹🇴', 'TR': '🇹🇷', 'TT': '🇹🇹', 'TV': '🇹🇻', 'TW': '🇹🇼', 'TZ': '🇹🇿', 'UA': '🇺🇦', 'UG': '🇺🇬',
        'UM': '🇺🇲', 'US': '🇺🇸', 'UY': '🇺🇾', 'UZ': '🇺🇿', 'VA': '🇻🇦', 'VC': '🇻🇨', 'VE': '🇻🇪', 'VG': '🇻🇬',
        'VI': '🇻🇮', 'VN': '🇻🇳', 'VU': '🇻🇺', 'WF': '🇼🇫', 'WS': '🇼🇸', 'XK': '🇽🇰', 'YE': '🇾🇪', 'YT': '🇾🇹',
        'ZA': '🇿🇦', 'ZM': '🇿🇲', 'ZW': '🇿🇼'
    }

    TLD_MAP = {
        ".ru": "🇷🇺 Russia", ".rf": "🇷🇺 Russia", ".su": "🇷🇺 Russia",
        ".de": "🇩🇪 Germany", ".nl": "🇳🇱 Netherlands", ".fi": "🇫🇮 Finland",
        ".fr": "🇫🇷 France", ".uk": "🇬🇧 United Kingdom", ".gb": "🇬🇧 United Kingdom",
        ".us": "🇺🇸 United States", ".gov": "🇺🇸 United States", ".edu": "🇺🇸 United States",
        ".ca": "🇨🇦 Canada", ".cn": "🇨🇳 China", ".ir": "🇮🇷 Iran",
        ".tr": "🇹🇷 Turkey", ".ua": "🇺🇦 Ukraine", ".kz": "🇰🇿 Kazakhstan",
        ".by": "🇧🇾 Belarus", ".pl": "🇵🇱 Poland", ".it": "🇮🇹 Italy",
        ".es": "🇪🇸 Spain", ".jp": "🇯🇵 Japan", ".kr": "🇰🇷 South Korea",
        ".in": "🇮🇳 India", ".br": "🇧🇷 Brazil", ".se": "🇸🇪 Sweden",
        ".ch": "🇨🇭 Switzerland", ".no": "🇳🇴 Norway", ".ae": "🇦🇪 UAE",
        ".sg": "🇸🇬 Singapore", ".hk": "🇭🇰 Hong Kong", ".au": "🇦🇺 Australia"
    }

    # Маппинг IATA кодов аэропортов в страны
    IATA_MAP = {
        # Europe
        "fra": "🇩🇪 Germany", "muc": "🇩🇪 Germany", "ber": "🇩🇪 Germany", "dus": "🇩🇪 Germany",
        "ams": "🇳🇱 Netherlands", "rtm": "🇳🇱 Netherlands",
        "lon": "🇬🇧 United Kingdom", "lhr": "🇬🇧 United Kingdom", "lgw": "🇬🇧 United Kingdom", "man": "🇬🇧 United Kingdom",
        "par": "🇫🇷 France", "cdg": "🇫🇷 France", "ory": "🇫🇷 France", "mrs": "🇫🇷 France",
        "hel": "🇫🇮 Finland",
        "sto": "🇸🇪 Sweden", "arn": "🇸🇪 Sweden",
        "osl": "🇳🇴 Norway",
        "waw": "🇵🇱 Poland",
        "mad": "🇪🇸 Spain", "bcn": "🇪🇸 Spain",
        "rom": "🇮🇹 Italy", "fco": "🇮🇹 Italy", "mxp": "🇮🇹 Italy",
        "zrh": "🇨🇭 Switzerland", "gva": "🇨🇭 Switzerland",
        "vie": "🇦🇹 Austria",
        
        # Asia
        "sgp": "🇸🇬 Singapore", "sin": "🇸🇬 Singapore",
        "tyo": "🇯🇵 Japan", "hnd": "🇯🇵 Japan", "nrt": "🇯🇵 Japan", "osa": "🇯🇵 Japan",
        "sel": "🇰🇷 South Korea", "icn": "🇰🇷 South Korea",
        "hkg": "🇭🇰 Hong Kong",
        "tpe": "🇹🇼 Taiwan",
        "dxb": "🇦🇪 UAE",
        
        # Americas
        "nyc": "🇺🇸 United States", "jfk": "🇺🇸 United States", "ewr": "🇺🇸 United States",
        "lax": "🇺🇸 United States", "sfo": "🇺🇸 United States", "sjc": "🇺🇸 United States",
        "chi": "🇺🇸 United States", "ord": "🇺🇸 United States",
        "mia": "🇺🇸 United States", "dal": "🇺🇸 United States", "sea": "🇺🇸 United States",
        "tor": "🇨🇦 Canada", "yyz": "🇨🇦 Canada", "yul": "🇨🇦 Canada", "yvr": "🇨🇦 Canada",
        "sao": "🇧🇷 Brazil", "gru": "🇧🇷 Brazil",
        
        # Other
        "syd": "🇦🇺 Australia", "mel": "🇦🇺 Australia",
        "jnb": "🇿🇦 South Africa"
    }

    # Ключевые слова в названиях
    NAME_KEYWORDS = {
        "germany": "🇩🇪 Germany", "deutschland": "🇩🇪 Germany", "german": "🇩🇪 Germany",
        "usa": "🇺🇸 United States", "united states": "🇺🇸 United States", "america": "🇺🇸 United States",
        "russia": "🇷🇺 Russia", "russian": "🇷🇺 Russia", "moscow": "🇷🇺 Russia",
        "netherlands": "🇳🇱 Netherlands", "holland": "🇳🇱 Netherlands", "amsterdam": "🇳🇱 Netherlands",
        "finland": "🇫🇮 Finland", "helsinki": "🇫🇮 Finland",
        "uk": "🇬🇧 United Kingdom", "britain": "🇬🇧 United Kingdom", "london": "🇬🇧 United Kingdom",
        "france": "🇫🇷 France", "paris": "🇫🇷 France",
        "turkey": "🇹🇷 Turkey", "istanbul": "🇹🇷 Turkey",
        "iran": "🇮🇷 Iran", "tehran": "🇮🇷 Iran",
        "poland": "🇵🇱 Poland", "warsaw": "🇵🇱 Poland",
        "ukraine": "🇺🇦 Ukraine", "kiev": "🇺🇦 Ukraine", "kyiv": "🇺🇦 Ukraine",
        "kazakhstan": "🇰🇿 Kazakhstan",
        "canada": "🇨🇦 Canada",
        "china": "🇨🇳 China",
        "japan": "🇯🇵 Japan", "tokyo": "🇯🇵 Japan",
        "korea": "🇰🇷 South Korea", "seoul": "🇰🇷 South Korea",
        "sweden": "🇸🇪 Sweden",
        "switzerland": "🇨🇭 Switzerland",
        "singapore": "🇸🇬 Singapore",
        "uae": "🇦🇪 UAE", "dubai": "🇦🇪 UAE"
    }

    @classmethod
    async def initialize(cls):
        if not os.path.exists(os.path.dirname(cls.DB_PATH)):
            os.makedirs(os.path.dirname(cls.DB_PATH))
            
        if not os.path.exists(cls.DB_PATH):
            logger.warning("📥 Downloading GeoIP database...")
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(cls.MMDB_URL, timeout=120) as resp:
                        if resp.status == 200:
                            with open(cls.DB_PATH, 'wb') as f:
                                while True:
                                    chunk = await resp.content.read(8192)
                                    if not chunk: break
                                    f.write(chunk)
                            logger.info("✅ GeoIP database downloaded.")
                        else:
                            logger.error(f"❌ GeoIP download failed: {resp.status}")
                            return
            except Exception as e:
                logger.error(f"❌ GeoIP download error: {e}")
                return

        try:
            cls._reader = geoip2.database.Reader(cls.DB_PATH)
            logger.info("✅ GeoIP Reader initialized.")
        except Exception as e:
            logger.error(f"❌ Failed to load GeoIP DB: {e}")

    @classmethod
    async def _resolve_host(cls, host: str) -> str | None:
        if host in cls._dns_cache:
            return cls._dns_cache[host]
        try:
            socket.inet_aton(host)
            return host
        except:
            pass
        try:
            loop = asyncio.get_running_loop()
            info = await loop.getaddrinfo(host, 80, type=socket.SOCK_STREAM)
            ip = info[0][4][0]
            cls._dns_cache[host] = ip
            return ip
        except Exception:
            return None

    @classmethod
    def _format_result(cls, code: str) -> str:
        if not code or len(code) != 2:
            return "🌍 Unk"
        flag = cls.FLAGS.get(code.upper(), "🌍")
        return f"{flag} {code.upper().title()}"

    @classmethod
    def _get_from_db(cls, ip: str) -> str | None:
        if not cls._reader:
            return None
        try:
            response = cls._reader.country(ip)
            code = response.country.iso_code
            if code:
                return cls._format_result(code)
        except Exception:
            return None
        return None

    @classmethod
    async def _fetch_from_provider(cls, session: aiohttp.ClientSession, provider: dict, ip: str) -> str | None:
        try:
            url = provider["url"].format(ip=ip)
            headers = provider.get("headers", {})
            timeout = aiohttp.ClientTimeout(total=10)
            async with session.get(url, headers=headers, timeout=timeout) as resp:
                if resp.status == 200:
                    data = await resp.json(content_type=None)
                    if provider["name"] == "ipwho.is" and not data.get("success"): return None
                    if provider["name"] == "ip-api.com" and data.get("status") == "fail": return None
                    code = data.get(provider["key"])
                    if code and len(code) == 2:
                        return cls._format_result(code)
        except Exception:
            pass
        return None
        
    @classmethod
    def _guess_by_tld(cls, host: str) -> str | None:
        host = host.lower().strip()
        for tld, region in cls.TLD_MAP.items():
            if host.endswith(tld):
                if host == tld[1:] or host.endswith(tld):
                     return region
        return None

    @classmethod
    def _guess_by_iata(cls, host: str) -> str | None:
        """Поиск IATA кодов в поддоменах (fra.server.com)"""
        parts = host.lower().split('.')
        for part in parts:
            # Ищем коды длиной 3 символа, иногда с цифрами (fra1, ams-2)
            # Простой поиск вхождения кода в часть домена
            for iata, region in cls.IATA_MAP.items():
                if iata in part:
                    # Проверка на ложные срабатывания (например 'sing' содержит 'sin')
                    # Но пока оставим простую проверку, так как это fallback
                    return region
        return None

    @classmethod
    def _guess_by_name(cls, name: str) -> str | None:
        """Поиск по названию конфига"""
        if not name: return None
        name_lower = name.lower()
        
        # 1. Поиск эмодзи флагов
        # Простой regex для флагов (regional indicators)
        flags = re.findall(r'[\U0001F1E6-\U0001F1FF]{2}', name)
        if flags:
            # Если нашли флаг, нужно понять какая это страна.
            # Обратного маппинга у нас нет, но мы можем вернуть флаг как есть + Unk?
            # Или просто вернуть "Флаг Detected"
            # Лучше поищем текстовые совпадения
            pass

        # 2. Поиск ключевых слов
        for keyword, region in cls.NAME_KEYWORDS.items():
            # Проверяем слово целиком или через разделители
            if keyword in name_lower:
                return region
        
        return None

    @classmethod
    async def identify_region(cls, session: aiohttp.ClientSession, host: str = None, remark: str = None) -> str:
        if not host: return "🌍 Unk"
        
        # 1. DNS RESOLUTION
        ip = await cls._resolve_host(host)
        
        if ip and ip not in ["127.0.0.1", "localhost", "0.0.0.0"]:
            if ip in cls._cache: return cls._cache[ip]

            # 2. Local MMDB
            if not cls._reader: await cls.initialize()
            local_result = cls._get_from_db(ip)
            if local_result:
                cls._cache[ip] = local_result
                return local_result

            # 3. Parallel Race
            tasks = []
            for provider in cls.PROVIDERS:
                tasks.append(asyncio.create_task(cls._fetch_from_provider(session, provider, ip)))
            try:
                active_tasks = set(tasks)
                while active_tasks:
                    done, pending = await asyncio.wait(active_tasks, return_when=asyncio.FIRST_COMPLETED)
                    for task in done:
                        result = task.result()
                        if result:
                            for p in pending: p.cancel()
                            cls._cache[ip] = result
                            if host != ip: cls._cache[host] = result
                            return result
                    active_tasks = pending
            except Exception:
                pass
            for t in tasks:
                if not t.done(): t.cancel()

        # --- FALLBACK HEURISTICS (Если IP подвел) ---
        
        # 4. IATA Code (Airport codes in host)
        iata_guess = cls._guess_by_iata(host)
        if iata_guess:
            cls._cache[host] = iata_guess
            if ip: cls._cache[ip] = iata_guess
            return iata_guess

        # 5. Config Name Analysis
        if remark:
            name_guess = cls._guess_by_name(remark)
            if name_guess:
                return name_guess

        # 6. TLD Guess
        tld_guess = cls._guess_by_tld(host)
        if tld_guess:
            cls._cache[host] = tld_guess
            return tld_guess

        # Final surrender
        cls._cache[host] = "🌍 Unk"
        if ip: cls._cache[ip] = "🌍 Unk"
        return "🌍 Unk"

    @classmethod
    async def get_regions_batch(cls, hosts_data: list[tuple[str, str]], session: aiohttp.ClientSession) -> dict[str, str]:
        """
        Input: list of (host, remark) tuples
        Output: dict {host: region}
        """
        if not cls._reader:
            await cls.initialize()
            
        results = {}
        
        # Map: host -> remark
        host_remark_map = {h: r for h, r in hosts_data}
        unique_hosts = set(host_remark_map.keys())
        
        resolved_map = {} 
        unresolved_hosts = []
        
        sem_dns = asyncio.Semaphore(50)
        async def resolve_worker(h):
            async with sem_dns:
                ip = await cls._resolve_host(h)
                if ip:
                    resolved_map[h] = ip
                else:
                    unresolved_hosts.append(h)

        await asyncio.gather(*[resolve_worker(h) for h in unique_hosts])

        # Process IPs
        unknown_ips = set()
        for host, ip in resolved_map.items():
            if ip in ["127.0.0.1", "localhost"]:
                results[host] = "🌍 Unk"
                continue
                
            local = cls._get_from_db(ip)
            if local:
                results[host] = local
            else:
                unknown_ips.add(ip)

        # Race for Unknown IPs
        if unknown_ips:
            sem_api = asyncio.Semaphore(5)
            ip_results = {}
            async def resolve_ip_race(target_ip):
                async with sem_api:
                    res = await cls.identify_region(session, target_ip)
                    ip_results[target_ip] = res
            await asyncio.gather(*[resolve_ip_race(ip) for ip in unknown_ips])
            
            for host, ip in resolved_map.items():
                if host not in results and ip in ip_results:
                    region = ip_results[ip]
                    if "Unk" in region:
                        # Fallback Chain
                        iata = cls._guess_by_iata(host)
                        if iata: results[host] = iata
                        else:
                            remark = host_remark_map.get(host)
                            name_g = cls._guess_by_name(remark)
                            if name_g: results[host] = name_g
                            else:
                                tld = cls._guess_by_tld(host)
                                if tld: results[host] = tld
                                else: results[host] = region
                    else:
                        results[host] = region

        # Process Unresolved (DNS Failed)
        for h in unresolved_hosts:
            # Fallback Chain
            iata = cls._guess_by_iata(h)
            if iata: results[h] = iata
            else:
                remark = host_remark_map.get(h)
                name_g = cls._guess_by_name(remark)
                if name_g: results[h] = name_g
                else:
                    tld = cls._guess_by_tld(h)
                    if tld: results[h] = tld
                    else: results[h] = "🌍 Unk"

        return results
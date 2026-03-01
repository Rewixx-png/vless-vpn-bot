import os
import aiohttp
import asyncio
import geoip2.database
import aiodns
import socket
import redis.asyncio as redis
from typing import Optional
from config import config

class GeoIP:
    MMDB_URLS =[
        "https://github.com/P3TERX/GeoLite.mmdb/raw/download/GeoLite2-Country.mmdb",
        "https://git.io/GeoLite2-Country.mmdb"
    ]
    DB_PATH = "utils/checker/mmdb/Country.mmdb"
    
    _reader: Optional[geoip2.database.Reader] = None
    _resolver: Optional[aiodns.DNSResolver] = None
    _redis: Optional[redis.Redis] = None
    
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

    @classmethod
    async def get_resolver(cls):
        if cls._resolver is None:
            cls._resolver = aiodns.DNSResolver()
        return cls._resolver

    @classmethod
    async def get_redis(cls):
        if cls._redis is None:
            try:
                cls._redis = redis.from_url(config.REDIS_URL)
            except Exception:
                pass
        return cls._redis

    @classmethod
    async def invalidate_cache(cls, host: str):
        if not host:
            return
        r = await cls.get_redis()
        if r:
            try:
                await r.delete(f"dns:{host}")
            except Exception:
                pass

    @classmethod
    async def resolve_host(cls, host: str) -> str | None:
        if not host:
            return None
            
        try:
            socket.inet_aton(host)
            return host
        except socket.error:
            pass

        r = await cls.get_redis()
        cache_key = f"dns:{host}"
        
        if r:
            try:
                cached = await r.get(cache_key)
                if cached:
                    return cached.decode('utf-8')
            except Exception:
                pass

        try:
            resolver = await cls.get_resolver()
            res = await resolver.query(host, 'A')
            ip = res[0].host
            
            if r:
                try:
                    await r.setex(cache_key, config.DNS_CACHE_TTL, ip)
                except Exception:
                    pass
                    
            return ip
        except Exception:
            return None

    @classmethod
    async def initialize(cls):
        await cls.get_redis()
        
        dir_path = os.path.dirname(cls.DB_PATH)
        if not os.path.exists(dir_path):
            os.makedirs(dir_path)

        if not os.path.exists(cls.DB_PATH):
            try:
                async with aiohttp.ClientSession() as session:
                    for url in cls.MMDB_URLS:
                        async with session.get(url, timeout=30) as resp:
                            if resp.status == 200:
                                with open(cls.DB_PATH, 'wb') as f:
                                    f.write(await resp.read())
                                break
            except: pass

        try:
            cls._reader = geoip2.database.Reader(cls.DB_PATH)
        except:
            cls._reader = None

    @classmethod
    async def update_database(cls) -> bool:
        dir_path = os.path.dirname(cls.DB_PATH)
        if not os.path.exists(dir_path):
            os.makedirs(dir_path)
            
        success = False
        try:
            async with aiohttp.ClientSession() as session:
                for url in cls.MMDB_URLS:
                    async with session.get(url, timeout=30) as resp:
                        if resp.status == 200:
                            with open(cls.DB_PATH, 'wb') as f:
                                f.write(await resp.read())
                            success = True
                            break
        except Exception:
            pass
            
        if success:
            try:
                cls._reader = geoip2.database.Reader(cls.DB_PATH)
            except:
                pass
        return success

    @classmethod
    def code_to_region(cls, code: str) -> str:
        if not code or len(code) != 2:
            return "🌍 UNK"
        
        code = code.upper()
        flag = cls.FLAGS.get(code, "🌍")
        
        names = {
            "DE": "Germany", "US": "USA", "NL": "Netherlands", "RU": "Russia",
            "FI": "Finland", "FR": "France", "GB": "UK", "UA": "Ukraine",
            "TR": "Turkey", "KZ": "Kazakhstan", "PL": "Poland", "SE": "Sweden",
            "CH": "Switzerland", "IT": "Italy", "ES": "Spain", "CA": "Canada",
            "JP": "Japan", "KR": "South Korea", "SG": "Singapore", "AE": "UAE"
        }
        
        name = names.get(code, code)
        return f"{flag} {name}"

    @classmethod
    async def identify_region(cls, session=None, host: str = None, remark: str = None) -> str:
        if remark:
            remark = remark.lower()
            if "germany" in remark or "de" in remark: return "🇩🇪 Germany"
            if "usa" in remark or "united states" in remark: return "🇺🇸 USA"
            if "russia" in remark or "ru" in remark: return "🇷🇺 Russia"
            if "nl" in remark or "netherlands" in remark: return "🇳🇱 Netherlands"

        if host:
            if host.endswith(".ru"): return "🇷🇺 Russia"
            if host.endswith(".de"): return "🇩🇪 Germany"
            if host.endswith(".uk"): return "🇬🇧 UK"
        
        return "🌍 UNK"

    @classmethod
    async def get_regions_batch(cls, hosts_data: list, session: aiohttp.ClientSession) -> dict:
        results = {}
        
        async def process_host(host, remark):
            region = await cls.identify_region(session, host, remark)
            if region != "🌍 UNK":
                return host, region
            
            ip = await cls.resolve_host(host)
            if ip and cls._reader:
                try:
                    response = cls._reader.country(ip)
                    code = response.country.iso_code
                    if code:
                        return host, cls.code_to_region(code)
                except Exception:
                    pass
            
            if ip:
                try:
                    async with session.get(f"http://ip-api.com/json/{ip}?fields=countryCode", timeout=2) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            if data.get("countryCode"):
                                return host, cls.code_to_region(data["countryCode"])
                except:
                    pass
            return host, "🌍 UNK"

        sem = asyncio.Semaphore(50)
        async def bounded_process(h, r):
            async with sem:
                return await process_host(h, r)

        tasks =[bounded_process(h, r) for h, r in hosts_data]
        res_list = await asyncio.gather(*tasks)
        for h, r in res_list:
            results[h] = r
            
        return results
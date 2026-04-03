import os
import re
import socket
import urllib.parse
import aiohttp
import asyncio
import geoip2.database
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

    COMMON_REGION_CODES = {
        "DE",
        "US",
        "NL",
        "RU",
        "FI",
        "FR",
        "GB",
        "UA",
        "TR",
        "KZ",
        "PL",
        "SE",
        "CH",
        "IT",
        "ES",
        "CA",
        "JP",
        "KR",
        "SG",
        "AE",
        "IR",
        "LT",
        "LV",
        "EE",
        "RO",
        "BG",
    }

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
        if not host or not isinstance(host, str):
            return None

        host = host.strip()
        
        if ':' in host and not host.startswith('['):
            host = host.split(':')[0]
            
        if host.startswith('[') and host.endswith(']'):
            host = host[1:-1]

        try:
            socket.inet_aton(host)
            return host
        except socket.error:
            pass

        try:
            socket.inet_pton(socket.AF_INET6, host)
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
            try:
                encoded_host = host.encode('idna').decode('ascii')
            except Exception:
                encoded_host = host
                
            loop = asyncio.get_running_loop()
            res = await loop.getaddrinfo(encoded_host, None, family=socket.AF_INET, type=socket.SOCK_STREAM)
            
            if res:
                ip = res[0][4][0]
                if r:
                    try:
                        await r.setex(cache_key, config.DNS_CACHE_TTL, ip)
                    except Exception:
                        pass
                return ip
        except Exception:
            pass
            
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
            remark = str(remark)
            for _ in range(3):
                decoded = urllib.parse.unquote(remark)
                if decoded == remark:
                    break
                remark = decoded

            for code, flag in cls.FLAGS.items():
                if flag in remark:
                    return cls.code_to_region(code)

            remark_lower = remark.lower()
            keyword_map = {
                "germany": "DE", "deutschland": "DE",
                "russia": "RU", "россия": "RU", "москва": "RU", "msk": "RU", "ru": "RU",
                "netherlands": "NL", "holland": "NL",
                "usa": "US", "united states": "US", "america": "US", "unitedstates": "US",
                "uk": "GB", "united kingdom": "GB", "england": "GB",
                "france": "FR", "fr": "FR", "finland": "FI", "turkey": "TR",
                "poland": "PL", "sweden": "SE", "ukraine": "UA",
                "kazakhstan": "KZ", "switzerland": "CH", "italy": "IT",
                "spain": "ES", "canada": "CA", "japan": "JP", "korea": "KR",
                "singapore": "SG", "uae": "AE", "dubai": "AE",
                "lithuania": "LT", "латвия": "LV", "литва": "LT", "эстония": "EE",
                "романия": "RO", "болгария": "BG",
                "美国": "US", "德国": "DE", "俄罗斯": "RU", "荷兰": "NL", "英国": "GB",
                "法国": "FR", "芬兰": "FI", "土耳其": "TR", "波兰": "PL", "瑞典": "SE",
                "瑞士": "CH", "意大利": "IT", "西班牙": "ES", "加拿大": "CA", "日本": "JP",
                "韩国": "KR", "新加坡": "SG", "阿联酋": "AE", "伊朗": "IR", "立陶宛": "LT",
                "拉脱维亚": "LV", "爱沙尼亚": "EE",
            }
            for kw, code in keyword_map.items():
                if re.search(r'\b' + re.escape(kw) + r'\b', remark_lower):
                    return cls.code_to_region(code)

            remark_upper = remark.upper()
            for code in cls.COMMON_REGION_CODES:
                if re.search(rf"(?<![A-Z0-9]){re.escape(code)}(?![A-Z0-9])", remark_upper):
                    return cls.code_to_region(code)

        if host:
            host_lower = host.lower()

            host_code_match = re.search(
                r"(?:^|[._-])(de|us|nl|ru|fi|fr|gb|ua|tr|kz|pl|se|ch|it|es|ca|jp|kr|sg|ae|ir|lt|lv|ee|ro|bg)(?:$|[._-])",
                host_lower,
            )
            if host_code_match:
                return cls.code_to_region(host_code_match.group(1).upper())

            tld_match = re.search(r'\.([a-z]{2})$', host_lower)
            if tld_match:
                tld = tld_match.group(1).upper()
                if tld in cls.FLAGS and tld not in ['CO', 'COM', 'NET', 'ORG', 'IO', 'ME', 'CC', 'TV']: 
                    return cls.code_to_region(tld)

        return "🌍 UNK"

    @classmethod
    async def identify_region_full(
        cls,
        host: str = None,
        remark: str = None,
        session: aiohttp.ClientSession | None = None,
    ) -> str:
        direct = await cls.identify_region(session=session, host=host, remark=remark)
        if direct != "🌍 UNK":
            return direct

        host_value = str(host or "").strip().lower()
        if not host_value:
            return "🌍 UNK"

        redis_client = await cls.get_redis()
        cache_key = f"region:{host_value}"
        if redis_client:
            try:
                cached = await redis_client.get(cache_key)
                if cached:
                    if isinstance(cached, bytes):
                        return cached.decode("utf-8")
                    return str(cached)
            except Exception:
                pass

        ip = await cls.resolve_host(host_value)
        if not ip:
            if redis_client:
                try:
                    await redis_client.setex(cache_key, 1800, "🌍 UNK")
                except Exception:
                    pass
            return "🌍 UNK"

        if cls._reader is None and os.path.exists(cls.DB_PATH):
            try:
                cls._reader = geoip2.database.Reader(cls.DB_PATH)
            except Exception:
                cls._reader = None

        if cls._reader:
            try:
                response = cls._reader.country(ip)
                code = response.country.iso_code
                if code:
                    region = cls.code_to_region(code)
                    if redis_client:
                        try:
                            await redis_client.setex(cache_key, 86400, region)
                        except Exception:
                            pass
                    return region
            except Exception:
                pass

        region = "🌍 UNK"
        try:
            if session is None:
                timeout = aiohttp.ClientTimeout(total=3)
                async with aiohttp.ClientSession(timeout=timeout) as local_session:
                    async with local_session.get(
                        f"http://ip-api.com/json/{ip}?fields=countryCode",
                        timeout=2,
                    ) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            code = data.get("countryCode")
                            if code:
                                region = cls.code_to_region(code)
            else:
                async with session.get(
                    f"http://ip-api.com/json/{ip}?fields=countryCode",
                    timeout=2,
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        code = data.get("countryCode")
                        if code:
                            region = cls.code_to_region(code)
        except Exception:
            pass

        if redis_client:
            try:
                await redis_client.setex(
                    cache_key,
                    86400 if region != "🌍 UNK" else 1800,
                    region,
                )
            except Exception:
                pass

        return region

    @classmethod
    async def get_regions_batch(cls, hosts_data: list, session: aiohttp.ClientSession) -> dict:
        results = {}

        async def process_host(host, remark):
            region = await cls.identify_region(session, host, remark)
            if region != "🌍 UNK":
                return host, region, "remark"

            ip = await cls.resolve_host(host)
            if ip and cls._reader:
                try:
                    response = cls._reader.country(ip)
                    code = response.country.iso_code
                    if code:
                        return host, cls.code_to_region(code), "ip"
                except Exception:
                    pass

            if ip:
                try:
                    async with session.get(f"http://ip-api.com/json/{ip}?fields=countryCode", timeout=2) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            if data.get("countryCode"):
                                return host, cls.code_to_region(data["countryCode"]), "ip"
                except Exception:
                    pass
            return host, "🌍 UNK", "none"

        sem = asyncio.Semaphore(10)
        async def bounded_process(h, r):
            async with sem:
                return await process_host(h, r)

        tasks = [bounded_process(h, r) for h, r in hosts_data]
        res_list = await asyncio.gather(*tasks, return_exceptions=True)
        
        for res in res_list:
            if isinstance(res, tuple) and len(res) == 3:
                h, r, src = res
                results[h] = (r, src)

        return results

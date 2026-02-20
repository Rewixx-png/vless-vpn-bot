import os
import aiohttp
import asyncio
import logging
import socket
import ipaddress
import geoip2.database
from typing import Optional, List
import redis.asyncio as redis
from config import config

logger = logging.getLogger("GeoIP")

class GeoIP:
    # Надежные зеркала MMDB
    MMDB_URLS = [
        "https://github.com/P3TERX/GeoLite.mmdb/raw/download/GeoLite2-Country.mmdb",
        "https://git.io/GeoLite2-Country.mmdb",
        "https://mmdbcdn.issrc.com/ip/GeoLite2-Country.mmdb"
    ]
    DB_PATH = "utils/checker/mmdb/Country.mmdb"
    
    _reader: Optional[geoip2.database.Reader] = None
    _redis: Optional[redis.Redis] = None
    _cf_cidrs: List[ipaddress.IPv4Network | ipaddress.IPv6Network] = []
    _cache = {}
    _dns_cache = {}
    
    # API провайдеры (Fallback). 
    PROVIDERS = [
        {
            "url": "http://ipwho.is/{ip}",
            "key": "country_code",
            "timeout": 5
        },
        {
            "url": "http://ip-api.com/json/{ip}?fields=countryCode",
            "key": "countryCode",
            "timeout": 3
        },
        {
            "url": "https://api.ip.sb/geoip/{ip}",
            "key": "country_code",
            "timeout": 5
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
        ".us": "🇺🇸 United States", ".gov": "🇺🇸 United States",
        ".ca": "🇨🇦 Canada", ".cn": "🇨🇳 China", ".ir": "🇮🇷 Iran",
        ".tr": "🇹🇷 Turkey", ".ua": "🇺🇦 Ukraine", ".kz": "🇰🇿 Kazakhstan",
        ".by": "🇧🇾 Belarus", ".pl": "🇵🇱 Poland", ".it": "🇮🇹 Italy",
        ".es": "🇪🇸 Spain", ".jp": "🇯🇵 Japan", ".kr": "🇰🇷 South Korea",
        ".in": "🇮🇳 India", ".br": "🇧🇷 Brazil", ".se": "🇸🇪 Sweden",
        ".ch": "🇨🇭 Switzerland", ".no": "🇳🇴 Norway", ".ae": "🇦🇪 UAE",
        ".sg": "🇸🇬 Singapore", ".hk": "🇭🇰 Hong Kong", ".au": "🇦🇺 Australia"
    }

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
        "ukraine": "🇺🇦 Ukraine", "kiev": "🇺🇦 Ukraine",
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
        """Initialize Redis, Cloudflare IP ranges, and download MMDB"""
        if cls._redis is None:
            try:
                cls._redis = redis.from_url(config.REDIS_URL, decode_responses=True)
            except Exception as e:
                logger.error(f"Redis init failed: {e}")
        
        # Cloudflare Ranges
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get("https://api.cloudflare.com/client/v4/ips", timeout=5) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        ipv4 = data.get("result", {}).get("ipv4_cidrs", [])
                        ipv6 = data.get("result", {}).get("ipv6_cidrs", [])
                        cls._cf_cidrs = [ipaddress.ip_network(cidr) for cidr in ipv4 + ipv6]
        except Exception:
            pass

        # Check and Download MMDB
        dir_path = os.path.dirname(cls.DB_PATH)
        if not os.path.exists(dir_path):
            os.makedirs(dir_path)

        if not os.path.exists(cls.DB_PATH) or os.path.getsize(cls.DB_PATH) < 1000000:
            logger.info("📥 Downloading GeoLite2 Database...")
            async with aiohttp.ClientSession() as session:
                for url in cls.MMDB_URLS:
                    try:
                        async with session.get(url, timeout=30) as resp:
                            if resp.status == 200:
                                with open(cls.DB_PATH, 'wb') as f:
                                    f.write(await resp.read())
                                logger.info(f"✅ Downloaded MMDB from {url}")
                                break
                    except Exception:
                        continue

        try:
            cls._reader = geoip2.database.Reader(cls.DB_PATH)
        except Exception:
            cls._reader = None

    @classmethod
    def _is_cloudflare(cls, ip_str: str) -> bool:
        if not cls._cf_cidrs: return False
        try:
            ip = ipaddress.ip_address(ip_str)
            for cidr in cls._cf_cidrs:
                if ip in cidr: return True
        except ValueError: pass
        return False

    @classmethod
    async def _resolve_host(cls, host: str) -> str | None:
        if host in cls._dns_cache: return cls._dns_cache[host]
        try:
            ipaddress.ip_address(host)
            return host
        except ValueError:
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
        if not code or len(code) != 2: return "🌍 Unk"
        flag = cls.FLAGS.get(code.upper(), "🌍")
        return f"{flag} {code.upper().title()}"

    @classmethod
    def _get_from_db(cls, ip: str) -> str | None:
        if not cls._reader: return None
        try:
            response = cls._reader.country(ip)
            code = response.country.iso_code
            if code: return cls._format_result(code)
        except Exception: pass
        return None

    @classmethod
    async def identify_region(cls, session: aiohttp.ClientSession, host: str = None, remark: str = None, proxy_ip: str = None) -> str:
        target_ip = proxy_ip
        if not target_ip and host:
            target_ip = await cls._resolve_host(host)

        # 1. Cache
        if target_ip:
            if target_ip in cls._cache and "Unk" not in cls._cache[target_ip]:
                return cls._cache[target_ip]
            if cls._redis:
                try:
                    cached = await cls._redis.get(f"geoip:{target_ip}")
                    if cached and "Unk" not in cached:
                        cls._cache[target_ip] = cached
                        return cached
                except: pass

        # 2. Local MMDB
        if target_ip and not cls._is_cloudflare(target_ip):
            if not cls._reader: await cls.initialize()
            local_res = cls._get_from_db(target_ip)
            if local_res:
                cls._cache[target_ip] = local_res
                if cls._redis: await cls._redis.setex(f"geoip:{target_ip}", 604800, local_res)
                return local_res

        # 3. API Fallback
        if target_ip and not cls._is_cloudflare(target_ip):
            for provider in cls.PROVIDERS:
                try:
                    url = provider["url"].format(ip=target_ip)
                    async with session.get(url, timeout=provider["timeout"]) as resp:
                        if resp.status == 200:
                            if "json" in url or "ipwho.is" in url:
                                data = await resp.json(content_type=None)
                                if "success" in data and not data["success"]: continue
                                code = data.get(provider["key"])
                            else:
                                code = await resp.text()
                            
                            if code:
                                code = code.strip()[:2]
                                res = cls._format_result(code)
                                if "Unk" not in res:
                                    cls._cache[target_ip] = res
                                    if cls._redis: await cls._redis.setex(f"geoip:{target_ip}", 604800, res)
                                    return res
                except Exception:
                    continue

        # 4. Heuristics
        if remark:
            guess = cls._guess_by_name(remark)
            if guess: return guess

        if host:
            guess = cls._guess_by_tld(host)
            if guess: return guess
            
            host_lower = host.lower()
            for iata in ["fra", "ams", "lon", "nyc", "lax", "sgp", "jpn"]:
                if f"{iata}." in host_lower or f"-{iata}" in host_lower:
                    if iata == "fra": return "🇩🇪 Germany"
                    if iata == "ams": return "🇳🇱 Netherlands"
                    if iata == "lon": return "🇬🇧 United Kingdom"
                    if iata == "nyc": return "🇺🇸 United States"
                    if iata == "lax": return "🇺🇸 United States"
                    if iata == "sgp": return "🇸🇬 Singapore"

        if target_ip:
            cls._cache[target_ip] = "🌍 Unk"
            if cls._redis: await cls._redis.setex(f"geoip:{target_ip}", 60, "🌍 Unk")

        return "🌍 Unk"

    @classmethod
    def _guess_by_tld(cls, host: str) -> str | None:
        host = host.lower().strip()
        for tld, region in cls.TLD_MAP.items():
            if host.endswith(tld): return region
        return None

    @classmethod
    def _guess_by_name(cls, name: str) -> str | None:
        if not name: return None
        name_lower = name.lower()
        for keyword, region in cls.NAME_KEYWORDS.items():
            if keyword in name_lower: return region
        return None

    # THE MISSING METHOD
    @classmethod
    async def get_regions_batch(cls, hosts_data: list, session: aiohttp.ClientSession) -> dict:
        """Batch processing for Admin Recheck"""
        if not cls._reader: await cls.initialize()
        results = {}
        
        sem = asyncio.Semaphore(50) 
        
        async def resolve_and_identify(host, remark):
            async with sem:
                res = await cls.identify_region(session, host=host, remark=remark)
                results[host] = res

        tasks = [resolve_and_identify(h, r) for h, r in hosts_data]
        await asyncio.gather(*tasks)
        return results
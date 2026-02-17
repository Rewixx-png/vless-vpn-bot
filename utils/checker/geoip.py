import aiohttp
import asyncio
import random

class GeoIP:
    GEOIP_PROVIDERS = [
        {"url": "http://ip-api.com/json/?fields=country,countryCode", "code_key": "countryCode", "name_key": "country"},
        {"url": "https://ipwho.is/", "code_key": "country_code", "name_key": "country"},
        {"url": "https://api.ip.sb/geoip", "code_key": "country_code", "name_key": "country"},
        {"url": "https://ipinfo.io/json", "code_key": "country", "name_key": None},
        {"url": "https://api.myip.com", "code_key": "cc", "name_key": "country"},
        {"url": "https://ifconfig.co/json", "code_key": "country_iso", "name_key": "country"},
        {"url": "https://freeipapi.com/api/json", "code_key": "countryCode", "name_key": "countryName"},
        {"url": "https://ip.guide/", "code_key": "country", "name_key": None, "nested": "location"}, 
        {"url": "https://www.iplocate.io/api/lookup/", "code_key": "country_code", "name_key": "country"},
        {"url": "https://ipapi.co/json/", "code_key": "country_code", "name_key": "country_name"},
        {"url": "http://www.geoplugin.net/json.gp", "code_key": "geoplugin_countryCode", "name_key": "geoplugin_countryName"},
        {"url": "https://api.db-ip.com/v2/free/self", "code_key": "countryCode", "name_key": "countryName"},
        {"url": "https://reallyfreegeoip.org/json/", "code_key": "country_code", "name_key": "country_name"},
        {"url": "https://api.dazzlepod.com/ip.json", "code_key": "country_code", "name_key": None},
        {"url": "https://ip-api.io/json", "code_key": "country_code", "name_key": "country_name"}
    ]

    @staticmethod
    def _get_flag_emoji(country_code: str) -> str:
        if not country_code or len(country_code) != 2:
            return "🌍"
        return "".join(chr(ord(c.upper()) + 127397) for c in country_code)

    @classmethod
    async def identify_region(cls, session: aiohttp.ClientSession, ip: str = None) -> str:
        region = "🌍 Unk"
        
        # Shuffle providers to distribute load and avoid rate limits
        providers = cls.GEOIP_PROVIDERS.copy()
        random.shuffle(providers)
        
        for provider in providers:
            try:
                if "special_parsing" in provider:
                    continue

                url = provider["url"]
                # Append IP to URL if provided and supported by the API structure usually (simplified here)
                # Most of these APIs support /json/IP or ?ip=IP. 
                # For simplicity in this robust version, we will try to use the ones that support IP path/query if IP is given.
                # However, for checking REMOTE servers (not self), we MUST pass the IP.
                # The previous implementation relied on 'self' check or 'batch'.
                
                target_url = url
                if ip:
                    # Adaptive URL formatting for common APIs
                    if "ip-api.com" in url:
                        target_url = f"http://ip-api.com/json/{ip}?fields=country,countryCode"
                    elif "ipwho.is" in url:
                        target_url = f"https://ipwho.is/{ip}"
                    elif "ipinfo.io" in url:
                        target_url = f"https://ipinfo.io/{ip}/json"
                    elif "freeipapi.com" in url:
                        target_url = f"https://freeipapi.com/api/json/{ip}"
                    elif "ipapi.co" in url:
                        target_url = f"https://ipapi.co/{ip}/json/"
                    elif "db-ip.com" in url:
                        target_url = f"https://api.db-ip.com/v2/free/{ip}"
                    else:
                        # Skip providers that don't easily support IP arg in this simple logic
                        continue

                async with session.get(target_url, timeout=4.0) as geo_resp:
                    if geo_resp.status == 200:
                        data = await geo_resp.json(content_type=None)
                        
                        code = None
                        if provider.get("nested"):
                            nested = data.get(provider["nested"])
                            if nested: 
                                code = nested.get(provider["code_key"])
                        else:
                            code = data.get(provider["code_key"])
                            
                        if code and len(code) == 2:
                            code = code.upper()
                            flag = cls._get_flag_emoji(code)
                            short_name = code.title()
                            
                            region = f"{flag} {short_name}"
                            return region
            except Exception: 
                continue
                
        return region

    @classmethod
    async def get_regions_batch(cls, ips: list[str], session: aiohttp.ClientSession) -> dict[str, str]:
        """
        Concurrently resolve multiple IPs using rotation of providers.
        Much more reliable than a single batch API call.
        """
        results = {}
        if not ips: return results
        
        # Semaphore to prevent opening too many connections at once
        sem = asyncio.Semaphore(20)

        async def resolve_one(ip):
            async with sem:
                region = await cls.identify_region(session, ip)
                if region and "Unk" not in region:
                    return ip, region
                return ip, None

        tasks = [resolve_one(ip) for ip in ips]
        resolved = await asyncio.gather(*tasks)

        for ip, reg in resolved:
            if reg:
                results[ip] = reg
        
        return results
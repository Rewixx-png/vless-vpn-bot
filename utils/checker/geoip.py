import aiohttp

class GeoIP:
    GEOIP_PROVIDERS = [
        {"url": "http://ip-api.com/json/?fields=country,countryCode", "code_key": "countryCode", "name_key": None},
        {"url": "https://ipwho.is/", "code_key": "country_code", "name_key": None},
        {"url": "https://api.myip.com", "code_key": "cc", "name_key": None},
        {"url": "https://ipinfo.io/json", "code_key": "country", "name_key": None},
        {"url": "https://ifconfig.co/json", "code_key": "country_iso", "name_key": None},
        {"url": "https://freeipapi.com/api/json", "code_key": "countryCode", "name_key": None},
        {"url": "https://api.ip.sb/geoip", "code_key": "country_code", "name_key": None},
        {"url": "https://ip.guide/", "code_key": "country", "name_key": None, "nested": "location"}, 
        {"url": "https://www.iplocate.io/api/lookup/", "code_key": "country_code", "name_key": None},
        {"url": "https://ipapi.co/json/", "code_key": "country_code", "name_key": None} 
    ]

    @staticmethod
    def _get_flag_emoji(country_code: str) -> str:
        if not country_code or len(country_code) != 2:
            return "🌍"
        return "".join(chr(ord(c.upper()) + 127397) for c in country_code)

    @classmethod
    async def identify_region(cls, session: aiohttp.ClientSession) -> str:
        region = "🌍 UNK"
        for provider in cls.GEOIP_PROVIDERS:
            try:
                async with session.get(provider["url"], timeout=2.5) as geo_resp:
                    if geo_resp.status == 200:
                        data = await geo_resp.json()
                        code = None
                        if provider.get("nested"):
                            nested = data.get(provider["nested"])
                            if nested: code = nested.get(provider["code_key"])
                        else:
                            code = data.get(provider["code_key"])
                            
                        if code and len(code) == 2:
                            region = f"{cls._get_flag_emoji(code)} {code.upper()}"
                            break
            except: continue
        return region

    @classmethod
    async def get_regions_batch(cls, ips: list[str], session: aiohttp.ClientSession) -> dict[str, str]:
        results = {}
        if not ips: return results
        try:
            for i in range(0, len(ips), 100):
                chunk = ips[i:i+100]
                try:
                    payload = [{"query": ip, "fields": "status,query,country,countryCode"} for ip in chunk]
                    async with session.post("http://ip-api.com/batch", json=payload, timeout=10) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            for item in data:
                                if item.get("status") == "success":
                                    code = item.get("countryCode")
                                    results[item.get("query")] = f"{cls._get_flag_emoji(code)} {code}"
                except: pass
        except: pass
        return results
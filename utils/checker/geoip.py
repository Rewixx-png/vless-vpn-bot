import aiohttp

class GeoIP:
    GEOIP_PROVIDERS = [
        # Primary High-Reliability APIs
        {"url": "http://ip-api.com/json/?fields=country,countryCode", "code_key": "countryCode", "name_key": "country"},
        {"url": "https://ipwho.is/", "code_key": "country_code", "name_key": "country"},
        {"url": "https://api.ip.sb/geoip", "code_key": "country_code", "name_key": "country"},
        {"url": "https://ipinfo.io/json", "code_key": "country", "name_key": None},
        
        # Secondary Backup APIs
        {"url": "https://api.myip.com", "code_key": "cc", "name_key": "country"},
        {"url": "https://ifconfig.co/json", "code_key": "country_iso", "name_key": "country"},
        {"url": "https://freeipapi.com/api/json", "code_key": "countryCode", "name_key": "countryName"},
        {"url": "https://ip.guide/", "code_key": "country", "name_key": None, "nested": "location"}, 
        {"url": "https://www.iplocate.io/api/lookup/", "code_key": "country_code", "name_key": "country"},
        {"url": "https://ipapi.co/json/", "code_key": "country_code", "name_key": "country_name"},
        
        # New Additional Providers
        {"url": "http://www.geoplugin.net/json.gp", "code_key": "geoplugin_countryCode", "name_key": "geoplugin_countryName"},
        {"url": "https://api.db-ip.com/v2/free/self", "code_key": "countryCode", "name_key": "countryName"},
        {"url": "https://ip2c.org/self", "special_parsing": "ip2c"}, # Special handling needed? No, standard JSON expected usually but ip2c returns text "1;CC;COUNTRY"
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
    async def identify_region(cls, session: aiohttp.ClientSession) -> str:
        region = "🌍 UNK"
        
        # Iterate through providers until we find a valid country code
        for provider in cls.GEOIP_PROVIDERS:
            try:
                # Special handling for text-based APIs if implemented later, skipping for now to keep it simple JSON
                if "special_parsing" in provider:
                    continue

                async with session.get(provider["url"], timeout=3.0) as geo_resp:
                    if geo_resp.status == 200:
                        data = await geo_resp.json(content_type=None) # content_type=None allows text/plain treated as json if valid
                        
                        code = None
                        name = None

                        if provider.get("nested"):
                            nested = data.get(provider["nested"])
                            if nested: 
                                code = nested.get(provider["code_key"])
                                name = nested.get(provider.get("name_key")) if provider.get("name_key") else None
                        else:
                            code = data.get(provider["code_key"])
                            name = data.get(provider.get("name_key")) if provider.get("name_key") else None
                            
                        if code and len(code) == 2:
                            # Normalize code
                            code = code.upper()
                            
                            # Construct Region String
                            flag = cls._get_flag_emoji(code)
                            
                            # Prefer full name if available, else code
                            if name:
                                region = f"{flag} {name}"
                            else:
                                region = f"{flag} {code}"
                                
                            break # Found it, stop looking
            except Exception: 
                continue # Try next provider
                
        return region

    @classmethod
    async def get_regions_batch(cls, ips: list[str], session: aiohttp.ClientSession) -> dict[str, str]:
        results = {}
        if not ips: return results
        
        # Primary Batch: ip-api.com (Supports batch up to 100)
        try:
            for i in range(0, len(ips), 100):
                chunk = ips[i:i+100]
                try:
                    payload = [{"query": ip, "fields": "status,query,country,countryCode"} for ip in chunk]
                    async with session.post("http://ip-api.com/batch", json=payload, timeout=15) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            for item in data:
                                if item.get("status") == "success":
                                    code = item.get("countryCode")
                                    name = item.get("country")
                                    query = item.get("query")
                                    
                                    if code and query:
                                        flag = cls._get_flag_emoji(code)
                                        results[query] = f"{flag} {name}"
                except: pass
        except: pass
        
        return results
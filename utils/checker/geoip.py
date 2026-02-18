import aiohttp
import asyncio

class GeoIP:
    # Используем ip-api.com batch (до 100 IP за запрос - бесплатно)
    BATCH_API_URL = "http://ip-api.com/json/batch"
    
    # Fallback провайдеры для batch failures
    FALLBACK_PROVIDERS = [
        {"url": "https://ipwho.is/{ip}", "code_key": "country_code"},
        {"url": "https://api.ip.sb/geoip", "code_key": "country_code"},
        {"url": "https://ipapi.co/{ip}/json/", "code_key": "country_code"},
    ]
    
    # Semaphore для контроля параллельных запросов
    CONCURRENCY = 50
    BATCH_SIZE = 100  # Максимум для ip-api.com batch
    
    # Кэш для результатов (чтобы не проверять одни и те же IP)
    _cache = {}

    @staticmethod
    def _get_flag_emoji(country_code: str) -> str:
        if not country_code or len(country_code) != 2:
            return "🌍"
        return "".join(chr(ord(c.upper()) + 127397) for c in country_code)

    @classmethod
    def _format_region(cls, country_code: str) -> str:
        if not country_code or len(country_code) != 2:
            return "🌍 Unk"
        flag = cls._get_flag_emoji(country_code)
        return f"{flag} {country_code.upper().title()}"

    @classmethod
    async def get_regions_batch(cls, ips: list[str], session: aiohttp.ClientSession) -> dict[str, str]:
        """
        Оптимизированная версия с batch API.
        1. Убираем дубликаты IP
        2. Используем batch API (до 100 IP за раз)
        3. Для оставшихся - параллельные fallback запросы
        4. Маппим результаты обратно на все входящие IP
        """
        if not ips:
            return {}
        
        # Получаем уникальные IP для запроса (исключая локальные)
        unique_ips = []
        seen = set()
        for ip in ips:
            if ip and ip not in ["127.0.0.1", "localhost"] and ip not in seen:
                unique_ips.append(ip)
                seen.add(ip)
        
        if not unique_ips:
            return {}
        
        # Проверяем уникальные IP через batch API
        await cls._batch_lookup(unique_ips, session)
        
        # Для неразрешённых - fallback
        unresolved = [ip for ip in unique_ips if ip not in cls._cache or cls._cache.get(ip) == "🌍 Unk"]
        if unresolved:
            await cls._fallback_lookup(unresolved, session)
        
        # Маппим результаты обратно на все входящие IP (включая дубликаты)
        results = {}
        for ip in ips:
            if ip in ["127.0.0.1", "localhost"]:
                results[ip] = "🌍 Unk"
            elif ip in cls._cache:
                results[ip] = cls._cache[ip]
            else:
                results[ip] = "🌍 Unk"
        
        return results

    @classmethod
    async def _batch_lookup(cls, ips: list[str], session: aiohttp.ClientSession):
        """Batch запрос к ip-api.com (до 100 IP за раз)"""
        
        # Обрабатываем батчами по 100 IP
        for i in range(0, len(ips), cls.BATCH_SIZE):
            batch = ips[i:i + cls.BATCH_SIZE]
            
            payload = [{"query": ip} for ip in batch]
            
            try:
                async with session.post(
                    cls.BATCH_API_URL,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        
                        if isinstance(data, list):
                            for item in data:
                                ip = item.get("query") or item.get("ip")
                                country_code = item.get("countryCode")
                                
                                if ip and country_code:
                                    region = cls._format_region(country_code)
                                    cls._cache[ip] = region
                        elif isinstance(data, dict):
                            # ip-api может вернуть ошибку batch
                            if data.get("status") == "fail":
                                pass  # Обработаем через fallback
            except Exception:
                pass

    @classmethod
    async def _fallback_lookup(cls, ips: list[str], session: aiohttp.ClientSession):
        """Fallback параллельные запросы для неразрешённых IP"""
        if not ips:
            return
        
        sem = asyncio.Semaphore(cls.CONCURRENCY)
        
        async def resolve_one(ip: str):
            async with sem:
                for provider in cls.FALLBACK_PROVIDERS:
                    try:
                        url = provider["url"].format(ip=ip)
                        async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                            if resp.status == 200:
                                data = await resp.json(content_type=None)
                                code = data.get(provider["code_key"])
                                
                                if code and len(code) == 2:
                                    region = cls._format_region(code)
                                    cls._cache[ip] = region
                                    return
                    except Exception:
                        continue
                
                # Если ничего не помогло
                cls._cache[ip] = "🌍 Unk"
        
        # Запускаем всё параллельно
        await asyncio.gather(*[resolve_one(ip) for ip in ips], return_exceptions=True)

    @classmethod
    async def identify_region(cls, session: aiohttp.ClientSession, ip: str = None) -> str:
        """Определение региона для одного IP (для обратной совместимости)"""
        if not ip or ip in ["127.0.0.1", "localhost"]:
            return "🌍 Unk"
        
        # Проверяем кэш
        if ip in cls._cache:
            return cls._cache[ip]
        
        # Используем fallback провайдеры
        for provider in cls.FALLBACK_PROVIDERS:
            try:
                url = provider["url"].format(ip=ip)
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                    if resp.status == 200:
                        data = await resp.json(content_type=None)
                        code = data.get(provider["code_key"])
                        
                        if code and len(code) == 2:
                            region = cls._format_region(code)
                            cls._cache[ip] = region
                            return region
            except Exception:
                continue
        
        cls._cache[ip] = "🌍 Unk"
        return "🌍 Unk"

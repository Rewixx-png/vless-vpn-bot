import logging
import aiohttp
from utils.parser import LinkParser
from utils.checker.api import CheckerAPI
from utils.checker.geoip import GeoIP
from utils.checker.xray import XrayExecutor

logger = logging.getLogger("Checker")

class VlessChecker:
    @staticmethod
    def parse_config(config_url: str):
        return LinkParser.parse_vless(config_url)

    @staticmethod
    async def process_subscription(config_url: str) -> tuple[bool, str, int, bool, str]:
        """
        Основной метод проверки. 
        Пытается использовать микросервис.
        Если микросервис недоступен, фоллбэк на локальный запуск (но лучше запустить сервис!)
        """
        # Попытка через API сервиса
        success, region, latency, ai, err = await CheckerAPI.check(config_url)
        
        if not success and err == "Checker Service Offline":
            # FALLBACK: Если сервис лежит, пробуем локально (но с риском загрузить CPU)
            # Это на случай если юзер забыл запустить сервис
            # logger.warning("Checker Service is offline! Using local check (High Load Risk).")
            # Временно возвращаем ошибку, чтобы принудить юзера запустить сервис
            return False, "", 0, False, "Checker Service Offline (Start utils/checker/service.py)"
            
        return success, region, latency, ai, err

    @classmethod
    async def get_regions_batch(cls, ips: list[str], session: aiohttp.ClientSession) -> dict[str, str]:
        return await GeoIP.get_regions_batch(ips, session)

    @staticmethod
    async def verify_domain(domain: str) -> tuple[bool, str]:
        try:
            import asyncio
            loop = asyncio.get_running_loop()
            try:
                ip = await loop.getaddrinfo(domain, 80)
                ip_addr = ip[0][4][0]
            except: return False, "DNS Resolve Failed"
            return True, f"OK ({ip_addr})"
        except Exception as e: return False, str(e)
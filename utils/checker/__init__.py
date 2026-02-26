import logging
import aiohttp
from utils.parser import LinkParser
from utils.checker.api import CheckerAPI
from utils.checker.geo_ip import GeoIP
from utils.checker.xray import XrayExecutor

logger = logging.getLogger("Checker")

class VlessChecker:
    @staticmethod
    def parse_config(config_url: str):
        return LinkParser.parse_vless(config_url)

    @staticmethod
    async def process_subscription(config_url: str) -> tuple[bool, str, int, float, bool, str]:
        success, region, latency, speed_mbps, ai, err = await CheckerAPI.check(config_url)
        
        if not success and err and str(err).startswith("SYS_ERR"):
            return False, "", 0, 0.0, False, err
            
        return success, region, latency, speed_mbps, ai, err

    @classmethod
    async def get_regions_batch(cls, hosts_data: list[tuple[str, str]], session: aiohttp.ClientSession) -> dict[str, str]:
        if hosts_data and isinstance(hosts_data[0], str):
            hosts_data = [(h, "") for h in hosts_data]
            
        return await GeoIP.get_regions_batch(hosts_data, session)

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
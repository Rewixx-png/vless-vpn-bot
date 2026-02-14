import asyncio
import aiohttp
import time
import logging
from aiohttp_socks import ProxyConnector
from .xray import XrayExecutor
from .geoip import GeoIP
from utils.parser import LinkParser

logger = logging.getLogger("Checker")

class VlessChecker:
    @staticmethod
    def parse_config(config_url: str):
        return LinkParser.parse_vless(config_url)

    @classmethod
    async def process_subscription(cls, config_url: str) -> tuple[bool, str, int, bool, str]:
        process, local_port, config_path = await XrayExecutor.start_xray(config_url)
        
        if not process:
            # config_path тут содержит ошибку
            return False, "", 0, False, config_path

        connector = ProxyConnector.from_url(f"socks5://127.0.0.1:{local_port}")
        timeout = aiohttp.ClientTimeout(total=6, connect=3)
        
        try:
            async with aiohttp.ClientSession(connector=connector, timeout=timeout) as proxy_session:
                start_time = time.monotonic()
                latency = 9999
                
                try:
                    async with proxy_session.get('http://cp.cloudflare.com/generate_204', allow_redirects=False) as resp:
                        if resp.status in [200, 204]:
                            latency = int((time.monotonic() - start_time) * 1000)
                        else:
                            raise Exception(f"Status {resp.status}")
                except Exception as e:
                    return False, "", 0, False, f"Connection Failed: {str(e)}"

                region = "🌍 UNK"
                ai_available = False

                if latency < 2000:
                    try:
                        ai_timeout = aiohttp.ClientTimeout(total=2.5)
                        async with proxy_session.get('https://api.openai.com/v1/models', timeout=ai_timeout) as ai_resp:
                            if ai_resp.status in [200, 401, 403]:
                                ai_available = True
                    except: pass

                    region = await GeoIP.identify_region(proxy_session)

            return True, region, latency, ai_available, "OK"

        except asyncio.CancelledError:
            if process:
                process.kill()
                await process.wait()
            raise 

        except Exception as e:
            return False, "", 0, False, f"System Error: {e}"

        finally:
            XrayExecutor.cleanup(process, config_path)

    @classmethod
    async def get_regions_batch(cls, ips: list[str], session: aiohttp.ClientSession) -> dict[str, str]:
        return await GeoIP.get_regions_batch(ips, session)

    @staticmethod
    async def verify_domain(domain: str) -> tuple[bool, str]:
        try:
            loop = asyncio.get_running_loop()
            try:
                ip = await loop.getaddrinfo(domain, 80)
                ip_addr = ip[0][4][0]
            except: return False, "DNS Resolve Failed"
            return True, f"OK ({ip_addr})"
        except Exception as e: return False, str(e)
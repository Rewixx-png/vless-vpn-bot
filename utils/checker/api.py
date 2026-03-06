import aiohttp
import asyncio
import logging
from config import config

logger = logging.getLogger("CheckerAPI")

class CheckerAPI:
    _session: aiohttp.ClientSession | None = None

    @classmethod
    async def get_session(cls) -> aiohttp.ClientSession:
        if cls._session is None or cls._session.closed:
            timeout = aiohttp.ClientTimeout(total=45.0, connect=10.0)
            connector = aiohttp.TCPConnector(limit=100, ttl_dns_cache=config.DNS_CACHE_TTL)
            cls._session = aiohttp.ClientSession(
                connector=connector, 
                timeout=timeout,
                cookie_jar=aiohttp.DummyCookieJar()
            )
        return cls._session

    @staticmethod
    async def check(config_url: str) -> tuple:
        session = await CheckerAPI.get_session()
        try:
            async with session.post(
                f"{config.CHECKER_URL}/check",
                json={"config": config_url}
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    
                    if "error" in data and not data.get("success", False):
                            err_msg = data.get("error", "Unknown Error")
                            if "Worker Busy" in err_msg and "SYS_ERR" not in err_msg:
                                err_msg = f"SYS_ERR: {err_msg}"
                            return False, "", 0, 0.0, False, False, err_msg
                    
                    return (
                        data.get("success", False),
                        data.get("region", "🌍 UNK"),
                        data.get("latency", 9999),
                        data.get("speed_mbps", 0.0),
                        data.get("ai", False),
                        data.get("no_ads", False),
                        data.get("error", "OK")
                    )
                elif resp.status == 503:
                    return False, "", 0, 0.0, False, False, "SYS_ERR: Worker Busy (503)"
                else:
                    return False, "", 0, 0.0, False, False, f"SYS_ERR: Service Error {resp.status}"
                    
        except aiohttp.ClientConnectorError:
            return False, "", 0, 0.0, False, False, "SYS_ERR: Checker Service Offline"
        except asyncio.TimeoutError:
            return False, "", 0, 0.0, False, False, "SYS_ERR: Checker API Timeout"
        except Exception as e:
            return False, "", 0, 0.0, False, False, f"SYS_ERR: API Error: {str(e)}"

    @classmethod
    async def close(cls):
        if cls._session:
            await cls._session.close()
            cls._session = None
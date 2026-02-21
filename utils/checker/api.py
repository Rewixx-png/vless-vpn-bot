import aiohttp
import logging
from config import config

logger = logging.getLogger("CheckerAPI")

class CheckerAPI:
    @staticmethod
    async def check(config_url: str) -> tuple:
        try:
            timeout = aiohttp.ClientTimeout(total=60.0)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(
                    f"{config.CHECKER_URL}/check",
                    json={"config": config_url}
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        if "error" in data and not "success" in data:
                             err_msg = data.get("error", "Unknown Error")
                             if "SYS_ERR" in err_msg:
                                 return False, "", 0, 0.0, False, err_msg
                             return False, "", 0, 0.0, False, err_msg
                             
                        return (
                            data.get("success", False),
                            data.get("region", "🌍 UNK"),
                            data.get("latency", 9999),
                            data.get("speed_mbps", 0.0),
                            data.get("ai", False),
                            data.get("error", "OK")
                        )
                    else:
                        return False, "", 0, 0.0, False, f"SYS_ERR: Service Error {resp.status}"
        except aiohttp.ClientConnectorError:
            return False, "", 0, 0.0, False, "SYS_ERR: Checker Service Offline"
        except asyncio.TimeoutError:
            return False, "", 0, 0.0, False, "SYS_ERR: Checker Service Timeout"
        except Exception as e:
            return False, "", 0, 0.0, False, f"SYS_ERR: API Error: {str(e)}"
import aiohttp
import logging
from config import config

logger = logging.getLogger("CheckerAPI")

class CheckerAPI:
    @staticmethod
    async def check(config_url: str) -> tuple[bool, str, int, bool, str]:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{config.CHECKER_URL}/check",
                    json={"config": config_url},
                    timeout=15
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        if "error" in data and not "success" in data:
                             return False, "", 0, False, data["error"]
                             
                        return (
                            data.get("success", False),
                            data.get("region", "🌍 UNK"),
                            data.get("latency", 9999),
                            data.get("ai", False),
                            data.get("error", "OK")
                        )
                    else:
                        return False, "", 0, False, f"Service Error: {resp.status}"
        except aiohttp.ClientConnectorError:
            return False, "", 0, False, "Checker Service Offline"
        except Exception as e:
            return False, "", 0, False, f"API Error: {str(e)}"
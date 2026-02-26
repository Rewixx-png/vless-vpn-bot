import aiohttp
import asyncio
import logging
from config import config

logger = logging.getLogger("CheckerAPI")

class CheckerAPI:
    @staticmethod
    async def check(config_url: str) -> tuple:
        try:
            # Общий таймаут клиента 60с, но чекер ответит быстрее
            timeout = aiohttp.ClientTimeout(total=60.0)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(
                    f"{config.CHECKER_URL}/check",
                    json={"config": config_url}
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        # Если API вернул явную ошибку
                        if "error" in data and not data.get("success", False):
                             err_msg = data.get("error", "Unknown Error")
                             if "Worker Busy" in err_msg and "SYS_ERR" not in err_msg:
                                 err_msg = f"SYS_ERR: {err_msg}"
                             # Возвращаем как есть
                             return False, "", 0, 0.0, False, err_msg
                        
                        # Успешный ответ (даже если latency 9999, главное success=True)
                        return (
                            data.get("success", False),
                            data.get("region", "🌍 UNK"),
                            data.get("latency", 9999),
                            data.get("speed_mbps", 0.0),
                            data.get("ai", False),
                            data.get("error", "OK")
                        )
                    elif resp.status == 503:
                        return False, "", 0, 0.0, False, "SYS_ERR: Worker Busy (503)"
                    else:
                        return False, "", 0, 0.0, False, f"SYS_ERR: Service Error {resp.status}"
        except aiohttp.ClientConnectorError:
            return False, "", 0, 0.0, False, "SYS_ERR: Checker Service Offline"
        except asyncio.TimeoutError:
            return False, "", 0, 0.0, False, "SYS_ERR: Checker API Timeout"
        except Exception as e:
            return False, "", 0, 0.0, False, f"SYS_ERR: API Error: {str(e)}"
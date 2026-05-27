import asyncio
import time
from utils.checker import VlessChecker
from config import config

async def main():
    config.CHECKER_USE_RU_PROXY_CHAIN = False
    link = "vless://2420af47-2316-482e-bb0f-b164df4b2334@84.201.159.228:443?flow=xtls-rprx-vision&encryption=none&type=tcp&security=reality&fp=chrome&sni=ads.x5.ru&pbk=1vSZjvhZO01oAEH3b7eebR1qF5dLU1Dq2E7xu8pwGSs&sid=428ef87fd47a3a32#Albania"
    start = time.time()
    res = await VlessChecker.process_subscription(link, strict_speed=False)
    end = time.time()
    print(f"Time: {end - start:.2f}s")
    print(f"Result: {res}")

if __name__ == "__main__":
    asyncio.run(main())

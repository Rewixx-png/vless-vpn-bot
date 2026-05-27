import asyncio
from utils.checker import VlessChecker
import time

async def main():
    link = "vless://00000000-0000-0000-0000-000000000000@1.1.1.1:443?encryption=none&security=tls&sni=example.com&type=tcp#Test"
    start = time.time()
    res = await VlessChecker.process_subscription(link)
    end = time.time()
    print(f"Time: {end - start:.2f}s")
    print(f"Result: {res}")

asyncio.run(main())

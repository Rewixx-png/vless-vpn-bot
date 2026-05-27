import asyncio
from utils.checker import VlessChecker

async def main():
    ok, latency, err = await VlessChecker.measure_tcp_jitter("1.1.1.1", 443)
    print(f"Jitter ok: {ok}, err: {err}")

asyncio.run(main())

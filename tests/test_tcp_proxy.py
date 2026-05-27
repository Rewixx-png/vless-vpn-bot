import asyncio
from utils.checker import VlessChecker
from utils.checker.proxy_pool import UpstreamProxy

async def main():
    proxy = UpstreamProxy(scheme="socks5", host="127.0.0.1", port=19080)
    # czu.ksnodes.net resolves to some IP. Let's test a known good IP. 1.1.1.1 port 443
    ok, lat, err = await VlessChecker._check_tcp_via_proxy("1.1.1.1", 443, 5.0, proxy)
    print(f"1.1.1.1: ok={ok}, lat={lat}, err={err}")

    ok, lat, err = await VlessChecker._check_tcp_via_proxy("150.241.74.149", 443, 5.0, proxy)
    print(f"150.241.74.149: ok={ok}, lat={lat}, err={err}")

asyncio.run(main())

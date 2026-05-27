import asyncio
from utils.checker.proxy_pool import UpstreamProxy, ProxyPool

async def main():
    proxy = UpstreamProxy(scheme="socks5", host="127.0.0.1", port=19080)
    ok, err = await ProxyPool._quick_probe_paid_proxy(proxy)
    print(f"Proxy probe: ok={ok}, err={err}")

asyncio.run(main())

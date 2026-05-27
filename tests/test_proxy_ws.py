import asyncio
from utils.checker.xray import XrayExecutor

async def main():
    link = "vless://b6ce8a51-19b9-4979-91ba-b4298c26d5fc@czu.ksnodes.net:443?type=tcp&security=tls&encryption=none&flow=xtls-rprx-vision&alpn=http/1.1,h2"
    process, port, config_path = await XrayExecutor.start_xray(link)
    print("Direct start:", process, port)
    
    if process:
        try:
            from utils.checker.service import check_connectivity
            ok, lat, err = await check_connectivity(port)
            print("Direct connect:", ok, lat, err)
        finally:
            await XrayExecutor.cleanup(process, config_path)
            
    upstream = {'scheme': 'socks5', 'host': '127.0.0.1', 'port': 19080}
    process, port, config_path = await XrayExecutor.start_xray(link, upstream_proxy=upstream)
    print("Proxy start:", process, port)
    
    if process:
        try:
            from utils.checker.service import check_connectivity
            ok, lat, err = await check_connectivity(port)
            print("Proxy connect:", ok, lat, err)
        finally:
            await XrayExecutor.cleanup(process, config_path)

asyncio.run(main())

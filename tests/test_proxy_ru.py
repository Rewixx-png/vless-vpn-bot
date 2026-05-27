import asyncio
from utils.checker.xray import XrayExecutor
from utils.parser import LinkParser

async def main():
    link = "vless://2420af47-2316-482e-bb0f-b164df4b2334@84.201.159.228:443?flow=xtls-rprx-vision&encryption=none&type=tcp&security=reality&fp=chrome&sni=ads.x5.ru&pbk=1vSZjvhZO01oAEH3b7eebR1qF5dLU1Dq2E7xu8pwGSs&sid=428ef87fd47a3a32#Albania"
    process, port, config_path = await XrayExecutor.start_xray(link)
    print("Direct start:", process, port)
    
    if process:
        try:
            from utils.checker.service import check_connectivity
            ok, lat, err = await check_connectivity(port)
            print("Direct connect:", ok, lat, err)
        finally:
            await XrayExecutor.cleanup(process, config_path)
            
    # Now with proxy
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

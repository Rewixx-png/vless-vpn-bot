import asyncio
from utils.checker.xray import XrayExecutor
from utils.parser import LinkParser
import time

async def main():
    link = 'vless://5074df4a-1b57-4417-9f9c-d055b420a6f3@158.160.114.71:443?flow=xtls-rprx-vision\u0026encryption=none\u0026type=tcp\u0026security=reality\u0026fp=qq\u0026sni=sso.passport.yandex.ru\u0026pbk=1vSZjvhZO01oAEH3b7eebR1qF5dLU1Dq2E7xu8pwGSs\u0026sid=428ef87fd47a3a32'
    parsed = LinkParser.parse_vless(link)
    
    local_port = 10811
    cfg = XrayExecutor._generate_config(parsed, local_port, upstream_proxy={'scheme': 'socks5', 'host': '127.0.0.1', 'port': 19080})
    
    import json
    with open('test_xray_config.json', 'w') as f:
        json.dump(cfg, f)
        
    process = await asyncio.create_subprocess_exec(
        XrayExecutor.XRAY_BIN, "-c", "test_xray_config.json",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    
    try:
        await asyncio.wait_for(process.wait(), timeout=0.5)
        stdout, stderr = await process.communicate()
        print("CRASHED EARLY!")
        print("STDOUT:", stdout.decode())
        print("STDERR:", stderr.decode())
        print("Return code:", process.returncode)
    except asyncio.TimeoutError:
        print("DID NOT CRASH EARLY!")
        process.kill()

asyncio.run(main())

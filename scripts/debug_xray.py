import asyncio
from utils.checker.xray import XrayExecutor
from utils.parser import LinkParser

async def main():
    link = "vless://2420af47-2316-482e-bb0f-b164df4b2334@84.201.159.228:443?flow=xtls-rprx-vision&encryption=none&type=tcp&security=reality&fp=chrome&sni=ads.x5.ru&pbk=1vSZjvhZO01oAEH3b7eebR1qF5dLU1Dq2E7xu8pwGSs&sid=428ef87fd47a3a32#Albania"
    upstream = {'scheme': 'socks5', 'host': '127.0.0.1', 'port': 19080}
    
    parsed = LinkParser.parse_vless(link)
    cfg = XrayExecutor._generate_config(parsed, 10811, upstream_proxy=upstream)
    import json
    with open('test_xray_config.json', 'w') as f:
        json.dump(cfg, f, indent=2)
        
    process = await asyncio.create_subprocess_exec(
        XrayExecutor.XRAY_BIN, "-c", "test_xray_config.json",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    stdout, stderr = await process.communicate()
    print("STDOUT:", stdout.decode())
    print("STDERR:", stderr.decode())

asyncio.run(main())

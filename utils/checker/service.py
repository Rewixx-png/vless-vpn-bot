import sys
import os
import gc
from pathlib import Path
import asyncio
import logging
import json
import time
import aiohttp
import subprocess
from aiohttp import web
from aiohttp_socks import ProxyConnector, ProxyError, ProxyConnectionError, ProxyTimeoutError

BASE_DIR = Path(__file__).resolve().parent.parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.append(str(BASE_DIR))

from utils.checker.xray import XrayExecutor
from utils.checker.geoip import GeoIP
from config import config

logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s - CHECKER - %(levelname)s - %(message)s"
)
logger = logging.getLogger("CheckerService")

MAX_CONCURRENT_CHECKS = 75
semaphore = asyncio.Semaphore(MAX_CONCURRENT_CHECKS)

PROBE_URLS = [
    "http://ip-api.com/json/?fields=countryCode,query",
    "https://ipwho.is/",
    "https://api.ip.sb/geoip",
    "https://ifconfig.co/json"
]

async def cleanup_zombie_xrays():
    while True:
        await asyncio.sleep(60)
        try:
            subprocess.run("ps -ef | grep 'xray_check_' | grep -v grep | awk '{print $2}' | xargs -r kill -9", shell=True, stderr=subprocess.DEVNULL)
            subprocess.run("find /tmp -name 'xray_check_*.json' -mmin +2 -delete 2>/dev/null", shell=True)
            gc.collect()
        except Exception:
            pass

async def probe_proxy(connector: ProxyConnector) -> dict:
    timeout = aiohttp.ClientTimeout(total=8.0, connect=5.0, sock_read=5.0)
    
    result = {
        "success": False,
        "region": "🌍 UNK",
        "latency": 9999,
        "ip": None,
        "error": None
    }

    async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
        for url in PROBE_URLS[:2]:
            try:
                start_time = time.monotonic()
                async with session.get(url, allow_redirects=True) as response:
                    if response.status == 200:
                        latency = int((time.monotonic() - start_time) * 1000)
                        
                        try:
                            data = await response.json(content_type=None)
                        except:
                            result["success"] = True
                            result["latency"] = latency
                            return result

                        code = None
                        ip = None
                        
                        if "countryCode" in data: code = data["countryCode"]
                        elif "country_code" in data: code = data["country_code"]
                        elif "country_iso" in data: code = data["country_iso"]
                        
                        if "query" in data: ip = data["query"]
                        elif "ip" in data: ip = data["ip"]

                        result["success"] = True
                        result["latency"] = latency
                        result["region"] = GeoIP.code_to_region(code) if code else "🌍 UNK"
                        result["ip"] = ip
                        
                        return result
                    
            except (asyncio.TimeoutError, ProxyTimeoutError):
                result["error"] = "Timeout"
            except (ProxyError, ProxyConnectionError, aiohttp.ClientConnectorError):
                result["error"] = "Connection Failed"
            except Exception as e:
                result["error"] = str(e)
    
    return result

async def check_ai_availability(connector: ProxyConnector) -> bool:
    timeout = aiohttp.ClientTimeout(total=3.0)
    try:
        async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
            async with session.get('https://api.openai.com/v1/models', allow_redirects=False) as resp:
                if resp.status in [200, 401, 403]:
                    return True
    except:
        pass
    return False

async def check_handler(request):
    try:
        data = await request.json()
    except:
        return web.json_response({"error": "Invalid JSON"}, status=400)
        
    config_url = data.get("config")
    if not config_url:
        return web.json_response({"error": "No config provided"}, status=400)

    try:
        await asyncio.wait_for(semaphore.acquire(), timeout=3.0)
    except asyncio.TimeoutError:
        return web.json_response({"error": "Service Busy"}, status=503)

    process = None
    config_path = None
    local_port = 0
    
    response_data = {
        "success": False,
        "region": "🌍 UNK",
        "latency": 9999,
        "speed_mbps": 0.0,
        "ai": False,
        "error": "Init"
    }

    try:
        process, local_port, config_path = await XrayExecutor.start_xray(config_url)
        
        if not process:
            response_data["error"] = config_path
            return web.json_response(response_data)

        connector = ProxyConnector.from_url(
            f"socks5://127.0.0.1:{local_port}", 
            rdns=True, 
            force_close=True,
            enable_cleanup_closed=True
        )

        probe_result = await probe_proxy(connector)
        
        if probe_result["success"]:
            response_data["success"] = True
            response_data["latency"] = probe_result["latency"]
            response_data["region"] = probe_result["region"]
            response_data["error"] = "OK"
            
            try:
                st_connector = ProxyConnector.from_url(f"socks5://127.0.0.1:{local_port}", rdns=True, force_close=True)
                async with aiohttp.ClientSession(connector=st_connector, timeout=aiohttp.ClientTimeout(total=15.0)) as st_session:
                    st_start = time.monotonic()
                    async with st_session.get('http://speed.cloudflare.com/__down?bytes=25000000') as resp:
                        if resp.status == 200:
                            content = await resp.read()
                            duration = time.monotonic() - st_start
                            if duration > 0.01:
                                speed = (len(content) * 8) / (duration * 1_000_000)
                                response_data["speed_mbps"] = round(speed, 2)
            except Exception:
                pass

            if response_data["speed_mbps"] > 1.0:
                 ai_connector = ProxyConnector.from_url(f"socks5://127.0.0.1:{local_port}", rdns=True, force_close=True)
                 response_data["ai"] = await check_ai_availability(ai_connector)

        else:
            response_data["error"] = probe_result.get("error", "Probe Failed")

    except Exception as e:
        response_data["error"] = str(e)
    finally:
        semaphore.release()
        await XrayExecutor.cleanup(process, config_path)

    return web.json_response(response_data)

async def health_check(request):
    return web.Response(text="OK")

def main():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    loop.run_until_complete(GeoIP.initialize())
    
    loop.create_task(cleanup_zombie_xrays())
    
    app = web.Application()
    app.router.add_post('/check', check_handler)
    app.router.add_get('/', health_check)
    
    print(f"🚀 Checker Service running on port {config.CHECKER_PORT}")
    web.run_app(app, port=config.CHECKER_PORT, print=None, access_log=None)

if __name__ == "__main__":
    if os.name == 'nt':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    main()

import sys
import os
import gc
import asyncio
import logging
import multiprocessing
import resource
from pathlib import Path
from aiohttp import web
from aiohttp_socks import ProxyConnector, ProxyError, ProxyConnectionError, ProxyTimeoutError
import subprocess
import time

from gunicorn.app.base import BaseApplication

BASE_DIR = Path(__file__).resolve().parent.parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.append(str(BASE_DIR))

from utils.checker.xray import XrayExecutor
from utils.checker.geo_ip import GeoIP
from config import config

try:
    soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
    resource.setrlimit(resource.RLIMIT_NOFILE, (hard, hard))
except Exception:
    pass

logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s - CHECKER - %(levelname)s - %(message)s"
)
logger = logging.getLogger("CheckerService")

MAX_CONCURRENT_CHECKS_PER_WORKER = 25
semaphore = asyncio.Semaphore(MAX_CONCURRENT_CHECKS_PER_WORKER)

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
            subprocess.run("find /tmp -name 'xray_*.json' -mmin +5 -delete 2>/dev/null", shell=True)
            gc.collect()
        except Exception:
            pass

async def probe_proxy(connector: ProxyConnector) -> dict:
    timeout = aiohttp.ClientTimeout(total=8.0, connect=4.0, sock_read=4.0)
    
    result = {
        "success": False,
        "region": "🌍 UNK",
        "latency": 9999,
        "ip": None,
        "error": None
    }

    async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
        url = PROBE_URLS[0]
        try:
            start_time = time.monotonic()
            async with session.get(url, allow_redirects=True) as response:
                if response.status == 200:
                    latency = int((time.monotonic() - start_time) * 1000)
                    
                    try:
                        data = await response.json(content_type=None)
                    except Exception:
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
    timeout = aiohttp.ClientTimeout(total=4.0)
    try:
        async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
            async with session.get('https://api.openai.com/v1/models', allow_redirects=False) as resp:
                if resp.status in [200, 401, 403]:
                    return True
    except Exception:
        pass
    return False

async def check_handler(request):
    try:
        data = await request.json()
    except Exception:
        return web.json_response({"error": "Invalid JSON"}, status=400)
        
    config_url = data.get("config")
    if not config_url:
        return web.json_response({"error": "No config provided"}, status=400)

    try:
        await asyncio.wait_for(semaphore.acquire(), timeout=10.0)
    except asyncio.TimeoutError:
        return web.json_response({"error": "SYS_ERR: Worker Busy"}, status=503)

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
            response_data["error"] = f"SYS_ERR: {config_path}"
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
                async with aiohttp.ClientSession(connector=st_connector, timeout=aiohttp.ClientTimeout(total=10.0)) as st_session:
                    st_start = time.monotonic()
                    async with st_session.get('http://speed.cloudflare.com/__down?bytes=10000000') as resp:
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

async def app_factory():
    await GeoIP.initialize()
    app = web.Application()
    app.router.add_post('/check', check_handler)
    app.router.add_get('/', health_check)
    
    asyncio.create_task(cleanup_zombie_xrays())
    return app

class GunicornApp(BaseApplication):
    def __init__(self, options=None):
        self.options = options or {}
        super().__init__()

    def load_config(self):
        for key, value in self.options.items():
            if key in self.cfg.settings and value is not None:
                self.cfg.set(key.lower(), value)

    def load(self):
        return app_factory

def main():
    workers = multiprocessing.cpu_count()
    if workers > 8: workers = 8
    
    options = {
        'bind': f'0.0.0.0:{config.CHECKER_PORT}',
        'workers': workers,
        'worker_class': 'aiohttp.GunicornWebWorker',
        'timeout': 60,
        'keepalive': 5,
        'loglevel': 'warning',
        'accesslog': None,
        'errorlog': '-'
    }
    
    GunicornApp(options).run()

if __name__ == "__main__":
    if os.name == 'nt':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(GeoIP.initialize())
        app = web.Application()
        app.router.add_post('/check', check_handler)
        web.run_app(app, port=config.CHECKER_PORT)
    else:
        main()

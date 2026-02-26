import sys
import os
import gc
import asyncio
import logging
import multiprocessing
import resource
from pathlib import Path
import aiohttp
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
    from settings import CHECKER_SETTINGS
except ImportError:
    CHECKER_SETTINGS = {
        "max_concurrent": 80,
        "timeout": 10,
        "connect_timeout": 3,
        "workers": 8,
    }

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

MAX_CONCURRENT_CHECKS_PER_WORKER = CHECKER_SETTINGS.get("max_concurrent", 80)
semaphore = asyncio.Semaphore(MAX_CONCURRENT_CHECKS_PER_WORKER)

PROBE_URLS = [
    "https://api.ip.sb/geoip",
    "https://ipwho.is/",
    "http://ip-api.com/json/?fields=countryCode,query",
]

def custom_exception_handler(loop, context):
    msg = context.get("message", "")
    if "Task was destroyed but it is pending" in str(msg):
        return
    loop.default_exception_handler(context)

async def cleanup_zombie_xrays():
    try:
        while True:
            await asyncio.sleep(30)
            try:
                XrayExecutor.cleanup_zombies()
                proc = await asyncio.create_subprocess_shell(
                    "find /tmp -name 'xray_*.json' -mmin +2 -delete 2>/dev/null",
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.DEVNULL
                )
                await proc.wait()
                gc.collect()
            except Exception:
                pass
    except asyncio.CancelledError:
        pass

async def probe_proxy(connector: ProxyConnector) -> dict:
    timeout = aiohttp.ClientTimeout(total=5.0, connect=2.0, sock_read=2.0)
    
    result = {
        "success": False,
        "region": "🌍 UNK",
        "latency": 9999,
        "ip": None,
        "error": "Failed"
    }

    async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
        for url in PROBE_URLS:
            try:
                start_time = time.monotonic()
                async with session.get(url, allow_redirects=True) as response:
                    latency = int((time.monotonic() - start_time) * 1000)
                    
                    result["success"] = True
                    result["latency"] = min(result["latency"], latency)
                    
                    if response.status == 200:
                        try:
                            data = await response.json(content_type=None)
                            code = data.get("countryCode") or data.get("country_code") or data.get("country_iso")
                            ip = data.get("query") or data.get("ip")
                            
                            if code:
                                result["region"] = GeoIP.code_to_region(code)
                            if ip:
                                result["ip"] = ip
                                
                            result["error"] = "OK"
                            return result
                        except Exception:
                            result["error"] = "Invalid JSON"
                    else:
                        result["error"] = f"HTTP {response.status}"
            except (asyncio.TimeoutError, ProxyTimeoutError):
                if result["error"] == "Failed": result["error"] = "Timeout"
            except (ProxyError, ProxyConnectionError, aiohttp.ClientConnectorError):
                if result["error"] == "Failed": result["error"] = "Connection Failed"
            except Exception as e:
                if result["error"] == "Failed": result["error"] = str(e)
    
    return result

async def check_ai_availability(connector: ProxyConnector) -> bool:
    timeout = aiohttp.ClientTimeout(total=3.0)
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
        # Увеличиваем время ожидания очереди, так как семафор маленький
        await asyncio.wait_for(semaphore.acquire(), timeout=30.0)
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
            
            if probe_result["region"] != "🌍 UNK":
                response_data["region"] = probe_result["region"]
                
            response_data["error"] = probe_result.get("error", "OK")
            
            # Облегченный спидтест (1МБ), только если пинг < 1500мс
            if response_data["latency"] < 1500:
                try:
                    st_connector = ProxyConnector.from_url(f"socks5://127.0.0.1:{local_port}", rdns=True, force_close=True)
                    async with aiohttp.ClientSession(connector=st_connector, timeout=aiohttp.ClientTimeout(total=3.0)) as st_session:
                        st_start = time.monotonic()
                        async with st_session.get('http://speed.cloudflare.com/__down?bytes=1000000') as resp:
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

async def start_background_tasks(app):
    loop = asyncio.get_running_loop()
    loop.set_exception_handler(custom_exception_handler)
    app['cleanup_task'] = asyncio.create_task(cleanup_zombie_xrays())

async def cleanup_background_tasks(app):
    task = app.get('cleanup_task')
    if task and not task.done():
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

async def app_factory():
    await GeoIP.initialize()
    app = web.Application()
    app.router.add_post('/check', check_handler)
    app.router.add_get('/', health_check)
    
    app.on_startup.append(start_background_tasks)
    app.on_cleanup.append(cleanup_background_tasks)
    
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
        'timeout': 120,
        'graceful_timeout': 30,
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
        app.on_startup.append(start_background_tasks)
        app.on_cleanup.append(cleanup_background_tasks)
        web.run_app(app, port=config.CHECKER_PORT)
    else:
        main()

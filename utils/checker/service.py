import sys
import os
import gc
import asyncio
import resource
import time
from pathlib import Path

if 'uvloop' in sys.modules:
    del sys.modules['uvloop']
asyncio.set_event_loop_policy(asyncio.DefaultEventLoopPolicy())

import aiohttp
from aiohttp import web
from aiohttp_socks import ProxyConnector
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
        "timeout": 8,
        "connect_timeout": 3,
        "workers": 2,
    }

try:
    soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
    resource.setrlimit(resource.RLIMIT_NOFILE, (hard, hard))
except Exception:
    pass

def custom_exception_handler(loop, context):
    msg = context.get("message", "")
    if "Task was destroyed but it is pending" in str(msg):
        return
    if "Unknown child process pid" in str(msg):
        return
    loop.default_exception_handler(context)

async def cleanup_zombie_xrays():
    try:
        tmp_dir = Path("/tmp")
        while True:
            await asyncio.sleep(30)
            try:
                XrayExecutor.cleanup_zombies()
                
                current_time = time.time()
                for file_path in tmp_dir.glob("xray_*.json"):
                    try:
                        if file_path.is_file():
                            mtime = file_path.stat().st_mtime
                            if current_time - mtime > 120:
                                file_path.unlink()
                    except Exception:
                        pass
                
                gc.collect()
            except Exception:
                pass
    except asyncio.CancelledError:
        pass

async def check_connectivity(connector: ProxyConnector) -> tuple[bool, int, str]:
    timeout = aiohttp.ClientTimeout(total=8.0, connect=4.0, sock_read=4.0)
    
    CHECK_URLS = [
        ("http://cp.cloudflare.com/generate_204", 204),
        ("http://www.gstatic.com/generate_204", 204),
        ("http://connectivitycheck.gstatic.com/generate_204", 204),
    ]
    
    try:
        async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
            start_time = time.monotonic()
            
            success = False
            last_error = ""
            for url, expected_status in CHECK_URLS:
                try:
                    async with session.get(url, allow_redirects=False) as response:
                        if response.status == expected_status:
                            success = True
                            break
                        last_error = f"HTTP {response.status}"
                except Exception as e:
                    last_error = str(e)
                    continue
            
            if not success:
                return False, 9999, f"Factor 4: Connectivity Failed ({last_error})"
            
            latency = int((time.monotonic() - start_time) * 1000)
            return True, latency, "OK"
                    
    except asyncio.TimeoutError:
        return False, 9999, "Factor 4: HTTP Timeout"
    except Exception as e:
        return False, 9999, f"Factor 4/5: {str(e)}"

async def probe_geoip(connector: ProxyConnector) -> dict:
    timeout = aiohttp.ClientTimeout(total=5.0, connect=3.0)
    result = {"region": "🌍 UNK", "ip": None}
    
    GEO_PROBES =[
        "https://api.ip.sb/geoip",
        "https://ipwho.is/",
        "http://ip-api.com/json/?fields=countryCode,query",
    ]

    async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
        for url in GEO_PROBES:
            try:
                async with session.get(url, allow_redirects=True) as response:
                    if response.status == 200:
                        data = await response.json(content_type=None)
                        code = data.get("countryCode") or data.get("country_code") or data.get("country_iso")
                        ip = data.get("query") or data.get("ip")
                        if code: result["region"] = GeoIP.code_to_region(code)
                        if ip: result["ip"] = ip
                        return result
            except:
                continue
    return result

async def check_ai_availability(connector: ProxyConnector) -> bool:
    timeout = aiohttp.ClientTimeout(total=5.0)
    openai_ok = False
    google_ok = False
    
    try:
        async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
            try:
                async with session.get('https://api.openai.com/v1/models', allow_redirects=False) as resp:
                    if resp.status in[200, 401, 403]:
                        openai_ok = True
            except:
                pass
                
            try:
                async with session.get('https://gemini.google.com/app', allow_redirects=True) as resp:
                    if resp.status in[200, 302]:
                        google_ok = True
            except:
                pass
                
            if not google_ok:
                try:
                    async with session.get('https://generativelanguage.googleapis.com/v1beta/models', allow_redirects=False) as resp:
                        if resp.status in[200, 400, 401, 403, 404]:
                            google_ok = True
                except:
                    pass

    except:
        pass
        
    return openai_ok and google_ok

async def check_handler(request):
    try: data = await request.json()
    except: return web.json_response({"error": "Invalid JSON"}, status=400)
        
    config_url = data.get("config")
    if not config_url: return web.json_response({"error": "No config provided"}, status=400)

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

        connector_strict = ProxyConnector.from_url(
            f"socks5://127.0.0.1:{local_port}", rdns=True, force_close=True, enable_cleanup_closed=True
        )
        
        is_alive, latency, error_msg = await check_connectivity(connector_strict)
        
        if is_alive:
            response_data["success"] = True
            response_data["latency"] = latency
            response_data["error"] = "OK"
            
            connector_geo = ProxyConnector.from_url(f"socks5://127.0.0.1:{local_port}", rdns=True, force_close=True)
            geo_info = await probe_geoip(connector_geo)
            response_data["region"] = geo_info["region"]
            
            if latency < 1200:
                connector_ai = ProxyConnector.from_url(f"socks5://127.0.0.1:{local_port}", rdns=True, force_close=True)
                response_data["ai"] = await check_ai_availability(connector_ai)
                
                try:
                    connector_speed = ProxyConnector.from_url(f"socks5://127.0.0.1:{local_port}", rdns=True, force_close=True)
                    async with aiohttp.ClientSession(connector=connector_speed, timeout=aiohttp.ClientTimeout(total=5.0)) as st_session:
                        st_start = time.monotonic()
                        
                        async def download_worker():
                            down_bytes = 0
                            first_byte = None
                            try:
                                async with st_session.get('https://speed.cloudflare.com/__down?bytes=15000000') as resp:
                                    if resp.status == 200:
                                        while True:
                                            chunk = await resp.content.read(65536)
                                            if not chunk: break
                                            if first_byte is None: first_byte = time.monotonic()
                                            down_bytes += len(chunk)
                                            if time.monotonic() - st_start > 2.5: break
                            except: pass
                            return down_bytes, first_byte

                        workers =[asyncio.create_task(download_worker()) for _ in range(3)]
                        results = await asyncio.gather(*workers)
                        
                        total_down = 0
                        earliest_fb = None
                        
                        for down, fb in results:
                            total_down += down
                            if fb is not None:
                                if earliest_fb is None or fb < earliest_fb:
                                    earliest_fb = fb
                        
                        if earliest_fb is not None and total_down > 0:
                            duration = time.monotonic() - earliest_fb
                            if duration > 0.05:
                                response_data["speed_mbps"] = round((total_down * 8) / (duration * 1_000_000), 2)
                except: pass
        else:
            response_data["error"] = error_msg

    except Exception as e:
        response_data["error"] = str(e)
    finally:
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
        try: await task
        except: pass

def app_factory():
    loop = asyncio.get_event_loop()
    loop.run_until_complete(GeoIP.initialize())
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
        return app_factory()

def main():
    workers = CHECKER_SETTINGS.get("workers", 2)
    GunicornApp({
        'bind': f'0.0.0.0:{config.CHECKER_PORT}',
        'workers': workers,
        'worker_class': 'aiohttp.GunicornWebWorker',
        'timeout': 120,
        'graceful_timeout': 30,
        'keepalive': 5,
        'loglevel': 'warning',
        'accesslog': None,
        'errorlog': '-'
    }).run()

if __name__ == "__main__":
    if os.name == 'nt':
        pass
    else:
        main()

import sys
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.append(str(BASE_DIR))

import asyncio
import logging
import json
import time
import aiohttp
from aiohttp import web
from aiohttp_socks import ProxyConnector

from utils.checker.xray import XrayExecutor
from utils.checker.geoip import GeoIP
from config import config

logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s - CHECKER_SVC - %(levelname)s - %(message)s"
)
logger = logging.getLogger("CheckerService")

MAX_CONCURRENT_CHECKS = 50
semaphore = asyncio.Semaphore(MAX_CONCURRENT_CHECKS)

async def check_handler(request):
    try:
        data = await request.json()
        config_url = data.get("config")
        
        if not config_url:
            return web.json_response({"error": "No config provided"}, status=400)

        async with semaphore:
            process, local_port, config_path = await XrayExecutor.start_xray(config_url)
            
            if not process:
                return web.json_response({
                    "success": False,
                    "error": config_path
                })

            connector = ProxyConnector.from_url(f"socks5://127.0.0.1:{local_port}")
            timeout = aiohttp.ClientTimeout(total=6.0, connect=3.0)
            
            result = {
                "success": False,
                "region": "🌍 UNK",
                "latency": 9999,
                "ai": False,
                "error": "OK"
            }

            try:
                async with aiohttp.ClientSession(connector=connector, timeout=timeout) as proxy_session:
                    start_time = time.monotonic()
                    
                    http_ok = False
                    try:
                        async with proxy_session.get('http://cp.cloudflare.com/generate_204', allow_redirects=False) as resp:
                            if resp.status == 204:
                                http_ok = True
                    except Exception:
                        pass

                    if not http_ok:
                        raise Exception("HTTP Ping Failed")

                    https_ok = False
                    try:
                        async with proxy_session.get('https://www.gstatic.com/generate_204', allow_redirects=False) as resp:
                            if resp.status == 204:
                                # Замеряем пинг только по успешному HTTPS
                                result["latency"] = int((time.monotonic() - start_time) * 1000)
                                https_ok = True
                            else:
                                raise Exception(f"HTTPS Status {resp.status}")
                    except Exception as e:
                        raise Exception(f"HTTPS SSL Failed: {e}")

                    if https_ok:
                        result["success"] = True
                        
                        if result["latency"] < 2000:
                            try:
                                ai_timeout = aiohttp.ClientTimeout(total=2.0)
                                openai_ok = False
                                async with proxy_session.get('https://api.openai.com/v1/models', timeout=ai_timeout) as ai_resp:
                                    if ai_resp.status in [200, 401, 403]:
                                        openai_ok = True
                                
                                gemini_ok = False
                                if openai_ok:
                                    async with proxy_session.get('https://generativelanguage.googleapis.com/v1beta/models?key=INVALID_KEY', timeout=ai_timeout) as gem_resp:
                                        if gem_resp.status in [400, 403, 200]: 
                                            gemini_ok = True

                                if openai_ok and gemini_ok:
                                    result["ai"] = True
                            except: pass

                            result["region"] = await GeoIP.identify_region(proxy_session)

            except Exception as e:
                result["error"] = str(e)
            finally:
                XrayExecutor.cleanup(process, config_path)

            return web.json_response(result)

    except Exception as e:
        logger.error(f"Handler error: {e}")
        return web.json_response({"error": str(e)}, status=500)

async def health_check(request):
    return web.Response(text="OK")

def main():
    app = web.Application()
    app.router.add_post('/check', check_handler)
    app.router.add_get('/', health_check)
    
    print(f"🚀 Checker Service running on port {config.CHECKER_PORT} with limit {MAX_CONCURRENT_CHECKS}")
    web.run_app(app, port=config.CHECKER_PORT, print=None)

if __name__ == "__main__":
    try:
        if os.name == 'nt':
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        main()
    except KeyboardInterrupt:
        pass
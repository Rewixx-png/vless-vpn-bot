import sys
import os
import gc
from pathlib import Path

# Fix imports
BASE_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.append(str(BASE_DIR))

import asyncio
import logging
import json
import time
import aiohttp
import subprocess
from aiohttp import web
from aiohttp_socks import ProxyConnector

from utils.checker.xray import XrayExecutor
from utils.checker.geoip import GeoIP
from config import config
try:
    from utils.parser import LinkParser
except ImportError:
    sys.path.append(str(BASE_DIR))
    from utils.parser import LinkParser

# Logging setup
logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s - CHECKER_SVC - %(levelname)s - %(message)s"
)
logging.getLogger("aiohttp.server").setLevel(logging.ERROR)
logging.getLogger("aiohttp.access").setLevel(logging.ERROR)

logger = logging.getLogger("CheckerService")

# Увеличиваем лимит, так как теперь есть жесткие таймауты
MAX_CONCURRENT_CHECKS = 100
semaphore = asyncio.Semaphore(MAX_CONCURRENT_CHECKS)

async def cleanup_zombie_xrays():
    """Aggressive cleanup of stuck processes and temp files"""
    while True:
        await asyncio.sleep(30)
        try:
            # Clean old config files
            subprocess.run("find /tmp -name 'xray_check_*.json' -mmin +2 -delete 2>/dev/null", shell=True)
            # Force GC to free up file descriptors/sockets
            gc.collect()
        except Exception:
            pass

async def check_handler(request):
    try:
        try:
            data = await request.json()
        except:
            return web.json_response({"error": "Invalid JSON"}, status=400)
            
        config_url = data.get("config")
        
        if not config_url:
            return web.json_response({"error": "No config provided"}, status=400)

        # Semaphore acquisition with timeout to prevent infinite stacking
        try:
            await asyncio.wait_for(semaphore.acquire(), timeout=5.0)
        except asyncio.TimeoutError:
            return web.json_response({"error": "Service Busy (Semaphore Timeout)"}, status=503)

        try:
            process, local_port, config_path = await XrayExecutor.start_xray(config_url)
            
            if not process:
                return web.json_response({
                    "success": False,
                    "error": config_path or "Start Failed"
                })

            # Force close connections after use to prevent TIME_WAIT accumulation
            connector = ProxyConnector.from_url(f"socks5://127.0.0.1:{local_port}", force_close=True)
            
            # Strict timeouts
            timeout = aiohttp.ClientTimeout(total=15.0, connect=4.0)
            
            result = {
                "success": False,
                "region": "🌍 UNK",
                "latency": 9999,
                "speed_mbps": 0.0,
                "ai": False,
                "error": "OK"
            }

            try:
                async with aiohttp.ClientSession(connector=connector, timeout=timeout) as proxy_session:
                    start_time = time.monotonic()
                    
                    # 1. HTTP PING
                    http_ok = False
                    try:
                        async with proxy_session.get('http://cp.cloudflare.com/generate_204', allow_redirects=False) as resp:
                            if resp.status in [200, 201, 204, 301, 302]:
                                http_ok = True
                    except Exception:
                        pass

                    if not http_ok:
                        raise Exception("HTTP Ping Failed")

                    # 2. HTTPS HANDSHAKE
                    https_ok = False
                    try:
                        async with proxy_session.get('https://www.gstatic.com/generate_204', allow_redirects=False) as resp:
                            if resp.status in [200, 204]:
                                result["latency"] = int((time.monotonic() - start_time) * 1000)
                                https_ok = True
                            else:
                                raise Exception(f"HTTPS Status {resp.status}")
                    except Exception as e:
                        raise Exception(f"HTTPS SSL Failed: {e}")

                    if https_ok:
                        # 3. SPEEDTEST (Small file)
                        speed_mbps = 0.0
                        try:
                            st_start = time.monotonic()
                            async with proxy_session.get('http://speed.cloudflare.com/__down?bytes=100000', timeout=aiohttp.ClientTimeout(total=5.0)) as st_resp:
                                if st_resp.status == 200:
                                    content = await st_resp.read()
                                    duration = time.monotonic() - st_start
                                    if duration > 0:
                                        speed_mbps = round((len(content) * 8) / (duration * 1000000), 2)
                        except Exception:
                            pass
                        
                        result["speed_mbps"] = speed_mbps
                        result["success"] = True
                        
                        # 4. GEOIP
                        try:
                            region = await GeoIP.identify_region(proxy_session)
                            
                            # Fallback if UNK
                            if "Unk" in region:
                                parsed = LinkParser.parse_vless(config_url)
                                if parsed:
                                    host = parsed.get("host") or parsed.get("server") or parsed.get("sni")
                                    remark = parsed.get("ps", "")
                                    if host:
                                        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=3)) as direct_session:
                                            region = await GeoIP.identify_region(direct_session, host=host, remark=remark)

                            result["region"] = region
                        except Exception as e:
                            logger.error(f"GeoIP Error: {e}")
                            result["region"] = "🌍 UNK"
                        
                        # 5. AI CHECK
                        if speed_mbps > 0.5:
                            try:
                                ai_timeout = aiohttp.ClientTimeout(total=2.0)
                                openai_ok = False
                                async with proxy_session.get('https://api.openai.com/v1/models', timeout=ai_timeout) as ai_resp:
                                    if ai_resp.status in [200, 401, 403]:
                                        openai_ok = True
                                
                                gemini_ok = False
                                if openai_ok:
                                    async with proxy_session.get('https://generativelanguage.googleapis.com/v1beta/models?key=INVALID_KEY', timeout=ai_timeout) as gem_resp:
                                        if gem_resp.status in [200, 400, 403]: 
                                            gemini_ok = True

                                if openai_ok and gemini_ok:
                                    result["ai"] = True
                            except: pass

            except Exception as e:
                result["error"] = str(e)
            finally:
                # Ensure process death
                await XrayExecutor.cleanup(process, config_path)

            return web.json_response(result)
        
        finally:
            # ALWAYS release semaphore
            semaphore.release()

    except Exception as e:
        logger.error(f"Critical Service Error: {e}", exc_info=True)
        return web.json_response({"error": str(e)}, status=500)

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
    
    print(f"🚀 Checker Service running on port {config.CHECKER_PORT} with limit {MAX_CONCURRENT_CHECKS}")
    web.run_app(app, port=config.CHECKER_PORT, print=None)

if __name__ == "__main__":
    import sys
    # Auto-restart loop inside python to avoid pm2 lag
    while True:
        try:
            if os.name == 'nt':
                asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
            main()
        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"❌ Error: {e}")
            time.sleep(1)

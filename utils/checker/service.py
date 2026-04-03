import sys
import os
import gc
import asyncio
import resource
import time
from pathlib import Path

if "uvloop" in sys.modules:
    del sys.modules["uvloop"]
asyncio.set_event_loop_policy(asyncio.DefaultEventLoopPolicy())

import aiohttp
from aiohttp import web
from aiohttp_socks import ProxyConnector
from gunicorn.app.base import BaseApplication
import redis.asyncio as redis

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

_redis_pool = None


async def get_redis_pool():
    global _redis_pool
    if _redis_pool is None:
        try:
            _redis_pool = redis.from_url(config.REDIS_URL)
        except Exception:
            pass
    return _redis_pool


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
                XrayExecutor.cleanup_zombies(max_age_sec=300)

                current_time = time.time()
                for file_path in tmp_dir.glob("xray_*.json"):
                    try:
                        if file_path.is_file():
                            mtime = file_path.stat().st_mtime
                            if current_time - mtime > 300:
                                file_path.unlink()
                    except Exception:
                        pass

                gc.collect()
            except Exception:
                pass
    except asyncio.CancelledError:
        pass


async def check_connectivity(local_port: int) -> tuple[bool, int, str]:
    timeout = aiohttp.ClientTimeout(
        total=config.CONNECTIVITY_TIMEOUT, connect=4.0, sock_read=4.0
    )

    primary_url = "http://cp.cloudflare.com/"

    connector = ProxyConnector.from_url(f"socks5://127.0.0.1:{local_port}", rdns=True)
    try:
        async with aiohttp.ClientSession(
            connector=connector, timeout=timeout
        ) as session:
            start_time = time.monotonic()

            async with session.get(primary_url, allow_redirects=True) as response:
                if 100 <= response.status < 500:
                    latency = int((time.monotonic() - start_time) * 1000)
                    return True, latency, "OK"
                return False, 9999, f"Factor 4: HTTP {response.status}"

    except asyncio.TimeoutError:
        return False, 9999, "Factor 4: HTTP Timeout"
    except Exception as e:
        return False, 9999, f"Factor 4: Connectivity Failed ({str(e)})"


async def probe_geoip(local_port: int) -> dict:
    timeout = aiohttp.ClientTimeout(total=5.0, connect=3.0)
    result = {"region": "🌍 UNK", "ip": None}

    GEO_PROBES = [
        "https://api.ip.sb/geoip",
        "https://ipwho.is/",
        "http://ip-api.com/json/?fields=countryCode,query",
    ]

    connector = ProxyConnector.from_url(f"socks5://127.0.0.1:{local_port}", rdns=True)
    try:
        async with aiohttp.ClientSession(
            connector=connector, timeout=timeout
        ) as session:
            for url in GEO_PROBES:
                try:
                    async with session.get(url, allow_redirects=True) as response:
                        if response.status == 200:
                            data = await response.json(content_type=None)
                            code = (
                                data.get("countryCode")
                                or data.get("country_code")
                                or data.get("country_iso")
                            )
                            ip = data.get("query") or data.get("ip")
                            if code:
                                result["region"] = GeoIP.code_to_region(code)
                            if ip:
                                result["ip"] = ip
                            return result
                except:
                    continue
    except:
        pass
    return result


async def check_ai_availability(local_port: int) -> bool:
    timeout = aiohttp.ClientTimeout(total=5.0)
    openai_ok = False
    google_ok = False

    connector = ProxyConnector.from_url(f"socks5://127.0.0.1:{local_port}", rdns=True)
    try:
        async with aiohttp.ClientSession(
            connector=connector, timeout=timeout
        ) as session:
            try:
                async with session.get(
                    "https://api.openai.com/v1/models", allow_redirects=False
                ) as resp:
                    if resp.status in [200, 401, 403]:
                        openai_ok = True
            except:
                pass

            try:
                async with session.get(
                    "https://gemini.google.com/app", allow_redirects=True
                ) as resp:
                    if resp.status in [200, 302]:
                        google_ok = True
            except:
                pass

            if not google_ok:
                try:
                    async with session.get(
                        "https://generativelanguage.googleapis.com/v1beta/models",
                        allow_redirects=False,
                    ) as resp:
                        if resp.status in [200, 400, 401, 403, 404]:
                            google_ok = True
                except:
                    pass
    except:
        pass

    return openai_ok and google_ok


async def check_no_ads(local_port: int) -> bool:
    timeout = aiohttp.ClientTimeout(total=4.0, connect=2.0)
    ad_domains = [
        "https://googleads.g.doubleclick.net/",
        "https://pagead2.googlesyndication.com/",
        "https://adservice.google.com/",
    ]
    fails = 0
    connector = ProxyConnector.from_url(f"socks5://127.0.0.1:{local_port}", rdns=True)
    try:
        async with aiohttp.ClientSession(
            connector=connector, timeout=timeout
        ) as session:
            for domain in ad_domains:
                try:
                    async with session.get(domain, allow_redirects=False) as resp:
                        if resp.status in [200, 301, 302, 400, 403, 404]:
                            return False
                except Exception:
                    fails += 1
    except Exception:
        fails = len(ad_domains)

    return fails == len(ad_domains)


def _pick_representative_speed(samples: list[float]) -> float:
    clean_samples = [float(v) for v in samples if float(v) > 0.0]
    if not clean_samples:
        return 0.0

    clean_samples.sort()
    count = len(clean_samples)

    if count >= 3:
        return clean_samples[count // 2]
    if count == 2:
        return (clean_samples[0] + clean_samples[1]) / 2.0
    return clean_samples[0]


async def _measure_speed_sample(
    session: aiohttp.ClientSession,
    url: str,
    per_url_timeout: float,
    max_bytes: int,
) -> float:
    started = time.monotonic()
    downloaded = 0

    try:
        async with session.get(url, allow_redirects=True) as response:
            if response.status != 200:
                return 0.0

            while downloaded < max_bytes:
                if (time.monotonic() - started) >= per_url_timeout:
                    break

                try:
                    chunk = await asyncio.wait_for(response.content.read(262144), timeout=1.0)
                except asyncio.TimeoutError:
                    break

                if not chunk:
                    break
                downloaded += len(chunk)
    except Exception:
        return 0.0

    elapsed = time.monotonic() - started
    if downloaded < 262144 or elapsed <= 0.1:
        return 0.0

    return (downloaded * 8) / (elapsed * 1_000_000)


async def check_handler(request):
    try:
        data = await request.json()
    except:
        return web.json_response({"error": "Invalid JSON"}, status=400)

    config_url = data.get("config")
    if not config_url:
        return web.json_response({"error": "No config provided"}, status=400)

    process = None
    config_path = None
    local_port = 0

    response_data = {
        "success": False,
        "region": "🌍 UNK",
        "latency": 9999,
        "speed_mbps": 0.0,
        "ai": False,
        "no_ads": False,
        "error": "Init",
    }

    try:
        process, local_port, config_path = await XrayExecutor.start_xray(config_url)

        if not process:
            response_data["error"] = config_path
            return web.json_response(response_data)

        is_alive, latency, error_msg = await check_connectivity(local_port)

        if not is_alive:
            response_data["error"] = error_msg
            return web.json_response(response_data)

        response_data["success"] = True
        response_data["latency"] = latency
        response_data["error"] = "OK"

        geo_info = await probe_geoip(local_port)
        response_data["region"] = geo_info["region"]
        ip = geo_info.get("ip")

        r_client = await get_redis_pool()

        if latency < 1200:
            cached_ai = None
            cached_ads = None

            if ip and r_client:
                try:
                    keys = [f"chk:ai:{ip}", f"chk:ads:{ip}"]
                    vals = await r_client.mget(keys)
                    if vals[0] is not None:
                        cached_ai = vals[0].decode() == "1"
                    if vals[1] is not None:
                        cached_ads = vals[1].decode() == "1"
                except:
                    pass

            if cached_ai is not None:
                response_data["ai"] = cached_ai
            else:
                response_data["ai"] = await check_ai_availability(local_port)
                if ip and r_client:
                    try:
                        await r_client.setex(
                            f"chk:ai:{ip}",
                            3600,
                            "1" if response_data["ai"] else "0",
                        )
                    except:
                        pass

            if cached_ads is not None:
                response_data["no_ads"] = cached_ads
            else:
                response_data["no_ads"] = await check_no_ads(local_port)
                if ip and r_client:
                    try:
                        await r_client.setex(
                            f"chk:ads:{ip}",
                            3600,
                            "1" if response_data["no_ads"] else "0",
                        )
                    except:
                        pass

        SPEED_TEST_URLS = [
            "https://speed.cloudflare.com/__down?bytes=20000000",
            "https://speed.hetzner.de/10MB.bin",
            "https://ash-speed.hetzner.com/10MB.bin",
            "https://fsn1-speed.hetzner.com/10MB.bin",
        ]

        try:
            connector_speed = ProxyConnector.from_url(
                f"socks5://127.0.0.1:{local_port}", rdns=True
            )
            async with aiohttp.ClientSession(
                connector=connector_speed,
                timeout=aiohttp.ClientTimeout(
                    total=max(6.0, float(config.SPEED_TEST_TIMEOUT) + 3.0),
                    connect=3.0,
                ),
            ) as st_session:
                speed_samples = []
                per_url_timeout = max(2.0, float(config.SPEED_TEST_TIMEOUT))
                max_bytes_per_url = 20 * 1024 * 1024

                for test_url in SPEED_TEST_URLS:
                    sample = await _measure_speed_sample(
                        st_session,
                        test_url,
                        per_url_timeout=per_url_timeout,
                        max_bytes=max_bytes_per_url,
                    )
                    if sample > 0.0:
                        speed_samples.append(sample)

                representative = _pick_representative_speed(speed_samples)
                if representative > 0.0:
                    response_data["speed_mbps"] = round(representative, 2)

        except Exception:
            pass

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
    app["cleanup_task"] = asyncio.create_task(cleanup_zombie_xrays())


async def cleanup_background_tasks(app):
    task = app.get("cleanup_task")
    if task and not task.done():
        task.cancel()
        try:
            await task
        except:
            pass


def app_factory():
    loop = asyncio.get_event_loop()
    loop.run_until_complete(GeoIP.initialize())
    app = web.Application()
    app.router.add_post("/check", check_handler)
    app.router.add_get("/", health_check)
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
    app = app_factory()
    web.run_app(app, host="0.0.0.0", port=config.CHECKER_PORT, shutdown_timeout=10)


if __name__ == "__main__":
    if os.name == "nt":
        pass
    else:
        main()

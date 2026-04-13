import sys
import os
import gc
import asyncio
import resource
import time
import logging
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
from utils.checker.proxy_pool import ProxyPool, UpstreamProxy
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
logger = logging.getLogger("CheckerService")


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


async def refresh_proxy_pool_loop():
    try:
        await ProxyPool.refresh(force=True)
    except Exception as e:
        logger.warning(f"ProxyPool initial refresh failed: {e}")

    try:
        while True:
            await asyncio.sleep(max(60, int(getattr(ProxyPool, "REFRESH_INTERVAL_SEC", 300))))
            try:
                await ProxyPool.refresh(force=True)
            except Exception as e:
                logger.warning(f"ProxyPool periodic refresh failed: {e}")
    except asyncio.CancelledError:
        pass


async def check_connectivity(local_port: int) -> tuple[bool, int, str]:
    timeout_sec = max(3.0, min(float(config.CONNECTIVITY_TIMEOUT), 10.0))
    timeout = aiohttp.ClientTimeout(
        total=timeout_sec,
        connect=min(3.5, timeout_sec),
        sock_read=min(3.5, timeout_sec),
    )
    primary_url = "http://cp.cloudflare.com/generate_204"

    connector = ProxyConnector.from_url(f"socks5://127.0.0.1:{local_port}", rdns=True)
    try:
        async with aiohttp.ClientSession(
            connector=connector, timeout=timeout
        ) as session:
            start_time = time.monotonic()

            async with session.get(primary_url, allow_redirects=False) as response:
                if response.status in {200, 204}:
                    latency = int((time.monotonic() - start_time) * 1000)
                    return True, latency, "OK"
                return False, 9999, f"Factor 4: HTTP {response.status}"

    except asyncio.TimeoutError:
        return False, 9999, "Factor 4: HTTP Timeout"
    except Exception as e:
        return False, 9999, f"Factor 4: Connectivity Failed ({str(e)})"


def _is_reset_like_error(err: Exception) -> bool:
    if isinstance(err, ConnectionResetError):
        return True

    text = str(err or "").strip().lower()
    if not text:
        return False

    markers = (
        "connection reset",
        "reset by peer",
        "broken pipe",
        "connection aborted",
        "eof",
        "server disconnected",
    )
    return any(marker in text for marker in markers)


async def deep_traffic_test(local_port: int) -> tuple[bool, int, float, str]:
    required_bytes = 2 * 1024 * 1024
    test_url = "https://speed.cloudflare.com/__down?bytes=2000000"

    timeout = aiohttp.ClientTimeout(
        total=max(12.0, float(config.SPEED_TEST_TIMEOUT) + 7.0),
        connect=4.0,
        sock_read=6.0,
    )

    connector = ProxyConnector.from_url(f"socks5://127.0.0.1:{local_port}", rdns=True)

    started = time.monotonic()
    downloaded = 0

    try:
        async with aiohttp.ClientSession(
            connector=connector,
            timeout=timeout,
            cookie_jar=aiohttp.DummyCookieJar(),
        ) as session:
            async with session.get(test_url, allow_redirects=True) as response:
                if response.status != 200:
                    return False, 9999, 0.0, f"Factor 4: Deep HTTP {response.status}"

                while downloaded < required_bytes:
                    chunk = await asyncio.wait_for(
                        response.content.read(min(262144, required_bytes - downloaded)),
                        timeout=2.0,
                    )
                    if not chunk:
                        break
                    downloaded += len(chunk)

        elapsed = time.monotonic() - started
        if downloaded < required_bytes:
            return (
                False,
                9999,
                0.0,
                f"Factor 4: Deep Traffic Incomplete ({downloaded}/{required_bytes})",
            )

        if elapsed <= 0.05:
            return False, 9999, 0.0, "Factor 4: Deep Traffic Invalid Timing"

        speed_mbps = (downloaded * 8) / (elapsed * 1_000_000)
        latency_ms = max(1, int(elapsed * 1000))
        return True, latency_ms, max(1.0, round(speed_mbps, 2)), "OK"

    except asyncio.TimeoutError:
        return False, 9999, 0.0, "Factor 4: Deep Traffic Timeout"
    except Exception as e:
        if _is_reset_like_error(e):
            return False, 9999, 0.0, "Factor 4: Deep Traffic Reset"
        return False, 9999, 0.0, f"Factor 4: Deep Traffic Failed ({str(e)})"


async def quick_speed_probe(local_port: int) -> float:
    test_urls = [
        "https://speed.cloudflare.com/__down?bytes=1200000",
        "https://speed.cloudflare.com/__down?bytes=2000000",
    ]

    timeout = aiohttp.ClientTimeout(total=6.0, connect=3.0, sock_read=4.0)
    connector = ProxyConnector.from_url(f"socks5://127.0.0.1:{local_port}", rdns=True)

    best_speed = 0.0
    try:
        async with aiohttp.ClientSession(
            connector=connector,
            timeout=timeout,
            cookie_jar=aiohttp.DummyCookieJar(),
        ) as session:
            for url in test_urls:
                started = time.monotonic()
                downloaded = 0
                try:
                    async with session.get(url, allow_redirects=True) as response:
                        if response.status != 200:
                            continue

                        while downloaded < 1200000:
                            chunk = await asyncio.wait_for(
                                response.content.read(262144),
                                timeout=1.4,
                            )
                            if not chunk:
                                break
                            downloaded += len(chunk)

                    elapsed = time.monotonic() - started
                    if downloaded >= 400000 and elapsed > 0.1:
                        speed_mbps = (downloaded * 8) / (elapsed * 1_000_000)
                        if speed_mbps > best_speed:
                            best_speed = speed_mbps
                except Exception:
                    continue
    except Exception:
        return 0.0

    if best_speed <= 0.0:
        return 0.0
    return round(max(1.0, best_speed), 2)


async def _classify_vless_failure_with_proxy_recheck(
    upstream_proxy: UpstreamProxy,
    factor_error: str,
) -> str:
    proxy_ok, proxy_err = await ProxyPool.probe_proxy(upstream_proxy, force=True)
    if proxy_ok:
        return factor_error

    ProxyPool.mark_bad(upstream_proxy)
    return f"SYS_ERR: RU Proxy Dead ({proxy_err})"


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
    upstream_proxy: UpstreamProxy | None = None
    use_ru_proxy_chain = bool(getattr(config, "CHECKER_USE_RU_PROXY_CHAIN", True))

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
        if use_ru_proxy_chain:
            upstream_proxy, proxy_err = await ProxyPool.acquire_working_proxy(max_attempts=6)
            if not upstream_proxy:
                err_text = str(proxy_err or "SYS_ERR: RU Proxy Pool Empty")
                if not err_text.startswith("SYS_ERR"):
                    err_text = f"SYS_ERR: {err_text}"
                response_data["error"] = err_text
                return web.json_response(response_data)

        process, local_port, config_path = await XrayExecutor.start_xray(
            config_url,
            upstream_proxy=(upstream_proxy.to_xray_dict() if upstream_proxy else None),
        )

        if not process:
            err_text = str(config_path or "SYS_ERR: Checker Init Failed")
            if (
                "SYS_ERR" not in err_text
                and (
                    "Xray Crashed" in err_text
                    or "Port Bind Timeout" in err_text
                    or "Worker Busy" in err_text
                )
            ):
                err_text = f"SYS_ERR: {err_text}"
            response_data["error"] = err_text
            return web.json_response(response_data)

        is_alive, latency, error_msg = await check_connectivity(local_port)

        if not is_alive:
            if use_ru_proxy_chain and upstream_proxy:
                classified_err = await _classify_vless_failure_with_proxy_recheck(
                    upstream_proxy,
                    error_msg,
                )
            else:
                classified_err = error_msg
            response_data["error"] = classified_err
            return web.json_response(response_data)

        deep_latency = latency
        deep_speed = 0.0
        if use_ru_proxy_chain:
            deep_ok, deep_latency, deep_speed, deep_err = await deep_traffic_test(local_port)
            if not deep_ok:
                classified_err = await _classify_vless_failure_with_proxy_recheck(
                    upstream_proxy,
                    deep_err,
                )
                response_data["error"] = classified_err
                return web.json_response(response_data)
        else:
            deep_speed = await quick_speed_probe(local_port)

        if deep_speed <= 0.0:
            estimated = 2400.0 / max(float(latency), 1.0)
            deep_speed = round(max(1.0, min(250.0, estimated)), 2)

        response_data["success"] = True
        response_data["latency"] = latency
        if not isinstance(response_data["latency"], int) or response_data["latency"] <= 0:
            response_data["latency"] = deep_latency
        response_data["speed_mbps"] = max(1.0, float(deep_speed or 1.0))
        response_data["rkn_mode"] = "ru_proxy" if use_ru_proxy_chain else "ru_direct"
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
                try:
                    response_data["ai"] = await asyncio.wait_for(
                        check_ai_availability(local_port),
                        timeout=2.5,
                    )
                except Exception:
                    response_data["ai"] = False
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
                try:
                    response_data["no_ads"] = await asyncio.wait_for(
                        check_no_ads(local_port),
                        timeout=2.5,
                    )
                except Exception:
                    response_data["no_ads"] = False
                if ip and r_client:
                    try:
                        await r_client.setex(
                            f"chk:ads:{ip}",
                            3600,
                            "1" if response_data["no_ads"] else "0",
                        )
                    except:
                        pass

    except Exception as e:
        response_data["success"] = False
        response_data["error"] = f"SYS_ERR: Checker Handler Exception ({str(e)})"
    finally:
        await XrayExecutor.cleanup(process, config_path)

    return web.json_response(response_data)


async def health_check(request):
    return web.Response(text="OK")


async def start_background_tasks(app):
    loop = asyncio.get_running_loop()
    loop.set_exception_handler(custom_exception_handler)
    app["cleanup_task"] = asyncio.create_task(cleanup_zombie_xrays())
    if bool(getattr(config, "CHECKER_USE_RU_PROXY_CHAIN", True)):
        app["proxy_pool_task"] = asyncio.create_task(refresh_proxy_pool_loop())


async def cleanup_background_tasks(app):
    for task_key in ("cleanup_task", "proxy_pool_task"):
        task = app.get(task_key)
        if task and not task.done():
            task.cancel()
            try:
                await task
            except Exception:
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

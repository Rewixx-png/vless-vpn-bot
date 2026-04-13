import asyncio
import time

import aiohttp

from utils.parser import LinkParser
from utils.checker.api import CheckerAPI
from utils.checker.geo_ip import GeoIP
from config import config


class VlessChecker:
    TCP_TIMEOUT_SEC = max(1.0, min(float(config.CONNECTIVITY_TIMEOUT), 10.0))
    TCP_JITTER_SAMPLES = 4
    TCP_JITTER_PAUSE_SEC = 0.06

    _SYS_ERR_MARKERS = (
        "SYS_ERR",
        "Worker Busy",
        "Service Offline",
        "Service Error",
        "Checker API Timeout",
        "Checker Timeout",
        "Xray Crashed",
        "Port Bind Timeout",
    )

    @staticmethod
    def parse_config(config_url: str):
        return LinkParser.parse_vless(config_url)

    @staticmethod
    async def _check_tcp(host: str, port: int, timeout: float) -> tuple[bool, int, str]:
        try:
            started = time.monotonic()
            conn = asyncio.open_connection(host, port)
            reader, writer = await asyncio.wait_for(conn, timeout=timeout)
            latency_ms = max(1, int((time.monotonic() - started) * 1000))

            if reader.at_eof():
                writer.close()
                try:
                    await writer.wait_closed()
                except Exception:
                    pass
                return False, 9999, "Factor 1: TCP Closed"

            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass

            return True, latency_ms, "OK"
        except asyncio.TimeoutError:
            return False, 9999, f"Factor 1: TCP Timeout (>{int(timeout)}s)"
        except Exception as e:
            return False, 9999, f"Factor 1: TCP Unreachable ({e})"

    @classmethod
    async def measure_tcp_jitter(
        cls,
        host: str,
        port: int,
        samples: int | None = None,
        timeout: float | None = None,
    ) -> tuple[bool, int, str]:
        safe_samples = max(3, int(samples or cls.TCP_JITTER_SAMPLES))
        safe_timeout = float(timeout or min(2.5, cls.TCP_TIMEOUT_SEC))

        latencies: list[int] = []
        for idx in range(safe_samples):
            ok, latency, err = await cls._check_tcp(
                host=host,
                port=port,
                timeout=safe_timeout,
            )
            if not ok:
                return False, 9999, err

            if isinstance(latency, int) and latency > 0:
                latencies.append(latency)

            if idx < safe_samples - 1:
                await asyncio.sleep(cls.TCP_JITTER_PAUSE_SEC)

        if len(latencies) < 2:
            return False, 9999, "Factor 5: Jitter Probe Failed"

        jitter_ms = max(latencies) - min(latencies)
        return True, max(0, int(jitter_ms)), "OK"

    @staticmethod
    async def _check_via_checker(
        config_url: str,
    ) -> tuple[bool, str, int, float, bool, bool, str, str]:
        try:
            (
                success,
                region,
                latency,
                speed_mbps,
                ai,
                no_ads,
                err,
            ) = await asyncio.wait_for(
                CheckerAPI.check(config_url), timeout=config.CHECKER_TIMEOUT
            )
        except asyncio.TimeoutError:
            return (
                False,
                "",
                0,
                0.0,
                False,
                False,
                f"SYS_ERR: Checker Timeout (>{config.CHECKER_TIMEOUT}s)",
                config_url,
            )

        if not success:
            err_text = str(err or "Factor 4: Connectivity Failed")
            if VlessChecker._is_sys_err(err_text):
                return (
                    False,
                    "",
                    0,
                    0.0,
                    False,
                    False,
                    VlessChecker._normalize_sys_err(err_text),
                    config_url,
                )

            if not err_text.startswith("Factor"):
                err_text = f"Factor 4: {err_text}"

            safe_region = region if region else "🌍 UNK"
            safe_latency = latency if isinstance(latency, int) else 9999
            safe_speed = float(speed_mbps) if isinstance(speed_mbps, (int, float)) else 0.0
            return (
                False,
                safe_region,
                safe_latency,
                safe_speed,
                False,
                False,
                err_text,
                config_url,
            )

        safe_region = region if region else "🌍 UNK"
        safe_latency = latency if isinstance(latency, int) else 9999
        safe_speed = float(speed_mbps) if isinstance(speed_mbps, (int, float)) else 0.0
        if safe_speed <= 0.0:
            safe_speed = 1.0

        return (
            True,
            safe_region,
            safe_latency,
            safe_speed,
            bool(ai),
            bool(no_ads),
            str(err or "OK"),
            config_url,
        )

    @classmethod
    def _is_sys_err(cls, err_text: str) -> bool:
        text = str(err_text or "")
        return any(marker in text for marker in cls._SYS_ERR_MARKERS)

    @staticmethod
    def _normalize_sys_err(err_text: str) -> str:
        text = str(err_text or "SYS_ERR: Unknown")
        if text.startswith("SYS_ERR"):
            return text
        return f"SYS_ERR: {text}"

    @staticmethod
    async def process_subscription(
        config_url: str,
        strict_speed: bool = True,
    ) -> tuple[bool, str, int, float, bool, bool, str, str]:
        _ = strict_speed
        parsed = LinkParser.parse_vless(config_url)
        if not parsed:
            return (
                False,
                "🌍 UNK",
                9999,
                0.0,
                False,
                False,
                "Factor 0: Invalid Config",
                config_url,
            )

        host = str(parsed.get("server", "") or "").strip()
        port = int(parsed.get("port", 0) or 0)
        if not host or port < 1 or port > 65535:
            return (
                False,
                "🌍 UNK",
                9999,
                0.0,
                False,
                False,
                "Factor 0: Invalid Host/Port",
                config_url,
            )

        is_alive, latency, err_text = await VlessChecker._check_tcp(
            host=host,
            port=port,
            timeout=VlessChecker.TCP_TIMEOUT_SEC,
        )

        if not is_alive:
            return (
                False,
                "🌍 UNK",
                9999,
                0.0,
                False,
                False,
                err_text,
                config_url,
            )

        (
            via_checker_ok,
            region,
            checker_latency,
            checker_speed,
            ai,
            no_ads,
            checker_err,
            updated_link,
        ) = await VlessChecker._check_via_checker(config_url)

        if not via_checker_ok:
            return (
                False,
                region if region else "🌍 UNK",
                checker_latency if isinstance(checker_latency, int) else 9999,
                checker_speed if isinstance(checker_speed, (int, float)) else 0.0,
                False,
                False,
                checker_err,
                updated_link,
            )

        final_latency = checker_latency if isinstance(checker_latency, int) else int(latency)
        final_speed = checker_speed if isinstance(checker_speed, (int, float)) else 1.0
        if final_speed <= 0.0:
            final_speed = 1.0

        return (
            True,
            region if region else "🌍 UNK",
            final_latency,
            float(final_speed),
            bool(ai),
            bool(no_ads),
            checker_err if checker_err else "OK",
            updated_link,
        )

    @classmethod
    async def get_regions_batch(
        cls, hosts_data: list, session: aiohttp.ClientSession
    ) -> dict:
        if hosts_data and isinstance(hosts_data[0], str):
            hosts_data = [(h, "") for h in hosts_data]

        return await GeoIP.get_regions_batch(hosts_data, session)

    @staticmethod
    async def verify_domain(domain: str) -> tuple[bool, str]:
        try:
            resolved_ip = await GeoIP.resolve_host(domain)
            if not resolved_ip:
                return False, "DNS Resolve Failed"
            return True, f"OK ({resolved_ip})"
        except Exception as e:
            return False, str(e)

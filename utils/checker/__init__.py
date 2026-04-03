import asyncio
import time

import aiohttp

from utils.parser import LinkParser
from utils.checker.api import CheckerAPI
from utils.checker.geo_ip import GeoIP
from config import config


class VlessChecker:
    TCP_TIMEOUT_SEC = max(1.0, min(float(config.CONNECTIVITY_TIMEOUT), 10.0))
    MIN_STRICT_SPEED_MBPS = 1.0

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
                "🌍 UNK",
                9999,
                0.0,
                False,
                False,
                f"Factor 4: Config Check Timeout (>{config.CHECKER_TIMEOUT}s)",
                config_url,
            )

        if not success:
            err_text = str(err or "Factor 4: Connectivity Failed")
            if err_text.startswith("SYS_ERR"):
                return False, "", 0, 0.0, False, False, err_text, config_url

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

        if safe_speed <= VlessChecker.MIN_STRICT_SPEED_MBPS:
            return (
                False,
                safe_region,
                safe_latency,
                0.0,
                False,
                False,
                "Factor 6: Speed <= 1 Mbps",
                config_url,
            )

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

    @staticmethod
    async def process_subscription(
        config_url: str,
        strict_speed: bool = True,
    ) -> tuple[bool, str, int, float, bool, bool, str, str]:
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

        if strict_speed:
            return await VlessChecker._check_via_checker(config_url)

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

        region = await GeoIP.identify_region_full(
            host=host,
            remark=str(parsed.get("name", "")),
        )
        if not region:
            region = "🌍 UNK"

        is_alive, latency, err_text = await VlessChecker._check_tcp(
            host=host,
            port=port,
            timeout=VlessChecker.TCP_TIMEOUT_SEC,
        )

        if is_alive:
            pseudo_speed = round(max(1.0, 1500.0 / max(float(latency), 1.0)), 2)
            return (
                True,
                region,
                int(latency),
                pseudo_speed,
                False,
                False,
                "OK",
                config_url,
            )

        return (
            False,
            region,
            9999,
            0.0,
            False,
            False,
            err_text,
            config_url,
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

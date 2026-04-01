import asyncio
import aiohttp
from utils.parser import LinkParser
from utils.checker.api import CheckerAPI
from utils.checker.geo_ip import GeoIP
from config import config

class VlessChecker:
    @staticmethod
    def parse_config(config_url: str):
        return LinkParser.parse_vless(config_url)

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

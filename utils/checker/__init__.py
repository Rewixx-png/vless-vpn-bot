import asyncio
import ssl
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
    async def check_tcp_connectivity(
        host: str, port: int, timeout: float = 5.0
    ) -> bool:
        conn = None
        try:
            conn = asyncio.open_connection(host, port)
            reader, writer = await asyncio.wait_for(conn, timeout=timeout)
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass
            return True
        except Exception:
            return False

    @staticmethod
    async def check_ssl_handshake(
        host: str, port: int, sni: str, timeout: float = 6.0
    ) -> bool:
        try:
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE

            conn = asyncio.open_connection(
                host,
                port,
                ssl=ctx,
                server_hostname=sni or host,
            )
            reader, writer = await asyncio.wait_for(conn, timeout=timeout)

            writer.close()
            try:
                await writer.wait_closed()
            except:
                pass
            return True
        except Exception:
            return False

    @staticmethod
    async def process_subscription(
        config_url: str,
        strict_speed: bool = True,
    ) -> tuple[bool, str, int, float, bool, bool, str, str]:
        parsed = LinkParser.parse_vless(config_url)

        if parsed:
            host = parsed.get("server")
            port = parsed.get("port")

            if host and port:
                resolved_ip = await GeoIP.resolve_host(host)
                check_ip = resolved_ip if resolved_ip else host

                is_tcp_alive = await VlessChecker.check_tcp_connectivity(
                    check_ip, port, timeout=5.0
                )
                if not is_tcp_alive:
                    await GeoIP.invalidate_cache(host)
                    return (
                        False,
                        "🌍 UNK",
                        9999,
                        0.0,
                        False,
                        False,
                        "Factor 1: TCP Unreachable",
                        config_url,
                    )

                security = parsed.get("security", "none")
                if security in ["tls", "reality"]:
                    sni = parsed.get("sni") or parsed.get("host") or host
                    is_ssl_alive = await VlessChecker.check_ssl_handshake(
                        check_ip, port, sni, timeout=6.0
                    )

                    if not is_ssl_alive:
                        FALLBACK_SNIS = [
                            "yahoo.com",
                            "www.microsoft.com",
                            "cloudflare-dns.com",
                            "gateway.icloud.com",
                            "itunes.apple.com",
                        ]
                        working_sni = None
                        for alt_sni in FALLBACK_SNIS:
                            if await VlessChecker.check_ssl_handshake(
                                check_ip, port, alt_sni, timeout=2.0
                            ):
                                working_sni = alt_sni
                                break

                        if working_sni:
                            config_url = LinkParser.update_param(
                                config_url, "sni", working_sni
                            )
                        else:
                            return (
                                False,
                                "🌍 UNK",
                                9999,
                                0.0,
                                False,
                                False,
                                "Factor 2: SSL Handshake Failed (All SNIs)",
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
                        f"Factor 3: Config Check Timeout (>{config.CHECKER_TIMEOUT}s)",
                        config_url,
                    )

                if strict_speed and success and speed_mbps < config.MIN_SPEED_MBPS:
                    return (
                        False,
                        region,
                        latency,
                        speed_mbps,
                        False,
                        False,
                        f"Factor 6: Speed Too Low ({speed_mbps} < {config.MIN_SPEED_MBPS})",
                        config_url,
                    )

                if not success and err and str(err).startswith("SYS_ERR"):
                    return False, "", 0, 0.0, False, False, err, config_url

                if (
                    not success
                    and not strict_speed
                    and err
                    and "Factor 4" in str(err)
                ):
                    fallback_region = region
                    if not fallback_region or "UNK" in str(fallback_region):
                        try:
                            fallback_region = await GeoIP.identify_region(
                                host=host,
                                remark=parsed.get("name"),
                            )
                        except Exception:
                            fallback_region = "🌍 UNK"

                    fallback_latency = latency if isinstance(latency, int) and latency < 9000 else 1800
                    fallback_speed = speed_mbps if isinstance(speed_mbps, (int, float)) and speed_mbps > 0 else 1.0

                    return (
                        True,
                        fallback_region or "🌍 UNK",
                        int(fallback_latency),
                        float(fallback_speed),
                        False,
                        False,
                        "WARN: Factor 4 bypassed",
                        config_url,
                    )

                return success, region, latency, speed_mbps, ai, no_ads, err, config_url

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

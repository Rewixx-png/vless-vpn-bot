import asyncio
import ssl
import aiohttp
from utils.parser import LinkParser
from utils.checker.api import CheckerAPI
from utils.checker.geo_ip import GeoIP

class VlessChecker:
    @staticmethod
    def parse_config(config_url: str):
        return LinkParser.parse_vless(config_url)

    @staticmethod
    async def check_tcp_connectivity(host: str, port: int, timeout: float = 2.0) -> bool:
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
    async def check_ssl_handshake(host: str, port: int, sni: str, timeout: float = 3.0) -> bool:
        try:
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            
            conn = asyncio.open_connection(host, port, ssl=ctx)
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
    async def process_subscription(config_url: str) -> tuple[bool, str, int, float, bool, str, str]:
        parsed = LinkParser.parse_vless(config_url)
        
        if parsed:
            host = parsed.get("server")
            port = parsed.get("port")
            
            if host and port:
                resolved_ip = await GeoIP.resolve_host(host)
                check_ip = resolved_ip if resolved_ip else host
                
                is_tcp_alive = await VlessChecker.check_tcp_connectivity(check_ip, port, timeout=2.0)
                if not is_tcp_alive:
                    await GeoIP.invalidate_cache(host)
                    return False, "🌍 UNK", 9999, 0.0, False, "Factor 1: TCP Unreachable", config_url

                security = parsed.get("security", "none")
                if security in ["tls", "reality"]:
                    sni = parsed.get("sni") or parsed.get("host") or host
                    is_ssl_alive = await VlessChecker.check_ssl_handshake(check_ip, port, sni, timeout=3.0)
                    
                    if not is_ssl_alive:
                        FALLBACK_SNIS =["yahoo.com", "www.microsoft.com", "cloudflare-dns.com", "gateway.icloud.com", "itunes.apple.com"]
                        working_sni = None
                        for alt_sni in FALLBACK_SNIS:
                            if await VlessChecker.check_ssl_handshake(check_ip, port, alt_sni, timeout=2.0):
                                working_sni = alt_sni
                                break
                        
                        if working_sni:
                            config_url = LinkParser.update_param(config_url, "sni", working_sni)
                        else:
                            return False, "🌍 UNK", 9999, 0.0, False, "Factor 2: SSL Handshake Failed (All SNIs)", config_url

        # Wrap CheckerAPI.check with timeout to prevent hanging
        try:
            success, region, latency, speed_mbps, ai, err = await asyncio.wait_for(
                CheckerAPI.check(config_url),
                timeout=25.0  # Max 25 seconds per config check
            )
        except asyncio.TimeoutError:
            return False, "🌍 UNK", 9999, 0.0, False, "Factor 3: Config Check Timeout (>25s)", config_url

        # Check speed - reject configs with speed < 25 Mbps
        if success and speed_mbps < 25.0:
            return False, region, latency, speed_mbps, False, f"Factor 6: Speed Too Low ({speed_mbps} < 25)", config_url

        if not success and err and str(err).startswith("SYS_ERR"):
            return False, "", 0, 0.0, False, err, config_url

        return success, region, latency, speed_mbps, ai, err, config_url

    @classmethod
    async def get_regions_batch(cls, hosts_data: list[tuple[str, str]], session: aiohttp.ClientSession) -> dict[str, str]:
        if hosts_data and isinstance(hosts_data[0], str):
            hosts_data =[(h, "") for h in hosts_data]
            
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
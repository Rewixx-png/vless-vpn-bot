import logging
import asyncio
import ssl
import aiohttp
from utils.parser import LinkParser
from utils.checker.api import CheckerAPI
from utils.checker.geo_ip import GeoIP
from utils.checker.xray import XrayExecutor

logger = logging.getLogger("Checker")

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
        writer = None
        try:
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            
            conn = asyncio.open_connection(host, port)
            reader, writer = await asyncio.wait_for(conn, timeout=timeout)
            
            try:
                await asyncio.wait_for(
                    writer.start_tls(ctx, server_hostname=sni if sni else host),
                    timeout=timeout
                )
                return True
            except Exception:
                return False
        except Exception:
            return False
        finally:
            if writer:
                try:
                    writer.close()
                    # Не ждем wait_closed, чтобы не блокировать loop, если сокет завис
                except Exception:
                    pass

    @staticmethod
    async def process_subscription(config_url: str) -> tuple[bool, str, int, float, bool, str]:
        parsed = LinkParser.parse_vless(config_url)
        
        if parsed:
            host = parsed.get("server")
            port = parsed.get("port")
            
            # FACTOR 1: TCP Ping (Layer 4)
            if host and port:
                is_tcp_alive = await VlessChecker.check_tcp_connectivity(host, port, timeout=2.0)
                if not is_tcp_alive:
                    return False, "🌍 UNK", 9999, 0.0, False, "Factor 1: TCP Unreachable"

            # FACTOR 2: SSL/TLS Handshake (Layer 6)
            security = parsed.get("security", "none")
            if security in ["tls", "reality"]:
                sni = parsed.get("sni") or parsed.get("host") or host
                is_ssl_alive = await VlessChecker.check_ssl_handshake(host, port, sni, timeout=3.0)
                if not is_ssl_alive:
                    return False, "🌍 UNK", 9999, 0.0, False, "Factor 2: SSL Handshake Failed"

        # FACTOR 3: Xray Real Test (Layer 7)
        success, region, latency, speed_mbps, ai, err = await CheckerAPI.check(config_url)
        
        if not success and err and str(err).startswith("SYS_ERR"):
            return False, "", 0, 0.0, False, err
            
        return success, region, latency, speed_mbps, ai, err

    @classmethod
    async def get_regions_batch(cls, hosts_data: list[tuple[str, str]], session: aiohttp.ClientSession) -> dict[str, str]:
        if hosts_data and isinstance(hosts_data[0], str):
            hosts_data = [(h, "") for h in hosts_data]
            
        return await GeoIP.get_regions_batch(hosts_data, session)

    @staticmethod
    async def verify_domain(domain: str) -> tuple[bool, str]:
        try:
            import asyncio
            loop = asyncio.get_running_loop()
            try:
                ip = await loop.getaddrinfo(domain, 80)
                ip_addr = ip[0][4][0]
            except: return False, "DNS Resolve Failed"
            return True, f"OK ({ip_addr})"
        except Exception as e: return False, str(e)
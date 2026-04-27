import asyncio
import base64
import ipaddress
import time

import aiohttp

from utils.parser import LinkParser
from utils.checker.api import CheckerAPI
from utils.checker.geo_ip import GeoIP
from utils.checker.proxy_pool import ProxyPool, UpstreamProxy
from config import config


class VlessChecker:
    TCP_TIMEOUT_SEC = max(1.0, min(float(config.CONNECTIVITY_TIMEOUT), 10.0))
    TCP_JITTER_SAMPLES = 4
    TCP_JITTER_PAUSE_SEC = 0.06
    TCP_PROXY_CACHE_TTL_SEC = 25.0

    _cached_tcp_proxy: UpstreamProxy | None = None
    _cached_tcp_proxy_at: float = 0.0

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
    async def _acquire_tcp_probe_proxy(cls) -> tuple[UpstreamProxy | None, str]:
        now = time.monotonic()
        if (
            cls._cached_tcp_proxy is not None
            and (now - cls._cached_tcp_proxy_at) <= cls.TCP_PROXY_CACHE_TTL_SEC
        ):
            return cls._cached_tcp_proxy, "OK"

        proxy, proxy_err = await ProxyPool.acquire_working_proxy(max_attempts=3)
        if proxy:
            cls._cached_tcp_proxy = proxy
            cls._cached_tcp_proxy_at = time.monotonic()
            return proxy, "OK"

        cls._cached_tcp_proxy = None
        cls._cached_tcp_proxy_at = 0.0
        err_text = str(proxy_err or "SYS_ERR: RU TCP Proxy Unavailable")
        if not err_text.startswith("SYS_ERR"):
            err_text = f"SYS_ERR: {err_text}"
        return None, err_text

    @classmethod
    def _drop_cached_tcp_proxy(cls) -> None:
        cls._cached_tcp_proxy = None
        cls._cached_tcp_proxy_at = 0.0

    @staticmethod
    async def _read_exact(reader: asyncio.StreamReader, size: int, timeout: float) -> bytes:
        return await asyncio.wait_for(reader.readexactly(size), timeout=timeout)

    @staticmethod
    def _build_socks_target(host: str, port: int) -> bytes:
        try:
            ip_v4 = ipaddress.IPv4Address(host)
            return b"\x01" + ip_v4.packed + int(port).to_bytes(2, byteorder="big")
        except Exception:
            pass

        try:
            ip_v6 = ipaddress.IPv6Address(host)
            return b"\x04" + ip_v6.packed + int(port).to_bytes(2, byteorder="big")
        except Exception:
            pass

        host_bytes = host.encode("idna")
        if len(host_bytes) > 255:
            raise ValueError("Host is too long for SOCKS5 domain target")
        return (
            b"\x03"
            + bytes([len(host_bytes)])
            + host_bytes
            + int(port).to_bytes(2, byteorder="big")
        )

    @staticmethod
    async def _consume_http_headers(reader: asyncio.StreamReader, timeout: float) -> None:
        while True:
            line = await asyncio.wait_for(reader.readline(), timeout=timeout)
            if not line or line in {b"\r\n", b"\n"}:
                return

    @classmethod
    async def _check_tcp_via_proxy(
        cls,
        host: str,
        port: int,
        timeout: float,
        proxy: UpstreamProxy,
    ) -> tuple[bool, int, str]:
        reader = None
        writer = None
        started = time.monotonic()
        phase = "connect_proxy"

        scheme = str(proxy.scheme or "").strip().lower()
        try:
            conn = asyncio.open_connection(proxy.host, proxy.port)
            reader, writer = await asyncio.wait_for(conn, timeout=timeout)

            if scheme.startswith("socks"):
                methods = [0x00]
                if proxy.username:
                    methods.append(0x02)

                writer.write(bytes([0x05, len(methods), *methods]))
                await asyncio.wait_for(writer.drain(), timeout=timeout)

                phase = "proxy_greeting"
                greeting = await cls._read_exact(reader, 2, timeout)
                if greeting[0] != 0x05:
                    cls._drop_cached_tcp_proxy()
                    return False, 9999, "SYS_ERR: TCP Proxy Invalid SOCKS Greeting"

                method = greeting[1]
                if method == 0xFF:
                    cls._drop_cached_tcp_proxy()
                    return False, 9999, "SYS_ERR: TCP Proxy Auth Method Rejected"

                if method == 0x02:
                    if not proxy.username:
                        cls._drop_cached_tcp_proxy()
                        return False, 9999, "SYS_ERR: TCP Proxy Requested Auth"

                    uname = proxy.username.encode("utf-8")
                    passwd = proxy.password.encode("utf-8")
                    if len(uname) > 255 or len(passwd) > 255:
                        cls._drop_cached_tcp_proxy()
                        return False, 9999, "SYS_ERR: TCP Proxy Credentials Too Long"

                    auth_packet = (
                        bytes([0x01, len(uname)])
                        + uname
                        + bytes([len(passwd)])
                        + passwd
                    )
                    writer.write(auth_packet)
                    await asyncio.wait_for(writer.drain(), timeout=timeout)

                    phase = "proxy_auth"
                    auth_reply = await cls._read_exact(reader, 2, timeout)
                    if auth_reply[1] != 0x00:
                        cls._drop_cached_tcp_proxy()
                        return False, 9999, "SYS_ERR: TCP Proxy Authentication Failed"

                target = cls._build_socks_target(host, port)
                writer.write(b"\x05\x01\x00" + target)
                await asyncio.wait_for(writer.drain(), timeout=timeout)

                phase = "proxy_connect"
                head = await cls._read_exact(reader, 4, timeout)
                if head[0] != 0x05:
                    return False, 9999, "Factor 1: TCP Proxy Protocol Error"

                reply = head[1]
                if reply != 0x00:
                    reply_map = {
                        0x01: "General Failure",
                        0x02: "Rule Set Denied",
                        0x03: "Network Unreachable",
                        0x04: "Host Unreachable",
                        0x05: "Connection Refused",
                        0x06: "TTL Expired",
                        0x07: "Command Not Supported",
                        0x08: "Address Type Not Supported",
                    }
                    reason = reply_map.get(reply, f"Reply {reply}")
                    return False, 9999, f"Factor 1: TCP Unreachable ({reason})"

                atyp = head[3]
                if atyp == 0x01:
                    await cls._read_exact(reader, 4, timeout)
                elif atyp == 0x03:
                    size = await cls._read_exact(reader, 1, timeout)
                    await cls._read_exact(reader, size[0], timeout)
                elif atyp == 0x04:
                    await cls._read_exact(reader, 16, timeout)
                else:
                    return False, 9999, "Factor 1: TCP Proxy Address Error"

                await cls._read_exact(reader, 2, timeout)

                latency_ms = max(1, int((time.monotonic() - started) * 1000))
                return True, latency_ms, "OK"

            if scheme.startswith("http"):
                auth_line = ""
                if proxy.username:
                    credentials = f"{proxy.username}:{proxy.password}".encode("utf-8")
                    auth_line = (
                        "Proxy-Authorization: Basic "
                        + base64.b64encode(credentials).decode("ascii")
                        + "\r\n"
                    )

                request = (
                    f"CONNECT {host}:{port} HTTP/1.1\r\n"
                    f"Host: {host}:{port}\r\n"
                    f"{auth_line}"
                    "Proxy-Connection: Keep-Alive\r\n\r\n"
                )
                writer.write(request.encode("utf-8"))
                await asyncio.wait_for(writer.drain(), timeout=timeout)

                phase = "http_proxy_tunnel"
                status_line = await asyncio.wait_for(reader.readline(), timeout=timeout)
                if not status_line:
                    return False, 9999, "Factor 1: TCP Proxy Empty HTTP Reply"

                status_text = status_line.decode("latin-1", errors="ignore").strip()
                if " " not in status_text:
                    cls._drop_cached_tcp_proxy()
                    return False, 9999, "SYS_ERR: TCP Proxy Invalid HTTP Reply"

                parts = status_text.split(" ", 2)
                code = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0
                await cls._consume_http_headers(reader, timeout=timeout)

                if code != 200:
                    if code in {401, 403, 407}:
                        cls._drop_cached_tcp_proxy()
                        return False, 9999, f"SYS_ERR: TCP Proxy Auth/ACL HTTP {code}"
                    return False, 9999, f"Factor 1: TCP Unreachable (HTTP Proxy {code})"

                latency_ms = max(1, int((time.monotonic() - started) * 1000))
                return True, latency_ms, "OK"

            cls._drop_cached_tcp_proxy()
            return False, 9999, f"SYS_ERR: Unsupported TCP Proxy Scheme ({proxy.scheme})"

        except asyncio.TimeoutError:
            if phase in {"connect_proxy", "proxy_greeting", "proxy_auth"}:
                cls._drop_cached_tcp_proxy()
                return False, 9999, "SYS_ERR: TCP Probe Proxy Timeout"
            return False, 9999, f"Factor 1: TCP Timeout via RU Proxy (>{int(timeout)}s)"
        except Exception as e:
            cls._drop_cached_tcp_proxy()
            return False, 9999, f"SYS_ERR: TCP Probe Proxy Error ({e})"
        finally:
            if writer is not None:
                writer.close()
                try:
                    await writer.wait_closed()
                except Exception:
                    pass

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
        use_ru_proxy = bool(getattr(config, "CHECKER_USE_RU_PROXY_CHAIN", True))

        probe_proxy = None
        if use_ru_proxy:
            probe_proxy, proxy_err = await cls._acquire_tcp_probe_proxy()
            if not probe_proxy:
                return False, 9999, proxy_err

        latencies: list[int] = []
        for idx in range(safe_samples):
            if probe_proxy is not None:
                ok, latency, err = await cls._check_tcp_via_proxy(
                    host=host,
                    port=port,
                    timeout=safe_timeout,
                    proxy=probe_proxy,
                )
            else:
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
        checker_timeout = float(config.CHECKER_TIMEOUT)
        if bool(getattr(config, "CHECKER_USE_RU_PROXY_CHAIN", True)):
            checker_timeout = max(checker_timeout, 35.0)

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
                CheckerAPI.check(config_url), timeout=checker_timeout
            )
        except asyncio.TimeoutError:
            return (
                False,
                "",
                0,
                0.0,
                False,
                False,
                f"SYS_ERR: Checker Timeout (>{checker_timeout}s)",
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
        use_ru_proxy = bool(getattr(config, "CHECKER_USE_RU_PROXY_CHAIN", True))
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

        probe_proxy = None
        if use_ru_proxy:
            probe_proxy, proxy_err = await VlessChecker._acquire_tcp_probe_proxy()
            if not probe_proxy:
                return (
                    False,
                    "🌍 UNK",
                    9999,
                    0.0,
                    False,
                    False,
                    proxy_err,
                    config_url,
                )

        if probe_proxy is not None:
            is_alive, latency, err_text = await VlessChecker._check_tcp_via_proxy(
                host=host,
                port=port,
                timeout=VlessChecker.TCP_TIMEOUT_SEC,
                proxy=probe_proxy,
            )
        else:
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

import asyncio
import ipaddress
import json
import re
import time
import urllib.parse

import aiohttp

from database.repo import SystemRepo


class TelegramProxyService:
    SOURCE_URLS = [
        "https://raw.githubusercontent.com/Argh94/Proxy-List/main/MTProto.txt",
        "https://raw.githubusercontent.com/MustafaBaqer/VestraNet-Nodes/main/protocols/mtproto.txt",
        "https://raw.githubusercontent.com/Surfboardv2ray/TGProto/main/proxies.txt",
        "https://raw.githubusercontent.com/hookzof/socks5_list/master/proxy.txt",
    ]
    CACHE_KEY = "tg_proxy_cache"
    CHECK_TIMEOUT = 1.8
    CHECK_CONCURRENCY = 35
    MAX_CHECK_LIMIT = 300
    MAX_OUTPUT_PROXIES = 50
    MAX_MERGED_CANDIDATES = 1500

    _HEX_RE = re.compile(r"^[0-9a-f]+$")
    _BASE64_SECRET_RE = re.compile(r"^[A-Za-z0-9_-]{22,512}$")
    _HOST_RE = re.compile(r"^[a-z0-9][a-z0-9.-]{0,252}[a-z0-9]$")
    _PLAIN_HOST_PORT_RE = re.compile(r"^([A-Za-z0-9.-]+):(\d{1,5})(?::.*)?$")

    @classmethod
    def _is_valid_host(cls, host: str) -> bool:
        value = (host or "").strip().strip(".").lower()
        if not value:
            return False
        if value in {"unknown", "none", "null"}:
            return False

        try:
            ipaddress.ip_address(value)
            return True
        except ValueError:
            pass

        if ".." in value:
            return False
        return bool(cls._HOST_RE.fullmatch(value))

    @classmethod
    def _normalize_secret(cls, secret_raw: str) -> tuple[str, str] | None:
        raw_value = urllib.parse.unquote(secret_raw or "").strip()
        if not raw_value:
            return None

        token = raw_value.split()[0].strip(" ,;)]}\"'")
        if not token:
            return None

        lower_token = token.lower()
        if cls._HEX_RE.fullmatch(lower_token) and len(lower_token) % 2 == 0:
            if lower_token.startswith("dd") and len(lower_token) == 34:
                return lower_token, "dd"
            if lower_token.startswith("ee") and 34 <= len(lower_token) <= 512:
                return lower_token, "ee"

        if cls._BASE64_SECRET_RE.fullmatch(token):
            return token, "base64"

        return None

    @staticmethod
    def _parse_port(port_raw: str) -> int | None:
        try:
            port = int(str(port_raw or "").strip())
        except Exception:
            return None

        if 1 <= port <= 65535:
            return port
        return None

    @classmethod
    def _normalize_mtproto(
        cls,
        server_raw: str,
        port_raw: str,
        secret_raw: str,
    ) -> dict | None:
        server = (server_raw or "").strip().strip(".").lower()
        if not cls._is_valid_host(server):
            return None

        port = cls._parse_port(port_raw)
        if not port:
            return None

        secret_info = cls._normalize_secret(secret_raw)
        if not secret_info:
            return None
        secret, secret_kind = secret_info

        proxy_link = "tg://proxy?" + urllib.parse.urlencode(
            {
                "server": server,
                "port": str(port),
                "secret": secret,
            },
            quote_via=urllib.parse.quote,
        )

        return {
            "kind": "mtproto",
            "secret_kind": secret_kind,
            "server": server,
            "port": port,
            "secret": secret,
            "link": proxy_link,
        }

    @classmethod
    def _normalize_socks(cls, server_raw: str, port_raw: str) -> dict | None:
        server = (server_raw or "").strip().strip(".").lower()
        if not cls._is_valid_host(server):
            return None

        port = cls._parse_port(port_raw)
        if not port:
            return None

        proxy_link = "tg://socks?" + urllib.parse.urlencode(
            {
                "server": server,
                "port": str(port),
            },
            quote_via=urllib.parse.quote,
        )

        return {
            "kind": "socks5",
            "server": server,
            "port": port,
            "link": proxy_link,
        }

    @classmethod
    def _normalize_proxy_line(cls, line: str) -> dict | None:
        raw = (line or "").strip()
        if not raw:
            return None

        token = raw.split()[0].strip().strip(",;")
        if not token:
            return None

        if "server=" in token and "port=" in token and "secret=" in token:
            query = urllib.parse.parse_qs(token, keep_blank_values=False)
            server = (query.get("server", [""])[0] or "").strip()
            port_raw = (query.get("port", [""])[0] or "").strip()
            secret_raw = (query.get("secret", [""])[0] or "").strip()
            proxy = cls._normalize_mtproto(server, port_raw, secret_raw)
            if proxy:
                return proxy

        parsed = urllib.parse.urlparse(token)
        query = urllib.parse.parse_qs(parsed.query, keep_blank_values=False)

        server = (query.get("server", [""])[0] or "").strip().strip(".")
        port_raw = (query.get("port", [""])[0] or "").strip()
        secret_raw = (query.get("secret", [""])[0] or "").strip()

        if server and port_raw and secret_raw:
            proxy = cls._normalize_mtproto(server, port_raw, secret_raw)
            if proxy:
                return proxy

        if server and port_raw and not secret_raw:
            is_socks_url = (
                parsed.netloc == "socks"
                or parsed.path.endswith("/socks")
                or parsed.scheme in {"socks", "socks5"}
            )
            if is_socks_url:
                proxy = cls._normalize_socks(server, port_raw)
                if proxy:
                    return proxy

        if parsed.scheme in {"socks", "socks5"} and parsed.hostname:
            try:
                parsed_port = parsed.port
            except ValueError:
                parsed_port = None

            if parsed_port:
                proxy = cls._normalize_socks(parsed.hostname, str(parsed_port))
                if proxy:
                    return proxy

        plain_match = cls._PLAIN_HOST_PORT_RE.fullmatch(token)
        if plain_match:
            proxy = cls._normalize_socks(
                plain_match.group(1),
                plain_match.group(2),
            )
            if proxy:
                return proxy

        return None

    @staticmethod
    def _proxy_key(proxy: dict) -> tuple:
        if str(proxy.get("kind", "")) == "mtproto":
            return (
                "mtproto",
                str(proxy.get("server", "")),
                int(proxy.get("port", 0) or 0),
                str(proxy.get("secret", "")),
            )
        return (
            "socks5",
            str(proxy.get("server", "")),
            int(proxy.get("port", 0) or 0),
        )

    @staticmethod
    async def _check_tcp(server: str, port: int, timeout: float) -> bool:
        try:
            conn = asyncio.open_connection(server, port)
            reader, writer = await asyncio.wait_for(conn, timeout=timeout)
            await asyncio.sleep(0.25)
            if reader.at_eof():
                writer.close()
                try:
                    await writer.wait_closed()
                except Exception:
                    pass
                return False
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass
            return True
        except Exception:
            return False

    @classmethod
    async def _fetch_source_lines(
        cls,
        session: aiohttp.ClientSession,
        source_url: str,
    ) -> tuple[str, list[str]]:
        try:
            async with session.get(source_url, allow_redirects=True) as resp:
                if resp.status != 200:
                    return source_url, []
                text = await resp.text()
        except Exception:
            return source_url, []

        return source_url, text.splitlines()

    @classmethod
    async def fetch_raw_lines(cls) -> list[tuple[str, list[str]]]:
        timeout = aiohttp.ClientTimeout(total=20, connect=8)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            tasks = [
                cls._fetch_source_lines(session, source_url)
                for source_url in cls.SOURCE_URLS
            ]
            return await asyncio.gather(*tasks, return_exceptions=False)

    @classmethod
    async def refresh_cache(cls) -> dict:
        source_payloads = await cls.fetch_raw_lines()

        source_stats = []
        source_buckets = []

        total_lines = 0
        parsed_total = 0

        for source_url, raw_lines in source_payloads:
            total_lines += len(raw_lines)
            source_local_seen = set()
            source_items = []

            parsed_in_source = 0
            for line in raw_lines:
                proxy = cls._normalize_proxy_line(line)
                if not proxy:
                    continue

                parsed_in_source += 1
                key = cls._proxy_key(proxy)
                if key in source_local_seen:
                    continue

                source_local_seen.add(key)
                source_items.append(proxy)

            parsed_total += parsed_in_source
            source_buckets.append(source_items)
            source_stats.append(
                {
                    "source": source_url,
                    "raw": len(raw_lines),
                    "parsed": parsed_in_source,
                    "unique": len(source_items),
                }
            )

        global_seen = set()
        candidates = []
        indices = [0] * len(source_buckets)

        while len(candidates) < cls.MAX_MERGED_CANDIDATES:
            progressed = False
            for bucket_idx, bucket in enumerate(source_buckets):
                pos = indices[bucket_idx]
                while pos < len(bucket):
                    proxy = bucket[pos]
                    pos += 1
                    key = cls._proxy_key(proxy)
                    if key in global_seen:
                        continue

                    global_seen.add(key)
                    candidates.append(proxy)
                    progressed = True
                    break

                indices[bucket_idx] = pos

                if len(candidates) >= cls.MAX_MERGED_CANDIDATES:
                    break

            if not progressed:
                break

        checked_candidates = candidates[: cls.MAX_CHECK_LIMIT]
        sem = asyncio.Semaphore(cls.CHECK_CONCURRENCY)

        def kind_priority(proxy: dict) -> int:
            kind = str(proxy.get("kind", ""))
            if kind == "mtproto":
                secret_kind = str(proxy.get("secret_kind", ""))
                if secret_kind == "dd":
                    return 0
                if secret_kind == "ee":
                    return 1
                return 2
            return 3

        async def check_one(proxy: dict) -> tuple[int, int, dict] | None:
            async with sem:
                is_alive_1 = await cls._check_tcp(
                    proxy["server"],
                    proxy["port"],
                    timeout=cls.CHECK_TIMEOUT,
                )

                if not is_alive_1:
                    return None

                start = time.monotonic()
                is_alive_2 = await cls._check_tcp(
                    proxy["server"],
                    proxy["port"],
                    timeout=cls.CHECK_TIMEOUT,
                )
                if not is_alive_2:
                    return None

                latency_ms = int((time.monotonic() - start) * 1000)
                return kind_priority(proxy), latency_ms, proxy

        results = await asyncio.gather(
            *(check_one(p) for p in checked_candidates),
            return_exceptions=False,
        )

        alive_items = [r for r in results if r]
        alive_items.sort(key=lambda item: (item[0], item[1]))
        best_items = alive_items[: cls.MAX_OUTPUT_PROXIES]

        proxy_items = [
            {
                "link": item[2]["link"],
                "latency_ms": int(item[1]),
                "kind": str(item[2].get("kind", "mtproto")),
                "secret_kind": str(item[2].get("secret_kind", "")),
            }
            for item in best_items
        ]
        alive_links = [item["link"] for item in proxy_items]

        payload = {
            "source": cls.SOURCE_URLS[0] if cls.SOURCE_URLS else "",
            "sources": cls.SOURCE_URLS,
            "source_stats": source_stats,
            "checked_at": int(time.time()),
            "total_lines": total_lines,
            "parsed": len(candidates),
            "parsed_total": parsed_total,
            "checked": len(checked_candidates),
            "alive": len(alive_links),
            "proxies": alive_links,
            "proxy_items": proxy_items,
        }

        await SystemRepo.set_config(
            cls.CACHE_KEY,
            json.dumps(payload, ensure_ascii=False),
        )
        return payload

    @classmethod
    async def get_cached(cls) -> dict | None:
        raw = await SystemRepo.get_config(cls.CACHE_KEY)
        if not raw:
            return None
        try:
            data = json.loads(raw)
            if isinstance(data, dict):
                return data
        except Exception:
            return None
        return None

    @classmethod
    async def get_cached_or_refresh(cls, max_age_sec: int = 3600) -> dict:
        cached = await cls.get_cached()
        now = int(time.time())
        if cached:
            checked_at = int(cached.get("checked_at", 0) or 0)
            if checked_at > 0 and (now - checked_at) <= max_age_sec:
                return cached
        return await cls.refresh_cache()

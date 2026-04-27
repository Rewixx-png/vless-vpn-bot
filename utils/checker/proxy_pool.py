import asyncio
import logging
import random
import re
import time
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlparse

import aiohttp
from aiohttp_socks import ProxyConnector

from config import config


logger = logging.getLogger("CheckerProxyPool")


@dataclass(frozen=True, slots=True)
class UpstreamProxy:
    scheme: str
    host: str
    port: int
    username: str = ""
    password: str = ""
    source: str = ""

    def to_url(self) -> str:
        auth = ""
        if self.username:
            auth = self.username
            if self.password:
                auth = f"{auth}:{self.password}"
            auth = f"{auth}@"
        return f"{self.scheme}://{auth}{self.host}:{self.port}"

    def to_xray_dict(self) -> dict:
        return {
            "scheme": self.scheme,
            "host": self.host,
            "port": self.port,
            "username": self.username,
            "password": self.password,
        }


class ProxyPool:
    SOURCE_URLS = (
        ("http", "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/http.txt"),
        ("socks5", "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/socks5.txt"),
        ("socks5", "https://raw.githubusercontent.com/TheSpeedX/SOCKS-List/master/socks5.txt"),
        ("socks5", "https://raw.githubusercontent.com/hookzof/socks5_list/master/proxy.txt"),
        (
            "http",
            "https://api.proxyscrape.com/v4/free-proxy-list/get?request=display_proxies&country=RU&protocol=http&proxy_format=ipport&format=text&timeout=4000",
        ),
        (
            "socks5",
            "https://api.proxyscrape.com/v4/free-proxy-list/get?request=display_proxies&country=RU&protocol=socks5&proxy_format=ipport&format=text&timeout=4000",
        ),
    )

    TARGET_COUNTRY_CODES = {"RU"}
    GEONODE_COUNTRY_CODE = "RU"
    GEONODE_PAGE_LIMIT = 150
    GEONODE_PAGES = 8
    GEONODE_URL_TEMPLATE = (
        "https://proxylist.geonode.com/api/proxy-list"
        "?limit={limit}&page={page}&sort_by=lastChecked&sort_type=desc"
        "&country={country}&protocols=http%2Csocks5"
    )

    GEO_CHECK_URL = "http://ip-api.com/json/?fields=status,countryCode,query"
    HEALTH_CHECK_URLS = (
        "http://ya.ru",
        "http://cp.cloudflare.com/generate_204",
    )

    REFRESH_INTERVAL_SEC = 300
    CANDIDATE_FETCH_TIMEOUT = aiohttp.ClientTimeout(total=24.0, connect=10.0)
    PROXY_VALIDATE_TIMEOUT = aiohttp.ClientTimeout(total=8.0, connect=4.0, sock_read=4.0)

    MAX_CANDIDATES_PER_SOURCE = 2200
    MAX_VALIDATE_CANDIDATES = 900
    VALIDATE_CONCURRENCY = 80
    RUNTIME_HEALTH_CACHE_TTL = 20
    GEO_CACHE_TTL = 1800
    BAD_PROXY_COOLDOWN_SEC = 120
    MAX_POOL_SIZE = 500
    PAID_PROXIES_RELOAD_SEC = 60

    _refresh_lock = asyncio.Lock()
    _proxies: list[UpstreamProxy] = []
    _last_refresh_at: float = 0.0
    _cursor: int = 0
    _paid_proxies: list[UpstreamProxy] = []
    _last_paid_reload_at: float = 0.0

    _bad_until: dict[str, float] = {}
    _health_cache: dict[str, tuple[bool, float]] = {}
    _geo_cache: dict[str, tuple[bool, float]] = {}

    @staticmethod
    async def _quick_probe_paid_proxy(proxy: UpstreamProxy) -> tuple[bool, str]:
        timeout = 2.0
        conn = None
        try:
            conn = await asyncio.wait_for(
                asyncio.open_connection(proxy.host, proxy.port),
                timeout=timeout,
            )
            reader, writer = conn

            scheme = str(proxy.scheme or "").strip().lower()
            if scheme.startswith("socks"):
                writer.write(b"\x05\x01\x00")
                await asyncio.wait_for(writer.drain(), timeout=timeout)
                data = await asyncio.wait_for(reader.readexactly(2), timeout=timeout)
                if data[0] != 0x05 or data[1] not in {0x00, 0x02}:
                    writer.close()
                    try:
                        await writer.wait_closed()
                    except Exception:
                        pass
                    return False, "Paid proxy SOCKS greeting failed"

            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass
            return True, "OK"
        except Exception as e:
            return False, f"Paid proxy unreachable ({str(e)})"

    @classmethod
    def _iter_proxy_tokens(cls, raw: str) -> list[str]:
        text = str(raw or "")
        if not text.strip():
            return []

        normalized = text.replace(";", "\n").replace(",", "\n")
        return [line.strip() for line in normalized.splitlines() if line.strip()]

    @classmethod
    def _load_paid_proxies(cls, force: bool = False) -> list[UpstreamProxy]:
        now = time.time()
        if (
            not force
            and cls._paid_proxies
            and (now - cls._last_paid_reload_at) < cls.PAID_PROXIES_RELOAD_SEC
        ):
            return list(cls._paid_proxies)

        raw_value = str(getattr(config, "RU_PAID_PROXIES", "") or "")
        tokens = cls._iter_proxy_tokens(raw_value)

        loaded: list[UpstreamProxy] = []
        seen = set()
        for token in tokens:
            parsed = cls._parse_proxy_line(
                line=token,
                default_scheme="socks5",
                source_url="paid:env",
            )
            if not parsed:
                continue
            key = parsed.to_url()
            if key in seen:
                continue
            seen.add(key)
            loaded.append(parsed)

        cls._paid_proxies = loaded
        cls._last_paid_reload_at = time.time()
        return list(cls._paid_proxies)

    @classmethod
    async def _check_country_ru(
        cls,
        session: aiohttp.ClientSession,
        cache_key: str,
        force: bool = False,
    ) -> tuple[bool, str]:
        now = time.time()
        if not force:
            cached = cls._geo_cache.get(cache_key)
            if cached and (now - cached[1]) <= cls.GEO_CACHE_TTL:
                return (True, "RU") if cached[0] else (False, "NOT_RU")

        try:
            async with session.get(cls.GEO_CHECK_URL, allow_redirects=True) as geo_resp:
                if geo_resp.status != 200:
                    cls._geo_cache[cache_key] = (False, time.time())
                    return False, f"GEO HTTP {geo_resp.status}"
                data = await geo_resp.json(content_type=None)
        except Exception as e:
            cls._geo_cache[cache_key] = (False, time.time())
            return False, f"GEO failed ({str(e)})"

        country = str(data.get("countryCode") or "").strip().upper()
        is_ru = country in cls.TARGET_COUNTRY_CODES
        cls._geo_cache[cache_key] = (is_ru, time.time())
        if is_ru:
            return True, "RU"
        return False, f"NOT_RU ({country or 'UNK'})"

    @classmethod
    def _normalize_scheme(cls, value: str, fallback: str = "socks5") -> str:
        scheme = str(value or fallback).strip().lower()
        if scheme in {"socks", "socks5h"}:
            return "socks5"
        if scheme.startswith("socks"):
            return "socks5"
        if scheme.startswith("http"):
            return "http"
        return "socks5"

    @classmethod
    def _parse_proxy_line(
        cls,
        line: str,
        default_scheme: str,
        source_url: str,
    ) -> Optional[UpstreamProxy]:
        raw = str(line or "").strip()
        if not raw or raw.startswith("#"):
            return None

        raw = raw.split("#", 1)[0].strip()
        if not raw:
            return None

        if "://" in raw:
            parsed = urlparse(raw)
            if not parsed.hostname or not parsed.port:
                return None
            scheme = cls._normalize_scheme(parsed.scheme, default_scheme)
            return UpstreamProxy(
                scheme=scheme,
                host=str(parsed.hostname),
                port=int(parsed.port),
                username=str(parsed.username or ""),
                password=str(parsed.password or ""),
                source=source_url,
            )

        parts = raw.split(":")
        if len(parts) not in {2, 4}:
            return None

        host = parts[0].strip()
        if not host:
            return None

        if not re.match(r"^[a-zA-Z0-9.-]+$", host):
            return None

        try:
            port = int(parts[1].strip())
        except Exception:
            return None

        if port < 1 or port > 65535:
            return None

        username = ""
        password = ""
        if len(parts) == 4:
            username = parts[2].strip()
            password = parts[3].strip()

        return UpstreamProxy(
            scheme=cls._normalize_scheme(default_scheme, default_scheme),
            host=host,
            port=port,
            username=username,
            password=password,
            source=source_url,
        )

    @classmethod
    async def _fetch_source(
        cls,
        session: aiohttp.ClientSession,
        default_scheme: str,
        source_url: str,
    ) -> list[UpstreamProxy]:
        try:
            async with session.get(source_url, allow_redirects=True) as resp:
                if resp.status != 200:
                    return []
                text = await resp.text(errors="ignore")
        except Exception:
            return []

        parsed: list[UpstreamProxy] = []
        for line in text.splitlines():
            proxy = cls._parse_proxy_line(
                line=line,
                default_scheme=default_scheme,
                source_url=source_url,
            )
            if proxy:
                parsed.append(proxy)
            if len(parsed) >= cls.MAX_CANDIDATES_PER_SOURCE:
                break
        return parsed

    @classmethod
    async def _fetch_geonode_page(
        cls,
        session: aiohttp.ClientSession,
        page: int,
    ) -> list[UpstreamProxy]:
        url = cls.GEONODE_URL_TEMPLATE.format(
            limit=cls.GEONODE_PAGE_LIMIT,
            page=page,
            country=cls.GEONODE_COUNTRY_CODE,
        )
        try:
            async with session.get(url, allow_redirects=True) as resp:
                if resp.status != 200:
                    return []
                payload = await resp.json(content_type=None)
        except Exception:
            return []

        items = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(items, list):
            return []

        parsed: list[UpstreamProxy] = []
        for item in items:
            if not isinstance(item, dict):
                continue

            host = str(item.get("ip") or "").strip()
            port_raw = item.get("port")
            protocols = item.get("protocols") or []

            if not host or not port_raw:
                continue

            try:
                port = int(port_raw)
            except Exception:
                continue

            if port < 1 or port > 65535:
                continue

            if isinstance(protocols, list):
                protocol_values = [str(p).strip().lower() for p in protocols]
            else:
                protocol_values = []

            scheme = "socks5" if "socks5" in protocol_values else "http"
            parsed.append(
                UpstreamProxy(
                    scheme=scheme,
                    host=host,
                    port=port,
                    source=f"geonode:{page}",
                )
            )

        return parsed

    @classmethod
    async def _fetch_geonode_candidates(
        cls,
        session: aiohttp.ClientSession,
    ) -> list[UpstreamProxy]:
        tasks = [
            cls._fetch_geonode_page(session, page)
            for page in range(1, cls.GEONODE_PAGES + 1)
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        aggregated: list[UpstreamProxy] = []
        for item in results:
            if isinstance(item, Exception):
                continue
            aggregated.extend(item)
        return aggregated

    @classmethod
    async def _download_candidates(cls) -> list[UpstreamProxy]:
        async with aiohttp.ClientSession(
            timeout=cls.CANDIDATE_FETCH_TIMEOUT,
            cookie_jar=aiohttp.DummyCookieJar(),
        ) as session:
            tasks = [
                cls._fetch_source(session, scheme, url)
                for scheme, url in cls.SOURCE_URLS
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            geonode_candidates = await cls._fetch_geonode_candidates(session)

        dedup: dict[str, UpstreamProxy] = {}
        for item in results:
            if isinstance(item, Exception):
                continue
            for proxy in item:
                dedup.setdefault(proxy.to_url(), proxy)

        for proxy in geonode_candidates:
            dedup.setdefault(proxy.to_url(), proxy)

        return list(dedup.values())

    @classmethod
    async def _validate_candidate(cls, proxy: UpstreamProxy) -> Optional[UpstreamProxy]:
        proxy_url = proxy.to_url()
        connector = ProxyConnector.from_url(proxy_url, rdns=True)
        try:
            async with aiohttp.ClientSession(
                connector=connector,
                timeout=cls.PROXY_VALIDATE_TIMEOUT,
                cookie_jar=aiohttp.DummyCookieJar(),
            ) as session:
                health_ok = False
                for url in cls.HEALTH_CHECK_URLS:
                    try:
                        async with session.get(url, allow_redirects=True) as resp:
                            if resp.status in {200, 204, 301, 302, 307, 308}:
                                health_ok = True
                                break
                    except Exception:
                        continue

                if not health_ok:
                    return None

                geo_ok, _geo_reason = await cls._check_country_ru(
                    session=session,
                    cache_key=proxy_url,
                    force=True,
                )
                if not geo_ok:
                    return None

                return proxy
        except Exception:
            return None

    @classmethod
    async def _validate_candidates(cls, candidates: list[UpstreamProxy]) -> list[UpstreamProxy]:
        if not candidates:
            return []

        sem = asyncio.Semaphore(max(1, int(cls.VALIDATE_CONCURRENCY)))

        async def _guarded_validate(proxy: UpstreamProxy) -> Optional[UpstreamProxy]:
            async with sem:
                return await cls._validate_candidate(proxy)

        validated_raw = await asyncio.gather(
            *[_guarded_validate(proxy) for proxy in candidates],
            return_exceptions=True,
        )

        validated: list[UpstreamProxy] = []
        for item in validated_raw:
            if isinstance(item, UpstreamProxy):
                validated.append(item)
        return validated

    @classmethod
    async def refresh(cls, force: bool = False) -> int:
        now = time.time()
        if (
            not force
            and cls._proxies
            and (now - cls._last_refresh_at) < cls.REFRESH_INTERVAL_SEC
        ):
            return len(cls._proxies)

        async with cls._refresh_lock:
            now = time.time()
            if (
                not force
                and cls._proxies
                and (now - cls._last_refresh_at) < cls.REFRESH_INTERVAL_SEC
            ):
                return len(cls._proxies)

            paid_candidates = cls._load_paid_proxies(force=True)
            candidates = await cls._download_candidates()
            if paid_candidates:
                paid_urls = {proxy.to_url() for proxy in paid_candidates}
                merged = list(paid_candidates)
                merged.extend(
                    [proxy for proxy in candidates if proxy.to_url() not in paid_urls]
                )
                candidates = merged

            if not candidates:
                cls._last_refresh_at = time.time()
                logger.warning("ProxyPool refresh: no candidates downloaded")
                return len(cls._proxies)

            if len(candidates) > cls.MAX_VALIDATE_CANDIDATES:
                geonode_candidates = [
                    proxy for proxy in candidates if proxy.source.startswith("geonode:")
                ]
                other_candidates = [
                    proxy for proxy in candidates if not proxy.source.startswith("geonode:")
                ]

                if len(geonode_candidates) >= cls.MAX_VALIDATE_CANDIDATES:
                    candidates = random.sample(geonode_candidates, cls.MAX_VALIDATE_CANDIDATES)
                else:
                    remaining = cls.MAX_VALIDATE_CANDIDATES - len(geonode_candidates)
                    if len(other_candidates) > remaining:
                        other_candidates = random.sample(other_candidates, remaining)
                    candidates = geonode_candidates + other_candidates

            validated = await cls._validate_candidates(candidates)
            if not validated:
                cls._last_refresh_at = time.time()
                logger.warning(
                    "ProxyPool refresh: no RU proxies validated; keeping previous pool"
                )
                return len(cls._proxies)

            random.shuffle(validated)
            cls._proxies = validated[: cls.MAX_POOL_SIZE]
            cls._cursor = 0
            cls._last_refresh_at = time.time()

            keep_from = cls._last_refresh_at - cls.BAD_PROXY_COOLDOWN_SEC
            cls._bad_until = {
                key: ts for key, ts in cls._bad_until.items() if ts >= keep_from
            }
            cls._health_cache.clear()
            cls._geo_cache.clear()

            logger.info(
                "ProxyPool refresh complete: candidates=%s validated_ru=%s pool=%s paid=%s",
                len(candidates),
                len(validated),
                len(cls._proxies),
                len(paid_candidates),
            )
            return len(cls._proxies)

    @classmethod
    def _pick_candidate(cls) -> Optional[UpstreamProxy]:
        if not cls._proxies:
            return None

        now = time.time()
        total = len(cls._proxies)
        for _ in range(total):
            idx = cls._cursor % total
            cls._cursor += 1
            proxy = cls._proxies[idx]
            if cls._bad_until.get(proxy.to_url(), 0) > now:
                continue
            return proxy
        return None

    @classmethod
    def mark_bad(cls, proxy: UpstreamProxy, cooldown_sec: int | None = None):
        ttl = int(cooldown_sec or cls.BAD_PROXY_COOLDOWN_SEC)
        cls._bad_until[proxy.to_url()] = time.time() + max(20, ttl)
        cls._health_cache[proxy.to_url()] = (False, time.time())

    @classmethod
    async def probe_proxy(
        cls,
        proxy: UpstreamProxy,
        force: bool = False,
    ) -> tuple[bool, str]:
        cache_key = proxy.to_url()
        now = time.time()

        if str(proxy.source or "").startswith("paid:"):
            ok, err = await cls._quick_probe_paid_proxy(proxy)
            cls._health_cache[cache_key] = (bool(ok), time.time())
            if ok:
                return True, "OK"
            return False, err

        if not force:
            cached = cls._health_cache.get(cache_key)
            if cached and (now - cached[1]) <= cls.RUNTIME_HEALTH_CACHE_TTL:
                if cached[0]:
                    return True, "OK"
                return False, "Proxy cached as unhealthy"

        connector = ProxyConnector.from_url(cache_key, rdns=True)
        try:
            async with aiohttp.ClientSession(
                connector=connector,
                timeout=cls.PROXY_VALIDATE_TIMEOUT,
                cookie_jar=aiohttp.DummyCookieJar(),
            ) as session:
                health_ok = False
                for url in cls.HEALTH_CHECK_URLS:
                    try:
                        async with session.get(url, allow_redirects=True) as resp:
                            if resp.status in {200, 204, 301, 302, 307, 308}:
                                health_ok = True
                                break
                    except Exception:
                        continue

                if not health_ok:
                    cls._health_cache[cache_key] = (False, time.time())
                    return False, "Proxy health check failed"

                geo_ok, geo_reason = await cls._check_country_ru(
                    session=session,
                    cache_key=cache_key,
                    force=force,
                )
                if not geo_ok:
                    cls._health_cache[cache_key] = (False, time.time())
                    return False, f"Proxy geo check failed ({geo_reason})"

            cls._health_cache[cache_key] = (True, time.time())
            return True, "OK"
        except asyncio.TimeoutError:
            cls._health_cache[cache_key] = (False, time.time())
            return False, "Proxy timeout"
        except Exception as e:
            cls._health_cache[cache_key] = (False, time.time())
            return False, f"Proxy connection failed ({str(e)})"

    @classmethod
    async def acquire_working_proxy(
        cls,
        max_attempts: int = 8,
    ) -> tuple[Optional[UpstreamProxy], str]:
        paid_proxies = cls._load_paid_proxies(force=False)
        if paid_proxies:
            for proxy in paid_proxies:
                ok, _probe_err = await cls._quick_probe_paid_proxy(proxy)
                if ok:
                    return proxy, "OK"

            return None, "SYS_ERR: RU Paid Proxy Unreachable"

        now = time.time()
        if not cls._proxies:
            if cls._refresh_lock.locked():
                return None, "SYS_ERR: RU Proxy Refresh In Progress"
            if (now - cls._last_refresh_at) >= cls.REFRESH_INTERVAL_SEC:
                await cls.refresh(force=True)
        elif (now - cls._last_refresh_at) >= cls.REFRESH_INTERVAL_SEC:
            if not cls._refresh_lock.locked():
                await cls.refresh(force=False)

        if not cls._proxies:
            return None, "SYS_ERR: RU Proxy Pool Empty"

        attempts = max(1, int(max_attempts))
        for _ in range(attempts):
            candidate = cls._pick_candidate()
            if not candidate:
                break

            ok, _probe_err = await cls.probe_proxy(candidate)
            if ok:
                return candidate, "OK"

            cls.mark_bad(candidate)

        if not cls._refresh_lock.locked() and (time.time() - cls._last_refresh_at) >= 60:
            try:
                asyncio.create_task(cls.refresh(force=True))
            except Exception:
                pass

        return None, "SYS_ERR: RU Proxy Pool Exhausted"

    @classmethod
    def get_stats(cls) -> dict:
        now = time.time()
        bad_now = 0
        for _, until_ts in cls._bad_until.items():
            if until_ts > now:
                bad_now += 1

        return {
            "pool_size": len(cls._proxies),
            "paid_count": len(cls._paid_proxies),
            "bad_now": bad_now,
            "last_refresh_at": int(cls._last_refresh_at or 0),
        }

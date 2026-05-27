import aiohttp
import asyncio
import base64
import logging
import re
import time
from typing import List
from urllib.parse import quote, urlparse

from database.repo import SubRepo, SourceRepo
from utils.checker import VlessChecker
from utils.batch_processor import CpuAdaptiveProcessor
from utils.parser import LinkParser
from config import config

logger = logging.getLogger("Collector")

FIXED_SOURCE_URLS = [
    "https://github.com/igareck/vpn-configs-for-russia/blob/main/Vless-Reality-White-Lists-Rus-Mobile-2.txt",
    "https://github.com/igareck/vpn-configs-for-russia/blob/main/Vless-Reality-White-Lists-Rus-Mobile.txt",
    "https://gist.githubusercontent.com/pythoneer-dev-q/dd66ec52d2a44084a957ba7f4dc33cd0/raw/wifi.txt",
    "https://gist.githubusercontent.com/pythoneer-dev-q/49c33dd8d4e279611e30a8c6fd938230/raw/mobile.txt",
    "https://raw.githubusercontent.com/kort0881/vpn-checker-backend/main/checked/RU_Best/ru_white_part1.txt",
    "https://raw.githubusercontent.com/kort0881/vpn-checker-backend/main/checked/RU_Best/ru_white_all_part1.txt",
    "https://raw.githubusercontent.com/kort0881/vpn-checker-backend/main/checked/My_Euro/my_euro_part1.txt",
    "https://raw.githubusercontent.com/kort0881/vpn-checker-backend/main/checked/My_Euro/my_euro_part2.txt",
    "https://raw.githubusercontent.com/kort0881/vpn-checker-backend/main/checked/My_Euro/my_euro_part3.txt",
    "https://raw.githubusercontent.com/kort0881/vpn-checker-backend/main/checked/My_Euro/my_euro_all_part1.txt",
    "https://raw.githubusercontent.com/kort0881/vpn-checker-backend/main/checked/My_Euro/my_euro_all_part2.txt",
    "https://raw.githubusercontent.com/kort0881/vpn-checker-backend/main/checked/My_Euro/my_euro_all_part3.txt",
    "https://raw.githubusercontent.com/kort0881/vpn-checker-backend/main/checked/RU_Best/ru_white_all_WHITE.txt",
    "https://raw.githubusercontent.com/kort0881/vpn-checker-backend/main/checked/My_Euro/my_euro_all_WHITE.txt",
    "https://raw.githubusercontent.com/kort0881/sbornik-vless/refs/heads/main/subs/vless_001.txt",
    "https://raw.githubusercontent.com/kort0881/sbornik-vless/refs/heads/main/subs/vless_002.txt",
    "https://raw.githubusercontent.com/kort0881/sbornik-vless/refs/heads/main/subs/vless_003.txt",
    "https://raw.githubusercontent.com/kort0881/sbornik-vless/refs/heads/main/subs/vless_004.txt",
    "https://raw.githubusercontent.com/kort0881/sbornik-vless/refs/heads/main/subs/vless_005.txt",
    "https://raw.githubusercontent.com/kort0881/sbornik-vless/refs/heads/main/subs/vless_006.txt",
    "https://raw.githubusercontent.com/kort0881/sbornik-vless/refs/heads/main/subs/vless_007.txt",
    "https://raw.githubusercontent.com/kort0881/sbornik-vless/refs/heads/main/subs/vless_008.txt",
    "https://raw.githubusercontent.com/kort0881/sbornik-vless/refs/heads/main/subs/vless_009.txt",
    "https://raw.githubusercontent.com/kort0881/sbornik-vless/refs/heads/main/subs/vless_010.txt",
    "https://raw.githubusercontent.com/Surfboardv2ray/TGParse/main/configtg.txt",
    "https://raw.githubusercontent.com/MustafaBaqer/VestraNet-Nodes/main/protocols/vless.txt",
    "https://raw.githubusercontent.com/R3ZARAHIMI/tg-v2ray-configs-every2h/main/Original-Configs.txt",
    "https://raw.githubusercontent.com/MohsenReyhani/vless-subscriptions/main/sub.txt",
    "https://raw.githubusercontent.com/Epodonios/v2ray-configs/refs/heads/main/Sub1.txt",
    "https://raw.githubusercontent.com/Epodonios/v2ray-configs/refs/heads/main/Sub2.txt",
    "https://raw.githubusercontent.com/Epodonios/v2ray-configs/refs/heads/main/Sub5.txt",
    "https://raw.githubusercontent.com/sevcator/5ubscrpt10n/main/protocols/vl.txt",
    "https://raw.githubusercontent.com/ShatakVPN/ConfigForge-V2Ray/main/configs/vless.txt",
    "https://raw.githubusercontent.com/kort0881/vpn-vless-configs-russia/main/githubmirror/clean/vless.txt",
    "https://raw.githubusercontent.com/MrTelepathic/v2ray-sub/refs/heads/main/configs.txt",
    "https://raw.githubusercontent.com/ALIILAPRO/v2rayNG-Config/main/sub.txt",
    "https://raw.githubusercontent.com/LuisF-92/Freedom-V2Ray/main/configs/vless.txt",
    "https://raw.githubusercontent.com/V2RayRoot/V2RayConfig/main/Config/vless.txt",
    "https://raw.githubusercontent.com/hamedcode/port-based-v2ray-configs/main/sub/vless.txt",
    "https://raw.githubusercontent.com/F0rc3Run/F0rc3Run/refs/heads/main/splitted-by-protocol/vless.txt",
    "https://raw.githubusercontent.com/barry-far/V2ray-config/main/Splitted-By-Protocol/vless.txt",
    "https://raw.githubusercontent.com/Argh94/V2RayAutoConfig/refs/heads/main/configs/Vless.txt",
    "https://raw.githubusercontent.com/poommin2543/v2ray-configsNew/refs/heads/main/Sub1.txt",
    "https://raw.githubusercontent.com/poommin2543/v2ray-configsNew/refs/heads/main/Sub2.txt",
    "https://raw.githubusercontent.com/poommin2543/v2ray-configsNew/refs/heads/main/Sub3.txt",
    "https://raw.githubusercontent.com/mohamadfg-dev/telegram-v2ray-configs-collector/refs/heads/main/category/vless.txt",
    "https://raw.githubusercontent.com/MatinGhanbari/v2ray-configs/main/subscriptions/filtered/subs/hysteria2.txt",
    "https://raw.githubusercontent.com/MustafaBaqer/VestraNet-Nodes/main/protocols/hy2.txt",
    "https://raw.githubusercontent.com/ShatakVPN/ConfigForge-V2Ray/main/configs/hysteria2.txt",
    "https://raw.githubusercontent.com/Argh94/V2RayAutoConfig/refs/heads/main/configs/Hysteria2.txt",
    "https://raw.githubusercontent.com/MustafaBaqer/VestraNet-Nodes/main/protocols/tuic.txt",
    "https://raw.githubusercontent.com/Argh94/V2RayAutoConfig/refs/heads/main/configs/Tuic.txt",
    "https://raw.githubusercontent.com/ninjastrikers/v2ray-configs/main/splitted/tuic.txt",
]

DEFAULT_SOURCES = [
    *FIXED_SOURCE_URLS,
]


class SubscriptionCollector:
    MAX_LINKS_PER_BATCH = 40000
    MIN_ACCEPT_SPEED_MBPS = 1.0
    MAX_ACCEPT_JITTER_MS = 20
    JITTER_TIMEOUT_SEC = 2.4
    JITTER_SAMPLES = 4

    FETCH_CONNECTOR_LIMIT = 40

    CHECK_INITIAL_WORKERS = 40
    CHECK_MIN_WORKERS = 20
    CHECK_MAX_WORKERS = 120
    CHECK_TARGET_CPU = 92.0
    CHECK_TARGET_RAM = 88.0

    RU_CHAIN_CHECK_INITIAL_WORKERS = 16
    RU_CHAIN_CHECK_MIN_WORKERS = 10
    RU_CHAIN_CHECK_MAX_WORKERS = 32
    RU_CHAIN_CHECK_TARGET_CPU = 75.0
    RU_CHAIN_CHECK_TARGET_RAM = 82.0

    BLOCKED_HOSTS = {
        "in-pl-hn.ray-proxy.ru",
    }
    JAPAN_KEYWORDS = (
        "japan",
        "tokyo",
        "osaka",
        "nagoya",
        "sapporo",
        "fukuoka",
        "yokohama",
        "nippon",
        "nihon",
        "япони",
        "япон",
    )
    _GITHUB_TREE_CACHE_TTL = 600
    _github_tree_cache = {}

    @classmethod
    def _has_japan_hint(cls, value: str) -> bool:
        text = str(value or "").strip().lower()
        if not text:
            return False

        if any(keyword in text for keyword in cls.JAPAN_KEYWORDS):
            return True

        return bool(re.search(r"(^|[\s._\-/])jp([\s._\-/]|$)", text))

    @classmethod
    def _japan_priority_score(cls, link: str) -> int:
        parsed = LinkParser.parse_vless(link)
        if not parsed:
            raw = str(link or "").lower()
            score = 0
            if "%f0%9f%87%af%f0%9f%87%b5" in raw:
                score += 25
            if cls._has_japan_hint(raw):
                score += 20
            return score

        score = 0
        name = str(parsed.get("name", "") or "")
        server = str(parsed.get("server", "") or "")
        sni = str(parsed.get("sni", "") or "")
        host = str(parsed.get("host", "") or "")
        service_name = str(parsed.get("serviceName", "") or "")

        if cls._has_japan_hint(name):
            score += 55
        if cls._has_japan_hint(server):
            score += 35
        if cls._has_japan_hint(sni):
            score += 25
        if cls._has_japan_hint(host):
            score += 20
        if cls._has_japan_hint(service_name):
            score += 15

        if str(server).strip().lower().endswith(".jp"):
            score += 15

        return score

    @classmethod
    async def run_collection(cls) -> dict:
        db_sources = await SourceRepo.get_enabled_urls()
        fixed_sources_total = len(FIXED_SOURCE_URLS)
        allowed_sources_set = set(FIXED_SOURCE_URLS)
        allowed_db_sources = [
            url
            for url in db_sources
            if url in allowed_sources_set
        ]
        ignored_db_sources = [
            url
            for url in db_sources
            if url not in allowed_sources_set
        ]
        base_sources = list(dict.fromkeys(DEFAULT_SOURCES + allowed_db_sources))

        source_meta = {
            "fixed_sources_total": fixed_sources_total,
            "custom_sources_enabled": len(db_sources),
            "custom_sources_accepted": len(allowed_db_sources),
            "custom_sources_ignored": len(ignored_db_sources),
        }

        connector = aiohttp.TCPConnector(limit=cls.FETCH_CONNECTOR_LIMIT)

        async with aiohttp.ClientSession(connector=connector) as session:
            expanded_tasks = [
                cls._expand_source_url(session, source_url)
                for source_url in base_sources
            ]
            expanded_results = await asyncio.gather(
                *expanded_tasks, return_exceptions=True
            )

            all_sources = []
            for source_url, expanded in zip(base_sources, expanded_results):
                if isinstance(expanded, Exception):
                    logger.warning(f"Source expansion failed for {source_url}: {expanded}")
                    all_sources.append(source_url)
                    continue

                if expanded:
                    all_sources.extend(expanded)
                else:
                    all_sources.append(source_url)

            all_sources = list(dict.fromkeys(all_sources))
            tasks = [cls._fetch_url(session, url) for url in all_sources]
            results = await asyncio.gather(*tasks, return_exceptions=True)

        source_meta["sources_used"] = len(all_sources)
        source_meta["custom_sources_used"] = len(allowed_db_sources)

        valid_results = [r for r in results if isinstance(r, str) and len(r) > 10]

        combined_text = "\n".join(valid_results)
        del valid_results

        decoded_content = cls._try_decode(combined_text)
        full_text = combined_text + "\n" + decoded_content
        del combined_text, decoded_content

        found_links = re.findall(r'(?:vless|trojan|hy2|hysteria2|tuic)://[^\s\'"<>]+', full_text)
        found_links = list(set(found_links))
        del full_text

        if not found_links:
            return {
                "processed": 0,
                "added": 0,
                "rejected": 0,
                "region_stats": {},
                "rejected_reasons": {},
                "discovered": 0,
                "already_known": 0,
                **source_meta,
            }

        unique_links = [l.strip() for l in found_links if l and l.strip()]
        unique_links = list(dict.fromkeys(unique_links))
        del found_links

        if not unique_links:
            return {
                "processed": 0,
                "added": 0,
                "rejected": 0,
                "region_stats": {},
                "rejected_reasons": {},
                "discovered": 0,
                "already_known": 0,
                **source_meta,
            }

        discovered_total = len(unique_links)

        existing_keys = await SubRepo.get_all_keys_set()
        unique_links = [link for link in unique_links if link not in existing_keys]

        already_known = max(0, discovered_total - len(unique_links))

        if not unique_links:
            return {
                "processed": 0,
                "added": 0,
                "rejected": 0,
                "region_stats": {},
                "rejected_reasons": {},
                "discovered": discovered_total,
                "already_known": already_known,
                **source_meta,
            }

        _addr_re = re.compile(r'@([^@:/?#\s]+):\d+', re.ASCII)

        def _extract_server_addr(link: str) -> str:
            m = _addr_re.search(link)
            return m.group(1).strip().lower() if m else ""

        known_servers: set[str] = set()
        for key in existing_keys:
            srv = _extract_server_addr(key)
            if srv:
                known_servers.add(srv)

        batch_seen_servers: set[str] = set()
        server_deduped: list[str] = []
        for link in unique_links:
            srv = _extract_server_addr(link)
            if not srv:
                server_deduped.append(link)
                continue
            if srv in known_servers or srv in batch_seen_servers:
                already_known += 1
                continue
            batch_seen_servers.add(srv)
            server_deduped.append(link)
        unique_links = server_deduped

        if not unique_links:
            return {
                "processed": 0,
                "added": 0,
                "rejected": 0,
                "region_stats": {},
                "rejected_reasons": {},
                "discovered": discovered_total,
                "already_known": already_known,
                **source_meta,
            }

        scored_links = [
            (cls._japan_priority_score(link), link)
            for link in unique_links
        ]
        scored_links.sort(key=lambda item: item[0], reverse=True)
        unique_links = [link for _, link in scored_links]
        source_meta["japan_priority_candidates"] = sum(
            1 for score, _ in scored_links if score > 0
        )

        if len(unique_links) > cls.MAX_LINKS_PER_BATCH:
            unique_links = unique_links[: cls.MAX_LINKS_PER_BATCH]

        result = await cls._check_and_add_batch(unique_links)
        result["discovered"] = discovered_total
        result["already_known"] = already_known
        result.update(source_meta)
        return result

    @staticmethod
    def _parse_github_tree_url(url: str) -> tuple[str, str, str, str] | None:
        parsed = urlparse(url)
        host = parsed.netloc.lower()
        if host not in {"github.com", "www.github.com"}:
            return None

        parts = [part for part in parsed.path.strip("/").split("/") if part]
        if len(parts) < 4:
            return None

        owner = parts[0]
        repo = parts[1]
        marker = parts[2].lower()

        if marker != "tree":
            return None

        branch = parts[3]
        sub_path = "/".join(parts[4:])
        return owner, repo, branch, sub_path

    @classmethod
    async def _expand_source_url(
        cls, session: aiohttp.ClientSession, source_url: str
    ) -> list[str]:
        github_tree = cls._parse_github_tree_url(source_url)
        if not github_tree:
            return [source_url]

        cached = cls._github_tree_cache.get(source_url)
        now = time.time()
        if cached and (now - cached["ts"]) < cls._GITHUB_TREE_CACHE_TTL:
            return cached["urls"]

        owner, repo, branch, root_path = github_tree
        txt_urls = await cls._discover_github_txt_urls(
            session=session,
            owner=owner,
            repo=repo,
            branch=branch,
            root_path=root_path,
        )

        if txt_urls:
            cls._github_tree_cache[source_url] = {"ts": now, "urls": txt_urls}
            logger.info(
                f"Expanded GitHub tree source {source_url} into {len(txt_urls)} txt files"
            )
            return txt_urls

        logger.warning(f"No txt files found for GitHub tree source: {source_url}")
        return [source_url]

    @staticmethod
    async def _discover_github_txt_urls(
        session: aiohttp.ClientSession,
        owner: str,
        repo: str,
        branch: str,
        root_path: str,
    ) -> list[str]:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
            "Accept": "application/vnd.github+json",
        }
        timeout = aiohttp.ClientTimeout(total=25, connect=10)

        pending_paths = [root_path.strip("/")] if root_path else [""]
        seen_paths = set()
        found_urls = []

        while pending_paths:
            current_path = pending_paths.pop()
            if current_path in seen_paths:
                continue
            seen_paths.add(current_path)

            encoded_path = quote(current_path, safe="/")
            if encoded_path:
                api_url = (
                    f"https://api.github.com/repos/{owner}/{repo}/contents/{encoded_path}"
                )
            else:
                api_url = f"https://api.github.com/repos/{owner}/{repo}/contents"

            try:
                async with session.get(
                    api_url,
                    headers=headers,
                    params={"ref": branch},
                    timeout=timeout,
                ) as resp:
                    if resp.status != 200:
                        logger.warning(
                            f"GitHub API returned {resp.status} for {api_url}"
                        )
                        continue

                    payload = await resp.json(content_type=None)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.warning(f"GitHub txt discovery failed for {api_url}: {e}")
                continue

            items = payload if isinstance(payload, list) else [payload]
            for item in items:
                if not isinstance(item, dict):
                    continue

                item_type = item.get("type")
                item_path = item.get("path")

                if item_type == "dir" and item_path:
                    pending_paths.append(item_path)
                    continue

                if item_type != "file":
                    continue

                file_name = (item.get("name") or "").lower()
                if not file_name.endswith(".txt"):
                    continue

                download_url = item.get("download_url")
                if download_url:
                    found_urls.append(download_url)

        return list(dict.fromkeys(found_urls))

    @classmethod
    async def _check_and_add_batch(cls, links: List[str]) -> dict:
        added_count = 0
        failed_count = 0
        region_stats = {}
        rejected_reasons = {
            "dead": 0,
            "high_jitter": 0,
            "blocked_host": 0,
            "dup_or_bl": 0,
            "fmt_err": 0,
            "sys_err": 0,
        }

        use_ru_chain = bool(getattr(config, "CHECKER_USE_RU_PROXY_CHAIN", True))
        if use_ru_chain:
            processor = CpuAdaptiveProcessor(
                initial_workers=cls.RU_CHAIN_CHECK_INITIAL_WORKERS,
                min_workers=cls.RU_CHAIN_CHECK_MIN_WORKERS,
                max_workers=cls.RU_CHAIN_CHECK_MAX_WORKERS,
                target_cpu=cls.RU_CHAIN_CHECK_TARGET_CPU,
                target_ram=cls.RU_CHAIN_CHECK_TARGET_RAM,
            )
        else:
            processor = CpuAdaptiveProcessor(
                initial_workers=cls.CHECK_INITIAL_WORKERS,
                min_workers=cls.CHECK_MIN_WORKERS,
                max_workers=cls.CHECK_MAX_WORKERS,
                target_cpu=cls.CHECK_TARGET_CPU,
                target_ram=cls.CHECK_TARGET_RAM,
            )

        _hy2_addr_re = re.compile(r'(?:hy2|hysteria2)://[^@]*@([^:/?#\s]+):(\d+)', re.ASCII)
        _tuic_addr_re = re.compile(r'tuic://[^@]*@([^:/?#\s]+):(\d+)', re.ASCII)

        async def process_link(link: str):
            try:
                scheme = link.split("://", 1)[0].lower() if "://" in link else ""

                if scheme == "tuic":
                    m = _tuic_addr_re.match(link)
                    if not m:
                        return False, "fmt_err"

                    host = m.group(1).strip().lower()
                    port = int(m.group(2))
                    if not host or port < 1 or port > 65535:
                        return False, "fmt_err"

                    if host in cls.BLOCKED_HOSTS:
                        return False, "blocked_host"

                    (
                        is_alive,
                        region,
                        latency,
                        speed_mbps,
                        ai_avail,
                        no_ads,
                        err,
                        updated_link,
                    ) = await VlessChecker.process_subscription(
                        link,
                        strict_speed=False,
                        skip_speed=False,
                    )

                    if not is_alive:
                        err_text = str(err or "")
                        if err_text.startswith("SYS_ERR"):
                            return False, "sys_err"
                        return False, "dead"

                    final_region = str(region or "").strip() or "🌍 UNK"
                    try:
                        final_latency = int(latency or 9999)
                    except Exception:
                        final_latency = 9999
                    final_speed = float(speed_mbps or 0.0)
                    if final_speed <= 1.05:
                        final_speed = 30.0

                    added = await SubRepo.smart_add_subscription(
                        vless_key=updated_link if updated_link else link,
                        region=final_region,
                        latency=final_latency,
                        speed_mbps=final_speed,
                        ai_available=bool(ai_avail),
                        no_ads=bool(no_ads),
                    )

                    if added:
                        return True, {"region": final_region}
                    return False, "dup_or_bl"

                if scheme in ("hy2", "hysteria2"):
                    m = _hy2_addr_re.match(link)
                    if not m:
                        return False, "fmt_err"

                    host = m.group(1).strip().lower()
                    port = int(m.group(2))
                    if not host or port < 1 or port > 65535:
                        return False, "fmt_err"

                    if host in cls.BLOCKED_HOSTS:
                        return False, "blocked_host"

                    (
                        is_alive,
                        region,
                        latency,
                        speed_mbps,
                        ai_avail,
                        no_ads,
                        err,
                        updated_link,
                    ) = await VlessChecker.process_subscription(
                        link,
                        strict_speed=False,
                        skip_speed=False,
                    )

                    if not is_alive:
                        err_text = str(err or "")
                        if err_text.startswith("SYS_ERR"):
                            return False, "sys_err"
                        return False, "dead"

                    final_region = str(region or "").strip() or "🌍 UNK"
                    try:
                        final_latency = int(latency or 9999)
                    except Exception:
                        final_latency = 9999
                    final_speed = float(speed_mbps or 0.0)
                    if final_speed <= 1.05:
                        final_speed = 30.0

                    added = await SubRepo.smart_add_subscription(
                        vless_key=updated_link if updated_link else link,
                        region=final_region,
                        latency=final_latency,
                        speed_mbps=final_speed,
                        ai_available=bool(ai_avail),
                        no_ads=bool(no_ads),
                    )

                    if added:
                        return True, {"region": final_region}
                    return False, "dup_or_bl"

                if scheme == "trojan":
                    _trojan_addr_re = re.compile(r'trojan://[^@]*@([^:/?#\s]+):(\d+)', re.ASCII)
                    m = _trojan_addr_re.match(link)
                    if not m:
                        return False, "fmt_err"

                    host = m.group(1).strip().lower()
                    port = int(m.group(2))
                    if not host or port < 1 or port > 65535:
                        return False, "fmt_err"

                    if host in cls.BLOCKED_HOSTS:
                        return False, "blocked_host"

                    (
                        is_alive,
                        region,
                        latency,
                        speed_mbps,
                        ai_avail,
                        no_ads,
                        err,
                        updated_link,
                    ) = await VlessChecker.process_subscription(
                        link,
                        strict_speed=False,
                        skip_speed=False,
                    )

                    if not is_alive:
                        err_text = str(err or "")
                        if err_text.startswith("SYS_ERR"):
                            return False, "sys_err"
                        return False, "dead"

                    final_region = str(region or "").strip() or "🌍 UNK"
                    try:
                        final_latency = int(latency or 9999)
                    except Exception:
                        final_latency = 9999
                    final_speed = float(speed_mbps or 0.0)
                    if final_speed <= 1.05:
                        final_speed = 30.0

                    added = await SubRepo.smart_add_subscription(
                        vless_key=updated_link if updated_link else link,
                        region=final_region,
                        latency=final_latency,
                        speed_mbps=final_speed,
                        ai_available=bool(ai_avail),
                        no_ads=bool(no_ads),
                    )

                    if added:
                        return True, {"region": final_region}
                    return False, "dup_or_bl"

                if "vless://" not in link or "@" not in link or ":" not in link:
                    return False, "fmt_err"

                parsed = LinkParser.parse_vless(link)
                if not parsed:
                    return False, "fmt_err"

                host = str(parsed.get("server", "") or "").strip().lower()
                if host in cls.BLOCKED_HOSTS:
                    return False, "blocked_host"

                (
                    is_alive,
                    region,
                    latency,
                    speed_mbps,
                    ai_avail,
                    no_ads,
                    err,
                    updated_link,
                ) = await VlessChecker.process_subscription(
                    link,
                    strict_speed=False,
                    skip_speed=True,
                )

                if (not is_alive) and str(err or "").startswith("SYS_ERR"):
                    await asyncio.sleep(0.12)
                    (
                        is_alive,
                        region,
                        latency,
                        speed_mbps,
                        ai_avail,
                        no_ads,
                        err,
                        updated_link,
                    ) = await VlessChecker.process_subscription(
                        link,
                        strict_speed=False,
                        skip_speed=True,
                    )

                is_standard_err = err and any(
                    f"Factor {i}" in str(err) for i in range(0, 7)
                )

                if not is_alive:
                    err_text = str(err or "")
                    if err_text.startswith("SYS_ERR") or not is_standard_err:
                        return False, "sys_err"
                    return False, "dead"

                final_region = str(region or "").strip() or "🌍 UNK"

                try:
                    final_latency = int(latency or 9999)
                except Exception:
                    final_latency = 9999

                final_speed = float(speed_mbps or 0.0)
                if final_speed <= 1.05:
                    final_speed = 30.0

                final_ai = bool(ai_avail)
                final_no_ads = bool(no_ads)
                final_link = updated_link if updated_link else link

                jitter_parsed = LinkParser.parse_vless(final_link)
                if not jitter_parsed:
                    return False, "fmt_err"

                jitter_host = str(jitter_parsed.get("server", "") or "").strip()
                jitter_port = int(jitter_parsed.get("port", 0) or 0)
                if not jitter_host or jitter_port < 1 or jitter_port > 65535:
                    return False, "fmt_err"

                jitter_ok, jitter_ms, jitter_err = await VlessChecker.measure_tcp_jitter(
                    host=jitter_host,
                    port=jitter_port,
                    samples=cls.JITTER_SAMPLES,
                    timeout=cls.JITTER_TIMEOUT_SEC,
                )
                if (not jitter_ok) and (not str(jitter_err or "").startswith("Factor 1")):
                    await asyncio.sleep(0.08)
                    jitter_ok, jitter_ms, jitter_err = await VlessChecker.measure_tcp_jitter(
                        host=jitter_host,
                        port=jitter_port,
                        samples=cls.JITTER_SAMPLES,
                        timeout=cls.JITTER_TIMEOUT_SEC,
                    )

                if not jitter_ok:
                    if str(jitter_err or "").startswith("Factor 1"):
                        return False, "dead"
                    return False, "sys_err"

                if int(jitter_ms) > cls.MAX_ACCEPT_JITTER_MS:
                    return False, "high_jitter"

                if final_speed < cls.MIN_ACCEPT_SPEED_MBPS:
                    return False, "dead"

                added = await SubRepo.smart_add_subscription(
                    vless_key=final_link,
                    region=final_region,
                    latency=final_latency,
                    speed_mbps=final_speed,
                    ai_available=final_ai,
                    no_ads=final_no_ads,
                )

                if added:
                    return True, {"region": final_region}
                return False, "dup_or_bl"

            except asyncio.CancelledError:
                raise
            except Exception:
                return False, "sys_err"

        result = await processor.process(
            items=links, process_func=process_link, on_progress=None
        )

        for item in result.items:
            if item["success"]:
                added_count += 1
                res_data = item["result"]
                reg = res_data.get("region", "UNK")

                if reg not in region_stats:
                    region_stats[reg] = 0
                region_stats[reg] += 1
            else:
                failed_count += 1
                reason = item["result"]
                if reason in rejected_reasons:
                    rejected_reasons[reason] += 1
                else:
                    rejected_reasons["sys_err"] += 1

        return {
            "processed": len(links),
            "added": added_count,
            "rejected": failed_count,
            "region_stats": region_stats,
            "rejected_reasons": rejected_reasons,
        }

    @staticmethod
    async def _fetch_url(session: aiohttp.ClientSession, url: str) -> str:
        try:
            if "github.com" in url and "/blob/" in url:
                url = url.replace("/blob/", "/raw/")

            cache_buster = (
                f"&t={int(time.time())}" if "?" in url else f"?t={int(time.time())}"
            )
            fetch_url = url + cache_buster

            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

            timeout = aiohttp.ClientTimeout(total=20, connect=10)

            async with session.get(fetch_url, headers=headers, timeout=timeout) as resp:
                if resp.status == 200:
                    content = await resp.read()
                    if len(content) > 10 * 1024 * 1024:
                        content = content[: 10 * 1024 * 1024]
                    return content.decode("utf-8", errors="ignore")
        except asyncio.CancelledError:
            raise
        except Exception:
            pass
        return ""

    @staticmethod
    def _try_decode(text: str) -> str:
        if not text:
            return ""
        decoded_parts = []

        lines = text.replace(",", "\n").splitlines()
        for line in lines:
            line = line.strip()
            if not line or "://" in line:
                continue
            try:
                pad = len(line) % 4
                if pad:
                    line += "=" * (4 - pad)

                dec = None
                try:
                    dec = base64.b64decode(line).decode("utf-8", errors="ignore")
                except:
                    pass
                if not dec or not any(p in dec for p in ("vless://", "trojan://", "hy2://", "hysteria2://", "tuic://")):
                    try:
                        dec = base64.urlsafe_b64decode(line).decode(
                            "utf-8", errors="ignore"
                        )
                    except:
                        pass

                if dec and any(p in dec for p in ("vless://", "trojan://", "hy2://", "hysteria2://", "tuic://")):
                    decoded_parts.append(dec)
            except Exception:
                pass

        if not decoded_parts:
            try:
                clean_text = re.sub(r"\s+", "", text)
                pad = len(clean_text) % 4
                if pad:
                    clean_text += "=" * (4 - pad)

                dec = None
                try:
                    dec = base64.b64decode(clean_text).decode("utf-8", errors="ignore")
                except:
                    pass
                if not dec or not any(p in dec for p in ("vless://", "trojan://", "hy2://", "hysteria2://", "tuic://")):
                    try:
                        dec = base64.urlsafe_b64decode(clean_text).decode(
                            "utf-8", errors="ignore"
                        )
                    except:
                        pass

                if dec:
                    decoded_parts.extend(re.findall(r'(?:vless|trojan|hy2|hysteria2|tuic)://[^\s\'"<>]+', dec))
            except Exception:
                pass

        return "\n".join(decoded_parts)

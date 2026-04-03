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
]

DEFAULT_SOURCES = [
    *FIXED_SOURCE_URLS,
]


class SubscriptionCollector:
    MAX_LINKS_PER_BATCH = 40000
    MIN_ACCEPT_SPEED_MBPS = 1.0
    BLOCKED_HOSTS = {
        "in-pl-hn.ray-proxy.ru",
    }
    _GITHUB_TREE_CACHE_TTL = 600
    _github_tree_cache = {}

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

        connector = aiohttp.TCPConnector(limit=15)

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

        found_links = re.findall(r'vless://[^\s\'"<>]+', full_text)
        found_links = list(set(found_links))
        del full_text

        reset_deleted = await SubRepo.delete_all_subs()

        if not found_links:
            return {
                "processed": 0,
                "added": 0,
                "rejected": 0,
                "region_stats": {},
                "rejected_reasons": {},
                "reset_deleted": reset_deleted,
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
                "reset_deleted": reset_deleted,
                **source_meta,
            }

        if len(unique_links) > cls.MAX_LINKS_PER_BATCH:
            unique_links = unique_links[: cls.MAX_LINKS_PER_BATCH]

        result = await cls._check_and_add_batch(unique_links)
        result["reset_deleted"] = reset_deleted
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
            "blocked_host": 0,
            "dup_or_bl": 0,
            "fmt_err": 0,
            "sys_err": 0,
        }

        processor = CpuAdaptiveProcessor(
            initial_workers=15,
            min_workers=10,
            max_workers=40,
            target_cpu=80.0,
            target_ram=80.0,
        )

        async def process_link(link: str):
            try:
                if "vless://" not in link or "@" not in link or ":" not in link:
                    return False, "fmt_err"

                parsed = LinkParser.parse_vless(link)
                if not parsed:
                    return False, "fmt_err"

                host = str(parsed.get("server", "") or "").strip().lower()
                if host in cls.BLOCKED_HOSTS:
                    return False, "blocked_host"

                (
                    tcp_alive,
                    tcp_region,
                    tcp_latency,
                    tcp_speed,
                    _,
                    _,
                    tcp_err,
                    updated_link,
                ) = await VlessChecker.process_subscription(
                    link,
                    strict_speed=False,
                )

                tcp_standard_err = tcp_err and any(
                    f"Factor {i}" in str(tcp_err) for i in range(1, 7)
                )

                if not tcp_alive and not tcp_standard_err:
                    return False, "sys_err"

                if not tcp_alive:
                    return False, "dead"

                (
                    is_alive,
                    region,
                    latency,
                    speed_mbps,
                    ai_avail,
                    no_ads,
                    err,
                    strict_updated_link,
                ) = await VlessChecker.process_subscription(
                    updated_link,
                    strict_speed=True,
                )

                is_standard_err = err and any(
                    f"Factor {i}" in str(err) for i in range(1, 7)
                )

                final_region = tcp_region if tcp_region else "🌍 UNK"
                final_latency = int(tcp_latency) if isinstance(tcp_latency, int) else 9999
                final_speed = float(tcp_speed or 0.0)
                final_ai = False
                final_no_ads = False
                final_link = strict_updated_link if strict_updated_link else updated_link

                if is_alive:
                    speed = float(speed_mbps or 0.0)
                    if speed <= cls.MIN_ACCEPT_SPEED_MBPS:
                        return False, "dead"

                    strict_region = str(region or "").strip()
                    if strict_region and strict_region != "🌍 UNK":
                        final_region = strict_region
                    final_latency = int(latency or final_latency)
                    final_speed = speed
                    final_ai = bool(ai_avail)
                    final_no_ads = bool(no_ads)
                else:
                    if not is_standard_err:
                        return False, "sys_err"

                    err_text = str(err or "")
                    if "Factor 6" in err_text:
                        return False, "dead"

                if final_speed <= cls.MIN_ACCEPT_SPEED_MBPS:
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
                if not dec or "vless://" not in dec:
                    try:
                        dec = base64.urlsafe_b64decode(line).decode(
                            "utf-8", errors="ignore"
                        )
                    except:
                        pass

                if dec and "vless://" in dec:
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
                if not dec or "vless://" not in dec:
                    try:
                        dec = base64.urlsafe_b64decode(clean_text).decode(
                            "utf-8", errors="ignore"
                        )
                    except:
                        pass

                if dec:
                    decoded_parts.extend(re.findall(r'vless://[^\s\'"<>]+', dec))
            except Exception:
                pass

        return "\n".join(decoded_parts)

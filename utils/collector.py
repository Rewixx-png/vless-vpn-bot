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

logger = logging.getLogger("Collector")

DEFAULT_SOURCES = [
    "https://github.com/igareck/vpn-configs-for-russia/blob/main/Vless-Reality-White-Lists-Rus-Mobile-2.txt",
    "https://github.com/igareck/vpn-configs-for-russia/blob/main/Vless-Reality-White-Lists-Rus-Mobile.txt",
]


class SubscriptionCollector:
    MAX_LINKS_PER_BATCH = 40000
    _GITHUB_TREE_CACHE_TTL = 600
    _github_tree_cache = {}

    @classmethod
    async def run_collection(cls) -> dict:
        db_sources = await SourceRepo.get_enabled_urls()
        base_sources = list(dict.fromkeys(DEFAULT_SOURCES[:2] + db_sources))

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

        valid_results = [r for r in results if isinstance(r, str) and len(r) > 10]

        combined_text = "\n".join(valid_results)
        del valid_results

        decoded_content = cls._try_decode(combined_text)
        full_text = combined_text + "\n" + decoded_content
        del combined_text, decoded_content

        found_links = re.findall(r'vless://[^\s\'"<>]+', full_text)
        found_links = list(set(found_links))
        del full_text

        if not found_links:
            return {
                "processed": 0,
                "added": 0,
                "rejected": 0,
                "region_stats": {},
                "rejected_reasons": {},
                "sources_used": len(all_sources),
                "custom_sources_used": len(db_sources),
            }

        existing_keys = await SubRepo.get_all_keys_set()
        unique_links = []
        for l in found_links:
            l = l.strip()
            if l and l not in existing_keys:
                unique_links.append(l)

        del found_links, existing_keys

        if not unique_links:
            return {
                "processed": 0,
                "added": 0,
                "rejected": 0,
                "region_stats": {},
                "rejected_reasons": {},
                "sources_used": len(all_sources),
                "custom_sources_used": len(db_sources),
            }

        if len(unique_links) > cls.MAX_LINKS_PER_BATCH:
            unique_links = unique_links[: cls.MAX_LINKS_PER_BATCH]

        result = await cls._check_and_add_batch(unique_links)
        result["sources_used"] = len(all_sources)
        result["custom_sources_used"] = len(db_sources)
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
        rejected_reasons = {"dead": 0, "dup_or_bl": 0, "fmt_err": 0, "sys_err": 0}

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

                (
                    is_alive,
                    region,
                    latency,
                    speed_mbps,
                    ai_avail,
                    no_ads,
                    err,
                    updated_link,
                ) = await VlessChecker.process_subscription(link)

                is_standard_err = err and any(
                    f"Factor {i}" in str(err) for i in range(1, 7)
                )

                if not is_alive and not is_standard_err:
                    return False, "sys_err"

                if is_alive:
                    if not region:
                        region = "🌍 UNK"

                    added = await SubRepo.smart_add_subscription(
                        vless_key=updated_link,
                        region=region,
                        latency=latency,
                        speed_mbps=speed_mbps,
                        ai_available=ai_avail,
                        no_ads=no_ads,
                    )

                    if added:
                        return True, {"region": region}
                    else:
                        return False, "dup_or_bl"
                else:
                    return False, "dead"

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

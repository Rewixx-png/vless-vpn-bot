"""
Optimized subscription collector with priority queue and stream processing.
"""
import aiohttp
import asyncio
import base64
import re
import logging
from typing import List, Set, Tuple, Optional

from database.repo import SubRepo
from utils.checker import VlessChecker
from utils.batch_processor import SmartBatchProcessor

logger = logging.getLogger("Collector")

# Source URLs for proxy collection
SUBSCRIPTION_SOURCES = [
    "https://github.com/MhdiTaheri/V2rayCollector_Py/blob/main/sub/Mix/mix.txt",
    "https://github.com/T3stAcc/V2Ray/blob/main/All_Configs_Sub.txt",
    "https://github.com/V2RayRoot/V2RayConfig/blob/main/Config/vless.txt",
    "https://github.com/ALIILAPRO/v2rayNG-Config/blob/main/server.txt",
    "https://raw.githubusercontent.com/yitong2333/proxy-minging/refs/heads/main/v2ray.txt",
    "https://raw.githubusercontent.com/acymz/AutoVPN/refs/heads/main/data/V2.txt",
    "https://raw.githubusercontent.com/miladtahanian/V2RayCFGDumper/refs/heads/main/config.txt",
    "https://raw.githubusercontent.com/roosterkid/openproxylist/main/V2RAY_RAW.txt",
    "https://github.com/Epodonios/v2ray-configs/raw/main/Splitted-By-Protocol/trojan.txt",
    "https://raw.githubusercontent.com/YasserDivaR/pr0xy/refs/heads/main/ShadowSocks2021.txt",
    "https://raw.githubusercontent.com/mohamadfg-dev/telegram-v2ray-configs-collector/refs/heads/main/category/vless.txt",
    "https://raw.githubusercontent.com/mheidari98/.proxy/refs/heads/main/vless",
    "https://raw.githubusercontent.com/youfoundamin/V2rayCollector/main/mixed_iran.txt",
    "https://raw.githubusercontent.com/mheidari98/.proxy/refs/heads/main/all",
    "https://github.com/Kwinshadow/TelegramV2rayCollector/raw/refs/heads/main/sublinks/mix.txt",
    "https://github.com/LalatinaHub/Mineral/raw/refs/heads/master/result/nodes",
    "https://raw.githubusercontent.com/miladtahanian/multi-proxy-config-fetcher/refs/heads/main/configs/proxy_configs.txt",
    "https://raw.githubusercontent.com/Pawdroid/Free-servers/refs/heads/main/sub",
    "https://github.com/MhdiTaheri/V2rayCollector_Py/raw/refs/heads/main/sub/Mix/mix.txt",
    "https://github.com/Epodonios/v2ray-configs/raw/main/Splitted-By-Protocol/vmess.txt",
    "https://github.com/MhdiTaheri/V2rayCollector/raw/refs/heads/main/sub/mix",
    "https://raw.githubusercontent.com/mehran1404/Sub_Link/refs/heads/main/V2RAY-Sub.txt",
    "https://raw.githubusercontent.com/shabane/kamaji/master/hub/merged.txt",
    "https://raw.githubusercontent.com/wuqb2i4f/xray-config-toolkit/main/output/base64/mix-uri",
    "https://raw.githubusercontent.com/AzadNetCH/Clash/refs/heads/main/AzadNet.txt",
    "https://raw.githubusercontent.com/STR97/STRUGOV/refs/heads/main/STR.BYPASS",
    "https://raw.githubusercontent.com/V2RayRoot/V2RayConfig/refs/heads/main/Config/vless.txt",
    "https://raw.githubusercontent.com/lagzian/SS-Collector/main/mix_clash.yaml",
    "https://raw.githubusercontent.com/Argh94/V2RayAutoConfig/refs/heads/main/configs/Vless.txt",
    "https://raw.githubusercontent.com/Argh94/V2RayAutoConfig/refs/heads/main/configs/Hysteria2.txt",
    "https://raw.githubusercontent.com/mahdibland/V2RayAggregator/master/sub/sub_list.json",
    "https://raw.githubusercontent.com/NiREvil/vless/main/sub/SSTime",
    "https://raw.githubusercontent.com/ndsphonemy/proxy-sub/main/speed.txt",
    "https://raw.githubusercontent.com/Mahdi0024/ProxyCollector/master/sub/proxies.txt",
    "https://raw.githubusercontent.com/Mosifree/-FREE2CONFIG/refs/heads/main/Reality",
    "https://raw.githubusercontent.com/MrMohebi/xray-proxy-grabber-telegram/master/collected-proxies/row-url/all.txt"
]


class SubscriptionCollector:
    """Optimized subscription collector with streaming and prioritization"""
    
    MAX_LINKS_PER_BATCH = 50000  # No limit - process all
    MAX_WORKERS = 15  # Reduced for less CPU usage
    PRIORITY_REGIONS = {"🇩🇪 DE", "🇳🇱 NL", "🇫🇷 FR", "🇬🇧 GB", "🇺🇸 US", "🇸🇬 SG", "🇯🇵 JP"}
    
    @classmethod
    async def run_collection(cls) -> dict:
        """Run collection with optimized processing"""
        logger.warning(f"🔄 Starting collection from {len(SUBSCRIPTION_SOURCES)} sources")
        
        # Fetch all sources concurrently
        async with aiohttp.ClientSession() as session:
            tasks = [cls._fetch_url(session, url) for url in SUBSCRIPTION_SOURCES]
            results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Process results
        all_content = []
        for result in results:
            if isinstance(result, str) and result:
                all_content.append(result)
        
        # Extract and decode links
        combined_text = "\n".join(all_content)
        del all_content  # Free memory
        
        decoded_content = cls._try_decode(combined_text)
        full_text = combined_text + "\n" + decoded_content
        del combined_text, decoded_content
        
        # Extract VLESS links
        found_links = re.findall(r'(vless://[a-zA-Z0-9\-_.!~*\'()&=+$%@:/?#\[\]]+)', full_text)
        found_links = list(set(found_links))  # Remove duplicates
        del full_text
        
        # Filter out existing keys
        existing_keys = await SubRepo.get_all_keys_set()
        unique_links = [l.strip() for l in found_links if l.strip() not in existing_keys]
        del found_links
        
        if not unique_links:
            logger.warning("No new links to add")
            return {"processed": 0, "added": 0}
        
        # Limit batch size to manage memory
        if len(unique_links) > cls.MAX_LINKS_PER_BATCH:
            unique_links = unique_links[:cls.MAX_LINKS_PER_BATCH]
        
        logger.warning(f"Checking {len(unique_links)} new links...")
        # Process links with priority queue
        return await cls._process_links_priority(unique_links)
    
    @classmethod
    async def _process_links_priority(cls, links: List[str]) -> dict:
        """Process links with minimal logging"""
        log = logging.getLogger("Collector")
        added_count = 0
        checked_count = 0
        dead_count = 0
        rejected_count = 0
        error_count = 0
        region_stats = {}
        total_links = len(links)

        processor = SmartBatchProcessor(
            worker_count=30,
            progress_interval=5.0,
            rate_limit=50
        )

        logger.warning(f"🔄 Start check: {total_links} links")

        async def check_and_add(link: str) -> Optional[dict]:
            """Check link and add if valid"""
            nonlocal checked_count, added_count, dead_count, rejected_count, error_count

            try:
                is_alive, region, latency, ai_available, err = await VlessChecker.process_subscription(link)
                checked_count += 1

                if is_alive:
                    added = await SubRepo.smart_add_subscription(
                        vless_key=link,
                        region=region,
                        latency=latency,
                        ai_available=ai_available
                    )

                    if added:
                        added_count += 1
                        logger.info(f"✅ +1 {region} | {latency}ms | [{added_count}/{total_links}]")
                        if region not in region_stats:
                            region_stats[region] = {"added": 0, "rejected": 0}
                        region_stats[region]["added"] += 1
                        return {"status": "added", "region": region, "latency": latency}
                    else:
                        rejected_count += 1
                        logger.debug(f"⚠️ Rejected: {region} | [{checked_count}/{total_links}]")
                        return {"status": "rejected", "region": region}
                else:
                    dead_count += 1
                    logger.debug(f"❌ Dead: {err} | [{checked_count}/{total_links}]")
                    return {"status": "dead", "error": err}

            except Exception as e:
                error_count += 1
                return {"status": "error", "error": str(e)}

        # Progress callback
        def on_progress(completed: int, total: int, success: int, failed: int):
            log.warning(f"🔄 Progress: {completed}/{total} | Added: {added_count}, Dead: {dead_count}, Rejected: {rejected_count}, Errors: {error_count}")

        # Process in batches
        result = await processor.process(
            items=links,
            process_func=check_and_add,
            on_progress=on_progress
        )
        
        logger.warning(f"✅ Done: +{added_count} added, {dead_count} dead, {rejected_count} rejected, {error_count} errors ({result.duration:.1f}s)")
        
        return {
            "processed": checked_count,
            "added": added_count,
            "dead": dead_count,
            "rejected": rejected_count,
            "errors": error_count,
            "duration": result.duration,
            "region_stats": region_stats
        }
    
    @staticmethod
    async def _fetch_url(session: aiohttp.ClientSession, url: str) -> str:
        """Fetch URL with GitHub raw conversion"""
        try:
            # Convert GitHub blob URLs to raw
            if "github.com" in url and "/blob/" in url:
                url = url.replace("/blob/", "/raw/")
            
            timeout = aiohttp.ClientTimeout(total=15, connect=5)
            async with session.get(url, timeout=timeout) as resp:
                if resp.status == 200:
                    content = await resp.read()
                    # Limit size to prevent memory issues
                    if len(content) > 2 * 1024 * 1024:  # 2MB limit
                        content = content[:2 * 1024 * 1024]
                    return content.decode('utf-8', errors='ignore')
        except asyncio.TimeoutError:
            logger.warning(f"⏱️ Timeout: {url[:50]}...")
        except Exception as e:
            logger.debug(f"Failed to fetch {url[:50]}: {e}")
        
        return ""
    
    @staticmethod
    def _try_decode(text: str) -> str:
        """Try to decode base64 content"""
        if not text or "://" in text:
            return ""
        
        try:
            # Remove whitespace
            clean_text = re.sub(r'\s+', '', text)
            
            # Add padding if needed
            missing_padding = len(clean_text) % 4
            if missing_padding:
                clean_text += '=' * (4 - missing_padding)
            
            decoded = base64.b64decode(clean_text).decode('utf-8', errors='ignore')
            
            # Validate it looks like proxy configs
            if "://" in decoded:
                return decoded
        except Exception:
            pass
        
        return ""

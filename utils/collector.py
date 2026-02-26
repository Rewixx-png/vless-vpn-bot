import aiohttp
import asyncio
import base64
import re
import logging
from typing import List

try:
    from settings import COLLECTOR_SETTINGS
except ImportError:
    COLLECTOR_SETTINGS = {
        "max_links_per_batch": 40000,
        "initial_workers": 20,
        "min_workers": 8,
        "max_workers": 60,
        "target_cpu": 90.0,
    }

from database.repo import SubRepo, SourceRepo
from utils.checker import VlessChecker
from utils.batch_processor import CpuAdaptiveProcessor, SmartBatchProcessor

logger = logging.getLogger("Collector")

DEFAULT_SOURCES = [
    "https://raw.githubusercontent.com/igareck/vpn-configs-for-russia/main/Vless-Reality-White-Lists-Rus-Mobile-2.txt",
    "https://raw.githubusercontent.com/igareck/vpn-configs-for-russia/main/Vless-Reality-White-Lists-Rus-Mobile.txt",
    "https://raw.githubusercontent.com/AvenCores/goida-vpn-configs/main/githubmirror/1.txt",
    "https://raw.githubusercontent.com/AvenCores/goida-vpn-configs/main/githubmirror/2.txt",
    "https://raw.githubusercontent.com/AvenCores/goida-vpn-configs/main/githubmirror/3.txt",
    "https://raw.githubusercontent.com/AvenCores/goida-vpn-configs/main/githubmirror/4.txt",
    "https://raw.githubusercontent.com/AvenCores/goida-vpn-configs/main/githubmirror/5.txt",
    "https://raw.githubusercontent.com/AvenCores/goida-vpn-configs/main/githubmirror/6.txt",
    "https://raw.githubusercontent.com/AvenCores/goida-vpn-configs/main/githubmirror/7.txt",
    "https://raw.githubusercontent.com/AvenCores/goida-vpn-configs/main/githubmirror/8.txt",
    "https://raw.githubusercontent.com/AvenCores/goida-vpn-configs/main/githubmirror/9.txt",
    "https://raw.githubusercontent.com/AvenCores/goida-vpn-configs/main/githubmirror/10.txt",
    "https://raw.githubusercontent.com/AvenCores/goida-vpn-configs/main/githubmirror/11.txt",
    "https://raw.githubusercontent.com/AvenCores/goida-vpn-configs/main/githubmirror/12.txt",
    "https://raw.githubusercontent.com/AvenCores/goida-vpn-configs/main/githubmirror/13.txt",
    "https://raw.githubusercontent.com/AvenCores/goida-vpn-configs/main/githubmirror/14.txt",
    "https://raw.githubusercontent.com/AvenCores/goida-vpn-configs/main/githubmirror/15.txt",
    "https://raw.githubusercontent.com/AvenCores/goida-vpn-configs/main/githubmirror/16.txt",
    "https://raw.githubusercontent.com/AvenCores/goida-vpn-configs/main/githubmirror/17.txt",
    "https://raw.githubusercontent.com/AvenCores/goida-vpn-configs/main/githubmirror/18.txt",
    "https://raw.githubusercontent.com/AvenCores/goida-vpn-configs/main/githubmirror/19.txt",
    "https://raw.githubusercontent.com/AvenCores/goida-vpn-configs/main/githubmirror/20.txt",
    "https://raw.githubusercontent.com/AvenCores/goida-vpn-configs/main/githubmirror/21.txt",
    "https://raw.githubusercontent.com/AvenCores/goida-vpn-configs/main/githubmirror/22.txt",
    "https://raw.githubusercontent.com/AvenCores/goida-vpn-configs/main/githubmirror/23.txt",
    "https://raw.githubusercontent.com/AvenCores/goida-vpn-configs/main/githubmirror/24.txt",
    "https://raw.githubusercontent.com/AvenCores/goida-vpn-configs/main/githubmirror/25.txt",
    "https://raw.githubusercontent.com/AvenCores/goida-vpn-configs/main/githubmirror/26.txt",
]

class SubscriptionCollector:
    MAX_LINKS_PER_BATCH = 40000 
    
    @classmethod
    async def run_collection(cls) -> dict:
        db_sources = await SourceRepo.get_enabled_urls()
        all_sources = list(set(DEFAULT_SOURCES + db_sources))
        
        logger.warning(f"🚀 Starting SAFE collection from {len(all_sources)} sources...")
        
        async with aiohttp.ClientSession() as session:
            # Ограничиваем одновременные запросы к источникам
            tasks = []
            for url in all_sources:
                tasks.append(cls._fetch_url(session, url))
            
            # Скачиваем чанками по 9 для скорости
            results = []
            for i in range(0, len(tasks), 9):
                chunk = tasks[i:i+9]
                chunk_res = await asyncio.gather(*chunk, return_exceptions=True)
                results.extend(chunk_res)
        
        valid_results = [r for r in results if isinstance(r, str) and len(r) > 10]
        
        combined_text = "\n".join(valid_results)
        del valid_results
        
        decoded_content = cls._try_decode(combined_text)
        full_text = combined_text + "\n" + decoded_content
        del combined_text, decoded_content
        
        found_links = re.findall(r'vless://[a-zA-Z0-9\-@:?&=%#_.]+', full_text)
        found_links = list(set(found_links))
        del full_text
        
        if not found_links:
            logger.warning("💤 No links found in sources.")
            return {"processed": 0, "added": 0}

        existing_keys = await SubRepo.get_all_keys_set()
        unique_links = []
        for l in found_links:
            l = l.strip()
            if l and l not in existing_keys:
                unique_links.append(l)
        
        del found_links, existing_keys
        
        if not unique_links:
            logger.warning("💤 All found links are already in DB.")
            return {"processed": 0, "added": 0}
        
        if len(unique_links) > cls.MAX_LINKS_PER_BATCH:
            unique_links = unique_links[:cls.MAX_LINKS_PER_BATCH]
        
        logger.warning(f"⚡ Unique candidates: {len(unique_links)}. Starting Adaptive Check...")
        return await cls._check_and_add_batch(unique_links)
    
    @classmethod
    async def _check_and_add_batch(cls, links: List[str]) -> dict:
        added_count = 0
        failed_count = 0
        region_stats = {}
        
        # Используем SmartBatchProcessor для скорости
        processor = SmartBatchProcessor(worker_count=10)

        async def process_link(link: str):
            try:
                if "vless://" not in link or "@" not in link or ":" not in link:
                    return False, "fmt_err"

                is_alive, region, latency, speed_mbps, ai_avail, err = await VlessChecker.process_subscription(link)
                
                if not is_alive and err and "SYS_ERR" in str(err):
                    return False, "sys_err"
                
                if is_alive:
                    if not region: region = "🌍 UNK"
                    
                    added = await SubRepo.smart_add_subscription(
                        vless_key=link,
                        region=region,
                        latency=latency,
                        speed_mbps=speed_mbps,
                        ai_available=ai_avail
                    )
                    
                    if added:
                        return True, {"region": region}
                    else:
                        return False, "dup_or_bl"
                else:
                    return False, "dead"
                    
            except Exception as e:
                return False, str(e)

        async def on_progress(completed, total, success, failed, workers):
            if completed % 100 == 0:
                percent = int((completed / total) * 100) if total > 0 else 0
                logger.info(f"📊 Col: {percent}% ({completed}/{total}) | 🏗 Wrk: {workers} | ✅ +{success}")

        result = await processor.process(
            items=links,
            process_func=process_link,
            on_progress=on_progress
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
        
        logger.warning(f"✅ Collector Summary: +{added_count} Added | {failed_count} Discarded")
        
        return {
            "processed": len(links),
            "added": added_count,
            "rejected": failed_count,
            "region_stats": region_stats
        }
    
    @staticmethod
    async def _fetch_url(session: aiohttp.ClientSession, url: str) -> str:
        try:
            if "github.com" in url and "/blob/" in url:
                url = url.replace("/blob/", "/raw/")
            
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
            }
            
            timeout = aiohttp.ClientTimeout(total=20, connect=10)
            
            async with session.get(url, headers=headers, timeout=timeout) as resp:
                if resp.status == 200:
                    content = await resp.read()
                    if len(content) > 10 * 1024 * 1024:
                        content = content[:10 * 1024 * 1024]
                    return content.decode('utf-8', errors='ignore')
        except Exception:
            pass
        return ""
    
    @staticmethod
    def _try_decode(text: str) -> str:
        if not text: return ""
        decoded_parts = []
        
        lines = text.replace(',', '\n').splitlines()
        for line in lines:
            line = line.strip()
            if not line or "://" in line: continue
            try:
                pad = len(line) % 4
                if pad: line += '=' * (4 - pad)
                dec = base64.b64decode(line).decode('utf-8', errors='ignore')
                if "vless://" in dec:
                    decoded_parts.append(dec)
            except Exception:
                pass
        
        if not decoded_parts:
            try:
                clean_text = re.sub(r'\s+', '', text)
                pad = len(clean_text) % 4
                if pad: clean_text += '=' * (4 - pad)
                dec = base64.b64decode(clean_text).decode('utf-8', errors='ignore')
                decoded_parts.extend(re.findall(r'vless://[^\s]+', dec))
            except Exception:
                pass
            
        return "\n".join(decoded_parts)

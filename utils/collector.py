import aiohttp
import asyncio
import base64
import re
import time
from typing import List

from database.repo import SubRepo, SourceRepo
from utils.checker import VlessChecker
from utils.batch_processor import CpuAdaptiveProcessor

DEFAULT_SOURCES =[
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
        
        connector = aiohttp.TCPConnector(limit=15)
        
        async with aiohttp.ClientSession(connector=connector) as session:
            tasks =[cls._fetch_url(session, url) for url in all_sources]
            results = await asyncio.gather(*tasks, return_exceptions=True)
        
        valid_results =[r for r in results if isinstance(r, str) and len(r) > 10]
        
        combined_text = "\n".join(valid_results)
        del valid_results
        
        decoded_content = cls._try_decode(combined_text)
        full_text = combined_text + "\n" + decoded_content
        del combined_text, decoded_content
        
        found_links = re.findall(r'vless://[^\s\'"<>]+', full_text)
        found_links = list(set(found_links))
        del full_text
        
        if not found_links:
            return {"processed": 0, "added": 0, "rejected": 0, "region_stats": {}, "rejected_reasons": {}}

        existing_keys = await SubRepo.get_all_keys_set()
        unique_links =[]
        for l in found_links:
            l = l.strip()
            if l and l not in existing_keys:
                unique_links.append(l)
        
        del found_links, existing_keys
        
        if not unique_links:
            return {"processed": 0, "added": 0, "rejected": 0, "region_stats": {}, "rejected_reasons": {}}
        
        if len(unique_links) > cls.MAX_LINKS_PER_BATCH:
            unique_links = unique_links[:cls.MAX_LINKS_PER_BATCH]
        
        return await cls._check_and_add_batch(unique_links)
    
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
            target_ram=80.0
        )

        async def process_link(link: str):
            try:
                if "vless://" not in link or "@" not in link or ":" not in link:
                    return False, "fmt_err"

                is_alive, region, latency, speed_mbps, ai_avail, no_ads, err, updated_link = await VlessChecker.process_subscription(link)
                
                is_standard_err = err and any(f"Factor {i}" in str(err) for i in range(1, 7))
                
                if not is_alive and not is_standard_err:
                    return False, "sys_err"
                
                if is_alive:
                    if not region: region = "🌍 UNK"
                    
                    added = await SubRepo.smart_add_subscription(
                        vless_key=updated_link,
                        region=region,
                        latency=latency,
                        speed_mbps=speed_mbps,
                        ai_available=ai_avail,
                        no_ads=no_ads
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
            items=links,
            process_func=process_link,
            on_progress=None
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
            "rejected_reasons": rejected_reasons
        }
    
    @staticmethod
    async def _fetch_url(session: aiohttp.ClientSession, url: str) -> str:
        try:
            if "github.com" in url and "/blob/" in url:
                url = url.replace("/blob/", "/raw/")
            
            cache_buster = f"&t={int(time.time())}" if "?" in url else f"?t={int(time.time())}"
            fetch_url = url + cache_buster
            
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
            }
            
            timeout = aiohttp.ClientTimeout(total=20, connect=10)
            
            async with session.get(fetch_url, headers=headers, timeout=timeout) as resp:
                if resp.status == 200:
                    content = await resp.read()
                    if len(content) > 10 * 1024 * 1024:
                        content = content[:10 * 1024 * 1024]
                    return content.decode('utf-8', errors='ignore')
        except asyncio.CancelledError:
            raise
        except Exception:
            pass
        return ""
    
    @staticmethod
    def _try_decode(text: str) -> str:
        if not text: return ""
        decoded_parts =[]
        
        lines = text.replace(',', '\n').splitlines()
        for line in lines:
            line = line.strip()
            if not line or "://" in line: continue
            try:
                pad = len(line) % 4
                if pad: line += '=' * (4 - pad)
                
                dec = None
                try:
                    dec = base64.b64decode(line).decode('utf-8', errors='ignore')
                except:
                    pass
                if not dec or "vless://" not in dec:
                    try:
                        dec = base64.urlsafe_b64decode(line).decode('utf-8', errors='ignore')
                    except:
                        pass
                        
                if dec and "vless://" in dec:
                    decoded_parts.append(dec)
            except Exception:
                pass
        
        if not decoded_parts:
            try:
                clean_text = re.sub(r'\s+', '', text)
                pad = len(clean_text) % 4
                if pad: clean_text += '=' * (4 - pad)
                
                dec = None
                try:
                    dec = base64.b64decode(clean_text).decode('utf-8', errors='ignore')
                except:
                    pass
                if not dec or "vless://" not in dec:
                    try:
                        dec = base64.urlsafe_b64decode(clean_text).decode('utf-8', errors='ignore')
                    except:
                        pass
                        
                if dec:
                    decoded_parts.extend(re.findall(r'vless://[^\s\'"<>]+', dec))
            except Exception:
                pass
            
        return "\n".join(decoded_parts)

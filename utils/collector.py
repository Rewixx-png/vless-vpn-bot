import aiohttp
import asyncio
import base64
import re
import logging
from typing import List

from database.repo import SubRepo, SourceRepo
from utils.checker import VlessChecker
from utils.batch_processor import CpuAdaptiveProcessor

logger = logging.getLogger("Collector")

DEFAULT_SOURCES = [
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
    "https://raw.githubusercontent.com/heidari98/.proxy/refs/heads/main/vless",
    "https://raw.githubusercontent.com/youfoundamin/V2rayCollector/main/mixed_iran.txt",
    "https://raw.githubusercontent.com/heidari98/.proxy/refs/heads/main/all",
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
    MAX_LINKS_PER_BATCH = 150000 
    
    @classmethod
    async def run_collection(cls) -> dict:
        db_sources = await SourceRepo.get_enabled_urls()
        all_sources = list(set(DEFAULT_SOURCES + db_sources))
        
        logger.warning(f"🚀 Starting SMART AGGRESSIVE collection from {len(all_sources)} sources ({len(db_sources)} custom)...")
        
        async with aiohttp.ClientSession() as session:
            tasks = [cls._fetch_url(session, url) for url in all_sources]
            results = await asyncio.gather(*tasks, return_exceptions=True)
        
        all_content = [r for r in results if isinstance(r, str) and r]
        
        combined_text = "\n".join(all_content)
        del all_content
        
        decoded_content = cls._try_decode(combined_text)
        full_text = combined_text + "\n" + decoded_content
        del combined_text, decoded_content
        
        found_links = re.findall(r'vless://[^\s]+', full_text)
        found_links = list(set(found_links))
        del full_text
        
        existing_keys = await SubRepo.get_all_keys_set()
        unique_links = [l.strip() for l in found_links if l.strip() not in existing_keys]
        del found_links, existing_keys
        
        if not unique_links:
            logger.warning("💤 No new unique links found.")
            return {"processed": 0, "added": 0}
        
        if len(unique_links) > cls.MAX_LINKS_PER_BATCH:
            unique_links = unique_links[:cls.MAX_LINKS_PER_BATCH]
        
        logger.warning(f"⚡ Found {len(unique_links)} candidates. Starting Turbo Check...")
        return await cls._check_and_add_batch(unique_links)
    
    @classmethod
    async def _check_and_add_batch(cls, links: List[str]) -> dict:
        added_count = 0
        failed_count = 0
        region_stats = {}
        
        processor = CpuAdaptiveProcessor(
            initial_workers=15,
            min_workers=5,
            max_workers=40,
            target_cpu=80.0
        )

        async def process_link(link: str):
            try:
                if "vless://" not in link or "@" not in link or ":" not in link:
                    return False, "invalid_format"

                is_alive, region, latency, speed_mbps, ai_avail, err = await VlessChecker.process_subscription(link)
                
                if not is_alive and err and "SYS_ERR" in str(err):
                    return False, "sys_err"
                
                if is_alive:
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
                        return False, "duplicate_or_limit"
                else:
                    return False, "dead"
                    
            except Exception as e:
                return False, str(e)

        async def on_progress(completed, total, success, failed, workers):
            if completed % 200 == 0:
                percent = int((completed / total) * 100) if total > 0 else 0
                logger.info(f"📊 Progress: {percent}% ({completed}/{total}) | 🏗 Workers: {workers} | ✅ +{success}")

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
        
        logger.warning(f"✅ Collection Finished: +{added_count} Added | {failed_count} Discarded")
        
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
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            }
            
            timeout = aiohttp.ClientTimeout(total=15, connect=5)
            
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

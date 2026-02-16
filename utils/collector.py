"""
Subscription collector - no health check, just basic validation and add to DB.
"""
import aiohttp
import asyncio
import base64
import re
import logging
from typing import List, Set, Optional

from database.repo import SubRepo

logger = logging.getLogger("Collector")

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

REGION_KEYWORDS = {
    "DE": ["germany", "deutschland", "berlin", "frankfurt"],
    "NL": ["netherlands", "nederland", "amsterdam", "rotterdam"],
    "FR": ["france", "français", "paris", "marseille"],
    "GB": ["uk", "united kingdom", "britain", "london", "england"],
    "US": ["usa", "united states", "america", "new york", "los angeles", "chicago"],
    "SG": ["singapore"],
    "JP": ["japan", "tokyo", "osaka"],
    "CA": ["canada", "toronto", "montreal"],
    "AU": ["australia", "sydney", "melbourne"],
    "CH": ["switzerland", "zürich", "geneva"],
    "SE": ["sweden", "stockholm"],
    "NO": ["norway", "oslo"],
    "FI": ["finland", "helsinki"],
    "DK": ["denmark", "copenhagen"],
    "AT": ["austria", "wien", "vienna"],
    "BE": ["belgium", "brussels"],
    "IE": ["ireland", "dublin"],
    "IT": ["italy", "italia", "rome", "milano"],
    "ES": ["spain", "españa", "madrid", "barcelona"],
    "PT": ["portugal", "lisbon"],
    "PL": ["poland", "warsaw"],
    "CZ": ["czech", "praha", "prague"],
    "RU": ["russia", "россия", "москва", "saint petersburg"],
    "UA": ["ukraine", "україна", "kyiv"],
    "TR": ["turkey", "türkiye", "istanbul"],
    "IN": ["india", "mumbai", "delhi"],
    "HK": ["hong kong", "hk"],
    "KR": ["korea", "south korea", "seoul"],
    "TW": ["taiwan", "taipei"],
    "TH": ["thailand", "bangkok"],
    "VN": ["vietnam", "hanoi", "ho chi minh"],
    "ID": ["indonesia", "jakarta"],
    "MY": ["malaysia", "kuala lumpur"],
    "PH": ["philippines", "manila"],
    "BR": ["brazil", "brasil", "são paulo"],
    "AR": ["argentina", "buenos aires"],
    "MX": ["mexico", "méxico"],
    "ZA": ["south africa", "johannesburg"],
    "AE": ["uae", "dubai", "emirates"],
}


class SubscriptionCollector:
    MAX_LINKS_PER_BATCH = 50000
    MAX_WORKERS = 30
    
    @classmethod
    async def run_collection(cls) -> dict:
        logger.warning(f"🔄 Starting collection from {len(SUBSCRIPTION_SOURCES)} sources")
        
        async with aiohttp.ClientSession() as session:
            tasks = [cls._fetch_url(session, url) for url in SUBSCRIPTION_SOURCES]
            results = await asyncio.gather(*tasks, return_exceptions=True)
        
        all_content = [r for r in results if isinstance(r, str) and r]
        
        combined_text = "\n".join(all_content)
        del all_content
        
        decoded_content = cls._try_decode(combined_text)
        full_text = combined_text + "\n" + decoded_content
        del combined_text, decoded_content
        
        found_links = re.findall(r'(vless://[a-zA-Z0-9\-_.!~*\'()&=+$%@:/?#\[\]]+)', full_text)
        found_links = list(set(found_links))
        del full_text
        
        existing_keys = await SubRepo.get_all_keys_set()
        unique_links = [l.strip() for l in found_links if l.strip() not in existing_keys]
        del found_links, existing_keys
        
        if not unique_links:
            logger.warning("No new links to add")
            return {"processed": 0, "added": 0}
        
        if len(unique_links) > cls.MAX_LINKS_PER_BATCH:
            unique_links = unique_links[:cls.MAX_LINKS_PER_BATCH]
        
        logger.warning(f"Processing {len(unique_links)} new links...")
        return await cls._process_links_fast(unique_links)
    
    @classmethod
    async def _process_links_fast(cls, links: List[str]) -> dict:
        added_count = 0
        rejected_count = 0
        region_stats = {}
        total_links = len(links)
        
        semaphore = asyncio.Semaphore(cls.MAX_WORKERS)
        
        async def validate_and_add(link: str):
            nonlocal added_count, rejected_count
            
            async with semaphore:
                parsed = cls._parse_vless(link)
                if not parsed:
                    rejected_count += 1
                    return {"status": "rejected", "reason": "parse_error"}
                
                region = cls._detect_region(parsed)
                
                added = await SubRepo.smart_add_subscription(
                    vless_key=link,
                    region=region,
                    latency=0,
                    ai_available=False
                )
                
                if added:
                    added_count += 1
                    if region not in region_stats:
                        region_stats[region] = {"added": 0}
                    region_stats[region]["added"] += 1
                    return {"status": "added", "region": region}
                else:
                    rejected_count += 1
                    return {"status": "rejected", "reason": "duplicate"}
        
        tasks = [validate_and_add(link) for link in links]
        await asyncio.gather(*tasks, return_exceptions=True)
        
        logger.warning(f"✅ Done: +{added_count} added, {rejected_count} rejected")
        
        return {
            "processed": total_links,
            "added": added_count,
            "rejected": rejected_count,
            "region_stats": region_stats
        }
    
    @staticmethod
    def _parse_vless(link: str) -> dict | None:
        try:
            if not link.startswith("vless://"):
                return None
            
            rest = link[8:]
            
            if "#" in rest:
                rest = rest.split("#")[0]
            
            if "?" in rest:
                rest = rest.split("?")[0]
            
            rest = rest.rstrip("/")
            
            if "@" not in rest:
                return None
            
            userinfo, host_port = rest.split("@", 1)
            
            if ":" not in host_port:
                return None
            
            return {"link": link, "userinfo": userinfo, "host_port": host_port}
        except:
            return None
    
    @classmethod
    def _detect_region(cls, parsed: dict) -> str:
        link = parsed.get("link", "")
        link_lower = link.lower()
        
        for code, keywords in REGION_KEYWORDS.items():
            for kw in keywords:
                if kw in link_lower:
                    flag = "".join(chr(ord(c.upper()) + 127397) for c in code)
                    return f"{flag} {code}"
        
        return "🌍 UNK"
    
    @staticmethod
    async def _fetch_url(session: aiohttp.ClientSession, url: str) -> str:
        try:
            if "github.com" in url and "/blob/" in url:
                url = url.replace("/blob/", "/raw/")
            
            timeout = aiohttp.ClientTimeout(total=15, connect=5)
            async with session.get(url, timeout=timeout) as resp:
                if resp.status == 200:
                    content = await resp.read()
                    if len(content) > 2 * 1024 * 1024:
                        content = content[:2 * 1024 * 1024]
                    return content.decode('utf-8', errors='ignore')
        except:
            pass
        return ""
    
    @staticmethod
    def _try_decode(text: str) -> str:
        if not text or "://" in text:
            return ""
        
        try:
            clean_text = re.sub(r'\s+', '', text)
            
            missing_padding = len(clean_text) % 4
            if missing_padding:
                clean_text += '=' * (4 - missing_padding)
            
            decoded = base64.b64decode(clean_text).decode('utf-8', errors='ignore')
            
            if "://" in decoded:
                return decoded
        except:
            pass
        
        return ""

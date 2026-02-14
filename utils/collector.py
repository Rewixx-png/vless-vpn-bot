import aiohttp
import asyncio
import base64
import re
import logging
import gc 
from database.repo import SubRepo
from utils.checker import VlessChecker

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
    @staticmethod
    async def run_collection():
        try:
            async with aiohttp.ClientSession() as session:
                tasks = [SubscriptionCollector._fetch_url(session, url) for url in SUBSCRIPTION_SOURCES]
                results = await asyncio.gather(*tasks, return_exceptions=True)
                results = [r for r in results if isinstance(r, str) and r]
        except asyncio.CancelledError:
            return

        all_content = "\n".join(results)
        del results
        gc.collect()

        decoded_content = SubscriptionCollector._try_decode(all_content)
        full_text = all_content + "\n" + decoded_content
        
        del all_content
        del decoded_content
        gc.collect()

        found_links = re.findall(r'(vless://[a-zA-Z0-9\-_.!~*\'()&=+$%@:/?#\[\]]+)', full_text)
        found_links = list(set(found_links))
        
        del full_text
        gc.collect()
        
        existing_keys = await SubRepo.get_all_keys_set()
        unique_links = [l.strip() for l in found_links if l.strip() not in existing_keys]
        
        if not unique_links:
            return
            
        if len(unique_links) > 3500:
            unique_links = unique_links[:3500]

        queue = asyncio.Queue()
        for link in unique_links:
            queue.put_nowait(link)

        valid_count = [0]
        
        WORKERS_COUNT = 100
        workers = []

        async def worker():
            while True:
                try:
                    link = await queue.get()
                except asyncio.CancelledError:
                    return

                try:
                    is_alive, region, latency, ai_available, err = await VlessChecker.process_subscription(link)
                    
                    if is_alive:
                        added = await SubRepo.smart_add_subscription(
                            vless_key=link, 
                            region=region, 
                            latency=latency, 
                            ai_available=ai_available
                        )
                        if added:
                            valid_count[0] += 1
                except asyncio.CancelledError:
                    queue.task_done()
                    return
                except Exception:
                    pass
                finally:
                    queue.task_done()
                    gc.collect()

        for _ in range(WORKERS_COUNT):
            workers.append(asyncio.create_task(worker()))

        try:
            await queue.join()
        except asyncio.CancelledError:
            pass
        finally:
            for w in workers:
                w.cancel()
            
            await asyncio.gather(*workers, return_exceptions=True)

    @staticmethod
    async def _fetch_url(session, url):
        try:
            if "github.com" in url and "/blob/" in url:
                url = url.replace("/blob/", "/raw/")
            async with session.get(url, timeout=10) as resp:
                if resp.status == 200:
                    content = await resp.read()
                    if len(content) > 1024 * 1024: 
                        content = content[:1024 * 1024]
                    return content.decode('utf-8', errors='ignore')
        except Exception:
            pass
        return ""

    @staticmethod
    def _try_decode(text):
        try:
            clean_text = re.sub(r'\s+', '', text)
            missing_padding = len(clean_text) % 4
            if missing_padding: clean_text += '=' * (4 - missing_padding)
            decoded = base64.b64decode(clean_text).decode('utf-8', errors='ignore')
            return decoded
        except Exception: return ""
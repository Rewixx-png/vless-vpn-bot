import aiohttp
import asyncio
import base64
import re
import logging
from database.repo import SubRepo
from utils.vless_checker import VlessChecker

logger = logging.getLogger("Collector")

SUBSCRIPTION_SOURCES = [
    "https://github.com/ebrasha/free-v2ray-public-list/blob/main/vless_configs.txt",
    "https://github.com/iboxz/free-v2ray-collector/blob/main/main/vless.txt",
    "https://github.com/F0rc3Run/F0rc3Run/blob/main/splitted-by-protocol/vless.txt",
    "https://github.com/sevcator/5ubscrpt10n/blob/main/protocols/vl.txt",
    "https://github.com/ALIILAPRO/v2rayNG-Config/blob/main/server.txt",
    "https://github.com/igareck/vpn-configs-for-russia/blob/main/WHITE-SNI-RU-all.txt",
    "https://github.com/sakha1370/OpenRay/raw/refs/heads/main/output/all_valid_proxies.txt",
    "https://raw.githubusercontent.com/sevcator/5ubscrpt10n/main/protocols/vl.txt",
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
    "https://raw.githubusercontent.com/MrMohebi/xray-proxy-grabber-telegram/master/collected-proxies/row-url/all.txt",
    "https://raw.githubusercontent.com/igareck/vpn-configs-for-russia/refs/heads/main/Vless-Reality-White-Lists-Rus-Mobile.txt",
    "https://raw.githubusercontent.com/igareck/vpn-configs-for-russia/refs/heads/main/Vless-Reality-White-Lists-Rus-Cable.txt",
    "https://raw.githubusercontent.com/V2RAYCONFIGSPOOL/V2RAY_SUB/refs/heads/main/v2ray_configs_no1.txt",
    "https://raw.githubusercontent.com/V2RAYCONFIGSPOOL/V2RAY_SUB/refs/heads/main/v2ray_configs_no2.txt",
    "https://raw.githubusercontent.com/V2RAYCONFIGSPOOL/V2RAY_SUB/refs/heads/main/v2ray_configs_no3.txt",
    "https://raw.githubusercontent.com/V2RAYCONFIGSPOOL/V2RAY_SUB/refs/heads/main/v2ray_configs_no4.txt",
    "https://raw.githubusercontent.com/V2RAYCONFIGSPOOL/V2RAY_SUB/refs/heads/main/v2ray_configs_no5.txt",
    "https://raw.githubusercontent.com/V2RAYCONFIGSPOOL/V2RAY_SUB/refs/heads/main/v2ray_configs_no6.txt",
    "https://raw.githubusercontent.com/V2RAYCONFIGSPOOL/V2RAY_SUB/refs/heads/main/v2ray_configs_no7.txt",
    "https://raw.githubusercontent.com/V2RAYCONFIGSPOOL/V2RAY_SUB/refs/heads/main/v2ray_configs_no8.txt",
    "https://raw.githubusercontent.com/V2RAYCONFIGSPOOL/V2RAY_SUB/refs/heads/main/v2ray_configs_no9.txt",
    "https://raw.githubusercontent.com/V2RAYCONFIGSPOOL/V2RAY_SUB/refs/heads/main/v2ray_configs_no10.txt",
    "https://raw.githubusercontent.com/V2RAYCONFIGSPOOL/V2RAY_SUB/refs/heads/main/v2ray_configs_no11.txt",
    "https://raw.githubusercontent.com/V2RAYCONFIGSPOOL/V2RAY_SUB/refs/heads/main/v2ray_configs_no12.txt",
    "https://raw.githubusercontent.com/V2RAYCONFIGSPOOL/V2RAY_SUB/refs/heads/main/v2ray_configs_no13.txt",
    "https://raw.githubusercontent.com/V2RAYCONFIGSPOOL/V2RAY_SUB/refs/heads/main/v2ray_configs_no14.txt",
    "https://raw.githubusercontent.com/V2RAYCONFIGSPOOL/V2RAY_SUB/refs/heads/main/v2ray_configs_no15.txt",
    "https://raw.githubusercontent.com/V2RAYCONFIGSPOOL/V2RAY_SUB/refs/heads/main/v2ray_configs_no16.txt",
    "https://raw.githubusercontent.com/V2RAYCONFIGSPOOL/V2RAY_SUB/refs/heads/main/v2ray_configs_no17.txt",
    "https://raw.githubusercontent.com/V2RAYCONFIGSPOOL/V2RAY_SUB/refs/heads/main/v2ray_configs_no18.txt",
    "https://raw.githubusercontent.com/V2RAYCONFIGSPOOL/V2RAY_SUB/refs/heads/main/v2ray_configs_no19.txt",
    "https://raw.githubusercontent.com/V2RAYCONFIGSPOOL/V2RAY_SUB/refs/heads/main/v2ray_configs_no20.txt"
]

class SubscriptionCollector:
    @staticmethod
    async def run_collection():
        logger.info("🚀 Starting VLESS collector...")
        
        try:
            async with aiohttp.ClientSession() as session:
                tasks = [SubscriptionCollector._fetch_url(session, url) for url in SUBSCRIPTION_SOURCES]
                results = await asyncio.gather(*tasks, return_exceptions=True)
                results = [r for r in results if isinstance(r, str) and r]
        except asyncio.CancelledError:
            logger.info("🛑 Collection cancelled during fetch.")
            return

        all_content = "\n".join(results)
        decoded_content = SubscriptionCollector._try_decode(all_content)
        full_text = all_content + "\n" + decoded_content

        found_links = re.findall(r'(vless://[a-zA-Z0-9\-_.!~*\'()&=+$%@:/?#\[\]]+)', full_text)
        found_links = list(set(found_links))
        
        logger.info(f"🔎 Found {len(found_links)} potential VLESS links. Validating...")

        existing_keys = await SubRepo.get_all_keys_set()
        unique_links = [l.strip() for l in found_links if l.strip() not in existing_keys]
        
        if not unique_links:
            logger.info("😴 No new unique links found.")
            return

        logger.info(f"🧬 Checking {len(unique_links)} new unique links via Xray...")

        queue = asyncio.Queue()
        for link in unique_links:
            queue.put_nowait(link)

        valid_count = [0]
        WORKERS_COUNT = 50 
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
                        try:
                            await SubRepo.add_subscription(
                                vless_key=link, 
                                region=region, 
                                latency=latency,
                                ai_available=ai_available
                            )
                            valid_count[0] += 1
                        except Exception:
                            pass
                except asyncio.CancelledError:
                    queue.task_done()
                    return
                except Exception:
                    pass
                finally:
                    queue.task_done()

        for _ in range(WORKERS_COUNT):
            workers.append(asyncio.create_task(worker()))

        try:
            await queue.join()
        except asyncio.CancelledError:
            logger.info("🛑 Collector waiting interrupted!")
        finally:
            for w in workers:
                w.cancel()
            
            await asyncio.gather(*workers, return_exceptions=True)
            
            logger.info(f"✅ Collector stopped. Added {valid_count[0]} VALID new keys.")

    @staticmethod
    async def _fetch_url(session, url):
        try:
            if "github.com" in url and "/blob/" in url:
                url = url.replace("/blob/", "/raw/")
            async with session.get(url, timeout=10) as resp:
                if resp.status == 200:
                    return await resp.text(encoding='utf-8', errors='ignore')
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
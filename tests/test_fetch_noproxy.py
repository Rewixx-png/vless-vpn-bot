import asyncio
from utils.collector import SubscriptionCollector
from config import config

async def main():
    config.CHECKER_USE_RU_PROXY_CHAIN = False
    
    # Temporarily set to a small source for speed
    from utils.collector import FIXED_SOURCE_URLS
    FIXED_SOURCE_URLS.clear()
    FIXED_SOURCE_URLS.append("https://raw.githubusercontent.com/igareck/vpn-configs-for-russia/main/Vless-Reality-White-Lists-Rus-Mobile-2.txt")
    
    res = await SubscriptionCollector.run_collection()
    print("Result without proxy:", res)

asyncio.run(main())

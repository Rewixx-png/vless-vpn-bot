import asyncio
import time
import aiohttp
from utils.collector import SubscriptionCollector
from utils.checker import VlessChecker

async def main():
    sources = ["https://raw.githubusercontent.com/igareck/vpn-configs-for-russia/main/Vless-Reality-White-Lists-Rus-Mobile-2.txt"]
    links = []
    
    print("Fetching links...")
    connector = aiohttp.TCPConnector(limit=10)
    async with aiohttp.ClientSession(connector=connector) as session:
        tasks = [SubscriptionCollector._fetch_url(session, url) for url in sources]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for res in results:
            if isinstance(res, str):
                decoded = SubscriptionCollector._try_decode(res)
                import re
                extracted = re.findall(r'vless://[^\s\'"<>]+', res + "\n" + decoded)
                links.extend(extracted)
        
    print(f"Got {len(links)} links. Testing first 5...")
    
    for i, link in enumerate(links[:5]):
        print(f"Testing link {i+1}...")
        start = time.time()
        res = await VlessChecker.process_subscription(link, strict_speed=False)
        end = time.time()
        print(f"Time: {end - start:.2f}s")
        print(f"Result: {res}")

if __name__ == "__main__":
    asyncio.run(main())

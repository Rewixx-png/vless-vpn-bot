import asyncio
from utils.checker import VlessChecker
from utils.collector import SubscriptionCollector
import aiohttp

async def main():
    print("Fetching first source...")
    connector = aiohttp.TCPConnector(limit=10)
    async with aiohttp.ClientSession(connector=connector) as session:
        text = await SubscriptionCollector._fetch_url(session, "https://raw.githubusercontent.com/kort0881/vpn-checker-backend/main/checked/RU_Best/ru_white_part1.txt")
        decoded = SubscriptionCollector._try_decode(text)
        import re
        links = re.findall(r'vless://[^\s\'"<>]+', text + "\n" + decoded)
        links = list(set(links))[:5]
        
    print(f"Found {len(links)} links, testing...")
    
    for link in links:
        is_alive, region, latency, speed_mbps, ai_avail, no_ads, err, updated_link = await VlessChecker.process_subscription(link, strict_speed=False)
        print(f"Link: {link[:50]}... -> is_alive: {is_alive}, err: {err}")

if __name__ == "__main__":
    asyncio.run(main())
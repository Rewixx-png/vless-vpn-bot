import asyncio
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
        links = list(set(links))[:20]
        
    print(f"Found {len(links)} links, testing...")
    
    result = await SubscriptionCollector._check_and_add_batch(links)
    print("Result:", result)

if __name__ == "__main__":
    asyncio.run(main())

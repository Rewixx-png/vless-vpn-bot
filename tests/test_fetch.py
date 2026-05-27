import asyncio
from utils.checker import VlessChecker
import urllib.request
import re
import time

async def main():
    print("Fetching links...")
    req = urllib.request.Request("https://raw.githubusercontent.com/yebekhe/TelegramV2rayCollector/main/sub/normal/vless")
    with urllib.request.urlopen(req) as response:
        content = response.read().decode('utf-8')
    
    links = [line.strip() for line in content.split('\n') if line.strip().startswith('vless://')]
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

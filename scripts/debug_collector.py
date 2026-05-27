import asyncio
from utils.collector import SubscriptionCollector
from config import config

async def main():
    # Only test with 1 source to speed it up
    from utils.collector import FIXED_SOURCE_URLS
    original_urls = FIXED_SOURCE_URLS.copy()
    FIXED_SOURCE_URLS.clear()
    FIXED_SOURCE_URLS.append(original_urls[0])
    
    res = await SubscriptionCollector.run_collection()
    print("Result:", res)

asyncio.run(main())

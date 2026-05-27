import asyncio
from utils.collector import SubscriptionCollector
from config import config

async def main():
    # Only test with 1 source to speed it up
    from utils.collector import FIXED_SOURCE_URLS
    original_urls = FIXED_SOURCE_URLS.copy()
    FIXED_SOURCE_URLS.clear()
    FIXED_SOURCE_URLS.append(original_urls[1])
    
    SubscriptionCollector.MAX_LINKS_PER_BATCH = 50 # Only test 50 links
    res = await SubscriptionCollector.run_collection()
    print("REASONS:", res.get("rejected_reasons"))

asyncio.run(main())

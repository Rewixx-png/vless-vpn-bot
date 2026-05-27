import asyncio
from database.core import async_session_factory
from database.models import Subscription
from sqlalchemy import select

async def main():
    async with async_session_factory() as s:
        res = await s.execute(select(Subscription.is_active, Subscription.death_count))
        rows = res.all()
        print(f"Total: {len(rows)}, Active: {sum(1 for r in rows if r[0])}")

if __name__ == "__main__":
    asyncio.run(main())

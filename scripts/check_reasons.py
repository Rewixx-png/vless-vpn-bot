import asyncio
import json
from database.core import engine
from sqlalchemy import text

async def main():
    async with engine.begin() as conn:
        res = await conn.execute(text("SELECT value FROM system_config WHERE key = 'collector_last_run'"))
        row = res.fetchone()
        if row:
            print("Stats:", row[0])
            
        res = await conn.execute(text("SELECT value FROM system_config WHERE key = 'topic_not_configs'"))
        row = res.fetchone()
        if row:
            print("topic_not_configs thread:", row[0])

asyncio.run(main())

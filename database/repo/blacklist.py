from sqlalchemy import select, insert, delete
from sqlalchemy.dialects.postgresql import insert as pg_insert
from database.core import async_session_factory
from database.models import BlacklistedItem

class BlacklistRepo:
    @staticmethod
    async def add_to_blacklist(vless_key: str, reason: str = "Unknown Region"):
        async with async_session_factory() as session:
            stmt = pg_insert(BlacklistedItem).values(
                vless_key=vless_key, 
                reason=reason
            ).on_conflict_do_nothing(index_elements=['vless_key'])
            
            await session.execute(stmt)
            await session.commit()

    @staticmethod
    async def is_blacklisted(vless_key: str) -> bool:
        async with async_session_factory() as session:
            result = await session.scalar(
                select(BlacklistedItem.id).where(BlacklistedItem.vless_key == vless_key)
            )
            return result is not None

    @staticmethod
    async def get_count() -> int:
        async with async_session_factory() as session:
            from sqlalchemy import func
            return await session.scalar(select(func.count(BlacklistedItem.id))) or 0
    
    @staticmethod
    async def clear_blacklist():
        async with async_session_factory() as session:
            await session.execute(delete(BlacklistedItem))
            await session.commit()
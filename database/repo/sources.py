from sqlalchemy import select, delete, update
from database.core import async_session_factory
from database.models import SubscriptionSource

class SourceRepo:
    @staticmethod
    async def add_source(url: str, title: str = None, enabled: bool = True) -> bool:
        async with async_session_factory() as session:
            existing = await session.execute(select(SubscriptionSource).where(SubscriptionSource.url == url))
            if existing.scalars().first():
                return False
            
            source = SubscriptionSource(url=url, title=title, is_enabled=enabled)
            session.add(source)
            await session.commit()
            return True

    @staticmethod
    async def get_all_sources() -> list[SubscriptionSource]:
        async with async_session_factory() as session:
            result = await session.execute(select(SubscriptionSource))
            return result.scalars().all()

    @staticmethod
    async def get_enabled_urls() -> list[str]:
        async with async_session_factory() as session:
            result = await session.execute(
                select(SubscriptionSource.url).where(SubscriptionSource.is_enabled == True)
            )
            return result.scalars().all()

    @staticmethod
    async def delete_source(source_id: int):
        async with async_session_factory() as session:
            await session.execute(delete(SubscriptionSource).where(SubscriptionSource.id == source_id))
            await session.commit()

    @staticmethod
    async def toggle_source(source_id: int, enabled: bool = None):
        async with async_session_factory() as session:
            source = await session.get(SubscriptionSource, source_id)
            if source:
                if enabled is not None:
                    source.is_enabled = enabled
                else:
                    source.is_enabled = not source.is_enabled
                await session.commit()
                return source.is_enabled
        return False
from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from database.core import async_session_factory
from database.models import SystemConfig

class SystemRepo:
    @staticmethod
    async def get_config(key: str) -> str | None:
        async with async_session_factory() as session:
            result = await session.get(SystemConfig, key)
            return result.value if result else None

    @staticmethod
    async def set_config(key: str, value: str):
        async with async_session_factory() as session:
            stmt = insert(SystemConfig).values(key=key, value=value)
            stmt = stmt.on_conflict_do_update(
                index_elements=['key'],
                set_=dict(value=value)
            )
            await session.execute(stmt)
            await session.commit()
    
    @staticmethod
    async def delete_config(key: str):
        async with async_session_factory() as session:
            config_item = await session.get(SystemConfig, key)
            if config_item:
                await session.delete(config_item)
                await session.commit()
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
            config_item = await session.get(SystemConfig, key)
            if config_item:
                config_item.value = value
            else:
                session.add(SystemConfig(key=key, value=value))
            await session.commit()

    @staticmethod
    async def delete_config(key: str):
        async with async_session_factory() as session:
            config_item = await session.get(SystemConfig, key)
            if config_item:
                await session.delete(config_item)
                await session.commit()

from sqlalchemy import select, update
from database.core import async_session_factory
from database.models import User

class UserRepo:
    @staticmethod
    async def add_user(user_id: int, username: str):
        async with async_session_factory() as session:
            user = await session.get(User, user_id)
            if not user:
                user = User(id=user_id, username=username)
                session.add(user)
                await session.commit()

    @staticmethod
    async def get_all_users():
        async with async_session_factory() as session:
            result = await session.execute(select(User.id))
            return result.scalars().all()

    @staticmethod
    async def get_user(user_id: int) -> User | None:
        async with async_session_factory() as session:
            return await session.get(User, user_id)

    @staticmethod
    async def get_user_filter(user_id: int) -> list[str] | None:
        async with async_session_factory() as session:
            user = await session.get(User, user_id)
            if user and user.country_filter:
                return user.country_filter.split(",")
            return None

    @staticmethod
    async def update_user_filter(user_id: int, countries: list[str] | None):
        filter_str = ",".join(countries) if countries else None
        async with async_session_factory() as session:
            stmt = update(User).where(User.id == user_id).values(country_filter=filter_str)
            await session.execute(stmt)
            await session.commit()

    @staticmethod
    async def get_user_tags(user_id: int) -> list[str]:
        async with async_session_factory() as session:
            user = await session.get(User, user_id)
            if user and user.tags_filter:
                return user.tags_filter.split(",")
            return []

    @staticmethod
    async def update_user_tags(user_id: int, tags: list[str] | None):
        tags_str = ",".join(tags) if tags else None
        async with async_session_factory() as session:
            stmt = update(User).where(User.id == user_id).values(tags_filter=tags_str)
            await session.execute(stmt)
            await session.commit()

    @staticmethod
    async def update_subscription_limit(user_id: int, limit: int):
        async with async_session_factory() as session:
            stmt = update(User).where(User.id == user_id).values(subscription_limit=limit)
            await session.execute(stmt)
            await session.commit()
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
        """Получить объект пользователя целиком"""
        async with async_session_factory() as session:
            return await session.get(User, user_id)

    @staticmethod
    async def get_user_filter(user_id: int) -> list[str] | None:
        """Возвращает список стран или None (если выбраны все)"""
        async with async_session_factory() as session:
            user = await session.get(User, user_id)
            if user and user.country_filter:
                return user.country_filter.split(",")
            return None

    @staticmethod
    async def update_user_filter(user_id: int, countries: list[str] | None):
        """Обновляет фильтр стран. Если countries пустой или None - сброс на 'Все'"""
        filter_str = ",".join(countries) if countries else None
        async with async_session_factory() as session:
            stmt = update(User).where(User.id == user_id).values(country_filter=filter_str)
            await session.execute(stmt)
            await session.commit()

    @staticmethod
    async def update_subscription_limit(user_id: int, limit: int):
        """Обновляет лимит количества ключей (0 = безлимит)"""
        async with async_session_factory() as session:
            stmt = update(User).where(User.id == user_id).values(subscription_limit=limit)
            await session.execute(stmt)
            await session.commit()
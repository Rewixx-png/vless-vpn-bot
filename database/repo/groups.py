from sqlalchemy import select, delete, update
from database.core import async_session_factory
from database.models import UserGroup

class GroupRepo:
    @staticmethod
    async def create_group(user_id: int, name: str, countries: list[str] | None):
        filter_str = ",".join(countries) if countries else None
        async with async_session_factory() as session:
            existing = await session.execute(
                select(UserGroup).where(UserGroup.user_id == user_id, UserGroup.name == name)
            )
            if existing.scalars().first():
                return False

            group = UserGroup(user_id=user_id, name=name, country_filter=filter_str)
            session.add(group)
            await session.commit()
            return group

    @staticmethod
    async def get_user_groups(user_id: int):
        async with async_session_factory() as session:
            result = await session.execute(
                select(UserGroup).where(UserGroup.user_id == user_id).order_by(UserGroup.name)
            )
            return result.scalars().all()

    @staticmethod
    async def get_group_by_name(user_id: int, name: str):
        async with async_session_factory() as session:
            result = await session.execute(
                select(UserGroup).where(UserGroup.user_id == user_id, UserGroup.name == name)
            )
            return result.scalars().first()

    @staticmethod
    async def delete_group(group_id: int):
        async with async_session_factory() as session:
            await session.execute(delete(UserGroup).where(UserGroup.id == group_id))
            await session.commit()

    @staticmethod
    async def update_group_countries(group_id: int, countries: list[str] | None):
        filter_str = ",".join(countries) if countries else None
        async with async_session_factory() as session:
            stmt = update(UserGroup).where(UserGroup.id == group_id).values(country_filter=filter_str)
            await session.execute(stmt)
            await session.commit()

    @staticmethod
    async def update_group_tags(group_id: int, tags: list[str] | None):
        tags_str = ",".join(tags) if tags else None
        async with async_session_factory() as session:
            stmt = update(UserGroup).where(UserGroup.id == group_id).values(tags_filter=tags_str)
            await session.execute(stmt)
            await session.commit()

    @staticmethod
    async def get_all_groups():
        async with async_session_factory() as session:
            result = await session.execute(select(UserGroup).order_by(UserGroup.user_id))
            return result.scalars().all()

    @staticmethod
    async def get_users_with_group_region(region: str) -> list[int]:
        async with async_session_factory() as session:
            # Ищем группы, у которых в фильтре есть этот регион
            stmt = select(UserGroup.user_id).where(UserGroup.country_filter.like(f"%{region}%"))
            result = await session.execute(stmt)
            # Возвращаем список уникальных user_id
            return list(set(result.scalars().all()))
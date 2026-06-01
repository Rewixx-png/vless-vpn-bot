import logging
from sqlalchemy import select, update, func, delete
from sqlalchemy.dialects.postgresql import insert
from database.core import async_session_factory
from database.models import User, UserGroup

logger = logging.getLogger(__name__)

class UserRepo:
    @staticmethod
    async def add_user(user_id: int, username: str):
        try:
            async with async_session_factory() as session:
                stmt = (
                    insert(User)
                    .values(id=user_id, username=username)
                    .on_conflict_do_nothing(index_elements=[User.id])
                )
                await session.execute(stmt)
                await session.commit()
        except Exception as e:
            logger.error(f"add_user error: {e}")

    @staticmethod
    async def get_all_users():
        try:
            async with async_session_factory() as session:
                result = await session.execute(select(User).order_by(User.id.desc()))
                return result.scalars().all()
        except Exception as e:
            logger.error(f"get_all_users error: {e}")
            return []

    @staticmethod
    async def get_users_paginated(limit: int, offset: int) -> list[User]:
        try:
            async with async_session_factory() as session:
                result = await session.execute(
                    select(User).order_by(User.id).limit(limit).offset(offset)
                )
                return result.scalars().all()
        except Exception as e:
            logger.error(f"get_users_paginated error: {e}")
            return []
            
    @staticmethod
    async def get_users_count() -> int:
        try:
            async with async_session_factory() as session:
                count = await session.scalar(select(func.count(User.id)))
                return count or 0
        except Exception as e:
            logger.error(f"get_users_count error: {e}")
            return 0

    @staticmethod
    async def get_user(user_id: int) -> User | None:
        try:
            async with async_session_factory() as session:
                return await session.get(User, user_id)
        except Exception as e:
            logger.error(f"get_user error: {e}")
            return None

    @staticmethod
    async def get_user_filter(user_id: int) -> list[str] | None:
        try:
            async with async_session_factory() as session:
                user = await session.get(User, user_id)
                if user and user.country_filter:
                    return user.country_filter.split(",")
                return None
        except Exception as e:
            logger.error(f"get_user_filter error: {e}")
            return None

    @staticmethod
    async def update_user_filter(user_id: int, countries: list[str] | None):
        try:
            filter_str = ",".join(countries) if countries else None
            async with async_session_factory() as session:
                stmt = update(User).where(User.id == user_id).values(country_filter=filter_str)
                await session.execute(stmt)
                await session.commit()
        except Exception as e:
            logger.error(f"update_user_filter error: {e}")

    @staticmethod
    async def get_user_tags(user_id: int) -> list[str]:
        try:
            async with async_session_factory() as session:
                user = await session.get(User, user_id)
                if user and user.tags_filter:
                    return user.tags_filter.split(",")
                return []
        except Exception as e:
            logger.error(f"get_user_tags error: {e}")
            return []

    @staticmethod
    async def update_user_tags(user_id: int, tags: list[str] | None):
        try:
            tags_str = ",".join(tags) if tags else None
            async with async_session_factory() as session:
                stmt = update(User).where(User.id == user_id).values(tags_filter=tags_str)
                await session.execute(stmt)
                await session.commit()
        except Exception as e:
            logger.error(f"update_user_tags error: {e}")

    @staticmethod
    async def update_subscription_limit(user_id: int, limit: int):
        try:
            async with async_session_factory() as session:
                stmt = update(User).where(User.id == user_id).values(subscription_limit=limit)
                await session.execute(stmt)
                await session.commit()
        except Exception as e:
            logger.error(f"update_subscription_limit error: {e}")

    @staticmethod
    async def update_fragment_setting(user_id: int, state: bool):
        try:
            async with async_session_factory() as session:
                stmt = update(User).where(User.id == user_id).values(use_fragment=state)
                await session.execute(stmt)
                await session.commit()
        except Exception as e:
            logger.error(f"update_fragment_setting error: {e}")

    @staticmethod
    async def get_user_protocol_filter(user_id: int) -> str | None:
        try:
            async with async_session_factory() as session:
                user = await session.get(User, user_id)
                if user:
                    return user.protocol_filter
                return None
        except Exception as e:
            logger.error(f"get_user_protocol_filter error: {e}")
            return None

    @staticmethod
    async def update_user_protocol_filter(user_id: int, protocol: str | None):
        try:
            async with async_session_factory() as session:
                stmt = update(User).where(User.id == user_id).values(protocol_filter=protocol)
                await session.execute(stmt)
                await session.commit()
        except Exception as e:
            logger.error(f"update_user_protocol_filter error: {e}")

    @staticmethod
    async def get_users_with_region(region: str) -> list[int]:
        try:
            async with async_session_factory() as session:
                stmt = select(User.id).where(User.country_filter.like(f"%{region}%"))
                result = await session.execute(stmt)
                return result.scalars().all()
        except Exception as e:
            logger.error(f"get_users_with_region error: {e}")
            return []

    @staticmethod
    async def delete_user(user_id: int) -> bool:
        try:
            deleted = await UserRepo.delete_users([user_id])
            return deleted > 0
        except Exception as e:
            logger.error(f"delete_user error: {e}")
            return False

    @staticmethod
    async def delete_users(user_ids: list[int]) -> int:
        if not user_ids:
            return 0

        try:
            unique_ids = sorted({int(user_id) for user_id in user_ids if user_id})
            if not unique_ids:
                return 0

            async with async_session_factory() as session:
                await session.execute(
                    delete(UserGroup).where(UserGroup.user_id.in_(unique_ids))
                )
                result = await session.execute(delete(User).where(User.id.in_(unique_ids)))
                await session.commit()

            try:
                rowcount = int(result.rowcount or 0)
                if rowcount < 0:
                    return len(unique_ids)
                return rowcount
            except Exception as e:
                logger.warning(f"delete_users rowcount error: {e}")
                return len(unique_ids)
        except Exception as e:
            logger.error(f"delete_users error: {e}")
            return 0

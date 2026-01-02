from sqlalchemy import select, func, delete, update, distinct
from database.core import async_session_factory
from database.models import User, Subscription

class DB:
    @staticmethod
    async def add_user(user_id: int, username: str):
        async with async_session_factory() as session:
            user = await session.get(User, user_id)
            if not user:
                user = User(id=user_id, username=username)
                session.add(user)
                await session.commit()

    @staticmethod
    async def get_stats():
        """Полная статистика для Админа"""
        async with async_session_factory() as session:
            users_count = await session.scalar(select(func.count(User.id)))
            subs_count = await session.scalar(select(func.count(Subscription.id)))
            active_subs = await session.scalar(select(func.count(Subscription.id)).where(Subscription.is_active == True))
            
            regions = await session.execute(
                select(Subscription.region, func.count(Subscription.id))
                .group_by(Subscription.region)
            )
            regions_stat = "\n".join([f"{r}: {c} шт." for r, c in regions.all()])
            
            return {
                "users": users_count,
                "total_subs": subs_count,
                "active_subs": active_subs,
                "regions": regions_stat
            }

    @staticmethod
    async def get_public_stats():
        """Легкая статистика для Юзера"""
        async with async_session_factory() as session:
            active_subs = await session.scalar(select(func.count(Subscription.id)).where(Subscription.is_active == True))
            regions_count = await session.scalar(select(func.count(distinct(Subscription.region))).where(Subscription.is_active == True))
            return {
                "active": active_subs or 0,
                "regions": regions_count or 0
            }

    @staticmethod
    async def get_all_users():
        async with async_session_factory() as session:
            result = await session.execute(select(User.id))
            return result.scalars().all()

    @staticmethod
    async def get_regions():
        async with async_session_factory() as session:
            result = await session.execute(
                select(Subscription.region)
                .where(Subscription.is_active == True)
                .distinct()
                .order_by(Subscription.region)
            )
            return result.scalars().all()

    @staticmethod
    async def get_subs_by_region(region: str):
        async with async_session_factory() as session:
            result = await session.execute(
                select(Subscription)
                .where(Subscription.region == region)
                .order_by(Subscription.latency_ms)
            )
            return result.scalars().all()

    @staticmethod
    async def get_sub_by_id(sub_id: int):
        async with async_session_factory() as session:
            return await session.get(Subscription, sub_id)

    @staticmethod
    async def delete_sub(sub_id: int):
        async with async_session_factory() as session:
            stmt = delete(Subscription).where(Subscription.id == sub_id)
            await session.execute(stmt)
            await session.commit()
            
    @staticmethod
    async def toggle_active(sub_id: int, current_state: bool):
        async with async_session_factory() as session:
            stmt = update(Subscription).where(Subscription.id == sub_id).values(is_active=not current_state)
            await session.execute(stmt)
            await session.commit()

    # --- НОВЫЕ МЕТОДЫ ДЛЯ ПРОВЕРКИ ---
    @staticmethod
    async def get_all_subscriptions_for_check():
        """Возвращает ВСЕ подписки (даже неактивные) для перепроверки"""
        async with async_session_factory() as session:
            result = await session.execute(select(Subscription))
            return result.scalars().all()

    @staticmethod
    async def update_sub_status(sub_id: int, is_active: bool, latency: int):
        """Обновляет статус и пинг подписки"""
        async with async_session_factory() as session:
            stmt = update(Subscription).where(Subscription.id == sub_id).values(
                is_active=is_active,
                latency_ms=latency
            )
            await session.execute(stmt)
            await session.commit()
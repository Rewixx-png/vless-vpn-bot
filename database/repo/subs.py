from sqlalchemy import select, delete, update
from database.core import async_session_factory
from database.models import Subscription

class SubRepo:
    @staticmethod
    async def get_all_subscriptions_for_check():
        async with async_session_factory() as session:
            result = await session.execute(select(Subscription))
            return result.scalars().all()

    @staticmethod
    async def get_unknown_regions_subs():
        async with async_session_factory() as session:
            result = await session.execute(
                select(Subscription)
                .where(Subscription.region.like("%Unknown%"))
            )
            return result.scalars().all()

    @staticmethod
    async def get_all_active_keys() -> list[str]:
        """Все активные ключи (устаревший метод, лучше использовать get_smart_keys)"""
        async with async_session_factory() as session:
            stmt = (
                select(Subscription.vless_key)
                .where(Subscription.is_active == True)
                .order_by(Subscription.latency_ms) # Сортируем по скорости всегда
            )
            result = await session.execute(stmt)
            return result.scalars().all()

    @staticmethod
    async def get_smart_keys(regions: list[str] | None, limit: int = 0) -> list[str]:
        """
        Умная выборка ключей для подписки.
        1. Фильтр по регионам (если задан).
        2. Сортировка по пингу (лучшие сверху).
        3. Обрезание по лимиту (если limit > 0).
        """
        async with async_session_factory() as session:
            stmt = (
                select(Subscription.vless_key)
                .where(Subscription.is_active == True)
            )

            # 1. Фильтр стран
            if regions:
                stmt = stmt.where(Subscription.region.in_(regions))
            
            # 2. Сортировка (быстрые первыми)
            stmt = stmt.order_by(Subscription.latency_ms.asc())

            # 3. Лимит
            if limit > 0:
                stmt = stmt.limit(limit)

            result = await session.execute(stmt)
            return result.scalars().all()

    @staticmethod
    async def get_filtered_active_keys(regions: list[str]) -> list[str]:
        """Legacy wrapper"""
        return await SubRepo.get_smart_keys(regions, limit=0)

    @staticmethod
    async def get_regions(protocol: str = None):
        async with async_session_factory() as session:
            stmt = select(Subscription.region).where(Subscription.is_active == True)
            if protocol:
                stmt = stmt.where(Subscription.vless_key.startswith(f"{protocol}://"))
            stmt = stmt.distinct().order_by(Subscription.region)
            result = await session.execute(stmt)
            return result.scalars().all()

    @staticmethod
    async def get_subs_by_region(region: str, protocol: str = None):
        async with async_session_factory() as session:
            stmt = select(Subscription).where(Subscription.region == region)
            if protocol:
                stmt = stmt.where(Subscription.vless_key.startswith(f"{protocol}://"))
            stmt = stmt.order_by(Subscription.latency_ms)
            result = await session.execute(stmt)
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
    async def delete_all_subs():
        """Удаляет ВСЕ подписки из базы данных"""
        async with async_session_factory() as session:
            await session.execute(delete(Subscription))
            await session.commit()

    @staticmethod
    async def toggle_active(sub_id: int, current_state: bool):
        async with async_session_factory() as session:
            stmt = update(Subscription).where(Subscription.id == sub_id).values(is_active=not current_state)
            await session.execute(stmt)
            await session.commit()

    @staticmethod
    async def update_sub_status(sub_id: int, is_active: bool, latency: int):
        async with async_session_factory() as session:
            stmt = update(Subscription).where(Subscription.id == sub_id).values(
                is_active=is_active,
                latency_ms=latency
            )
            await session.execute(stmt)
            await session.commit()

    @staticmethod
    async def update_sub_region(sub_id: int, region: str):
        async with async_session_factory() as session:
            stmt = update(Subscription).where(Subscription.id == sub_id).values(region=region)
            await session.execute(stmt)
            await session.commit()

    @staticmethod
    async def add_subscription(vless_key: str, region: str, latency: int):
        async with async_session_factory() as session:
            sub = Subscription(vless_key=vless_key, region=region, latency_ms=latency)
            session.add(sub)
            await session.commit()
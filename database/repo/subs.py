from sqlalchemy import select, delete, update, func, text
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
                .where(
                    (Subscription.region.like("%Unknown%")) | 
                    (Subscription.region.like("%UNK%"))
                )
            )
            return result.scalars().all()

    @staticmethod
    async def get_all_active_keys() -> list[str]:
        async with async_session_factory() as session:
            stmt = (
                select(Subscription.vless_key)
                .where(Subscription.is_active == True)
                .order_by(Subscription.latency_ms)
            )
            result = await session.execute(stmt)
            return result.scalars().all()

    @staticmethod
    async def get_all_keys_set() -> set[str]:
        async with async_session_factory() as session:
            result = await session.execute(select(Subscription.vless_key))
            return set(result.scalars().all())

    @staticmethod
    async def get_smart_keys(
        regions: list[str] | None, 
        tags: list[str] | None = None,
        limit: int = 0
    ) -> list[Subscription]:
        async with async_session_factory() as session:
            stmt = (
                select(Subscription)
                .where(Subscription.is_active == True)
            )

            if regions:
                stmt = stmt.where(Subscription.region.in_(regions))
            
            if tags:
                if 'ai' in tags:
                    stmt = stmt.where(Subscription.ai_available == True)
                
                if 'fast' in tags:
                    stmt = stmt.where(Subscription.latency_ms < 100)
                
                if 'wl' in tags:
                    stmt = stmt.where(
                        (Subscription.vless_key.like("%security=reality%")) | 
                        (Subscription.vless_key.like("%flow=xtls-rprx-vision%"))
                    )

            stmt = stmt.order_by(Subscription.latency_ms.asc())

            if limit > 0:
                stmt = stmt.limit(limit)

            result = await session.execute(stmt)
            return result.scalars().all()

    @staticmethod
    async def get_regions(protocol: str = None):
        async with async_session_factory() as session:
            stmt = select(Subscription.region).where(Subscription.is_active == True)
            stmt = stmt.distinct().order_by(Subscription.region)
            result = await session.execute(stmt)
            return result.scalars().all()

    @staticmethod
    async def get_subs_by_region(region: str):
        async with async_session_factory() as session:
            stmt = select(Subscription).where(Subscription.region == region)
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
        async with async_session_factory() as session:
            await session.execute(delete(Subscription))
            await session.commit()
    
    @staticmethod
    async def delete_unknown_subs():
        async with async_session_factory() as session:
            stmt = delete(Subscription).where(
                (Subscription.region.like("%Unknown%")) | 
                (Subscription.region.like("%UNK%"))
            )
            await session.execute(stmt)
            await session.commit()

    @staticmethod
    async def delete_subs_by_region(region: str):
        async with async_session_factory() as session:
            stmt = delete(Subscription).where(Subscription.region == region)
            await session.execute(stmt)
            await session.commit()

    @staticmethod
    async def toggle_active(sub_id: int, current_state: bool):
        async with async_session_factory() as session:
            stmt = update(Subscription).where(Subscription.id == sub_id).values(is_active=not current_state)
            await session.execute(stmt)
            await session.commit()

    @staticmethod
    async def update_sub_status(sub_id: int, is_active: bool, latency: int, ai_available: bool = False):
        async with async_session_factory() as session:
            stmt = update(Subscription).where(Subscription.id == sub_id).values(
                is_active=is_active,
                latency_ms=latency,
                ai_available=ai_available
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
    async def add_subscription(vless_key: str, region: str, latency: int, ai_available: bool = False):
        async with async_session_factory() as session:
            existing = await session.scalar(select(Subscription).where(Subscription.vless_key == vless_key))
            if not existing:
                sub = Subscription(
                    vless_key=vless_key, 
                    region=region, 
                    latency_ms=latency,
                    ai_available=ai_available
                )
                session.add(sub)
                await session.commit()

    @staticmethod
    async def count_by_region(region: str) -> int:
        async with async_session_factory() as session:
            count = await session.scalar(
                select(func.count(Subscription.id)).where(Subscription.region == region)
            )
            return count or 0

    @staticmethod
    async def get_worst_in_region(region: str) -> Subscription | None:
        async with async_session_factory() as session:
            stmt = (
                select(Subscription)
                .where(Subscription.region == region)
                .order_by(Subscription.is_active.asc(), Subscription.latency_ms.desc())
                .limit(1)
            )
            result = await session.execute(stmt)
            return result.scalars().first()

    @staticmethod
    async def smart_add_subscription(vless_key: str, region: str, latency: int, ai_available: bool = False) -> bool:
        if "Unknown" in region or "UNK" in region:
            return False

        async with async_session_factory() as session:
            # 1. Быстрая проверка на дубликат
            existing = await session.scalar(select(Subscription.id).where(Subscription.vless_key == vless_key))
            if existing:
                return False

            # 2. Получаем текущее количество
            count = await session.scalar(
                select(func.count(Subscription.id)).where(Subscription.region == region)
            )
            count = count or 0

            # 3. ЛИМИТ 100
            LIMIT = 100

            if count < LIMIT:
                sub = Subscription(
                    vless_key=vless_key, 
                    region=region, 
                    latency_ms=latency,
                    ai_available=ai_available
                )
                session.add(sub)
                await session.commit()
                return True
            else:
                # Если лимит превышен, ищем худший сервер (мертвый или с высоким пингом)
                # is_active ASC -> False (мертвые) идут первыми
                # latency_ms DESC -> Самый большой пинг идет первым
                stmt = (
                    select(Subscription)
                    .where(Subscription.region == region)
                    .order_by(Subscription.is_active.asc(), Subscription.latency_ms.desc())
                    .limit(1)
                )
                worst = (await session.execute(stmt)).scalars().first()

                # Если нашли худшего кандидата
                if worst:
                    # Заменяем ТОЛЬКО если новый сервер лучше (живой против мертвого) 
                    # ИЛИ (оба живые, но новый быстрее)
                    is_better = False
                    if not worst.is_active:
                        is_better = True # Заменяем мертвого всегда
                    elif latency < worst.latency_ms:
                        is_better = True # Заменяем медленного на быстрого
                    
                    if is_better:
                        await session.delete(worst)
                        await session.flush() # Применяем удаление, чтобы освободить место
                        
                        sub = Subscription(
                            vless_key=vless_key, 
                            region=region, 
                            latency_ms=latency,
                            ai_available=ai_available
                        )
                        session.add(sub)
                        await session.commit()
                        return True
        
        return False

    @staticmethod
    async def enforce_limits():
        """
        HARD CLEANUP: Удаляет лишние записи, если их стало больше 100 из-за гонки потоков.
        Оставляет ТОП-100 лучших (Живые + Мин. пинг) для каждой страны.
        """
        async with async_session_factory() as session:
            # SQL запрос для PostgreSQL
            # Удаляем все записи, у которых порядковый номер > 100 в группе по региону
            sql = text("""
                DELETE FROM subscriptions
                WHERE id IN (
                    SELECT id FROM (
                        SELECT id,
                        ROW_NUMBER() OVER (
                            PARTITION BY region 
                            ORDER BY is_active DESC, latency_ms ASC
                        ) as rn
                        FROM subscriptions
                    ) t
                    WHERE t.rn > 100
                );
            """)
            try:
                await session.execute(sql)
                await session.commit()
            except Exception as e:
                print(f"Error enforcing limits: {e}")
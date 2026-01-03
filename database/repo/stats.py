from sqlalchemy import select, func, distinct
from database.core import async_session_factory
from database.models import User, Subscription
import math

class StatsRepo:
    @staticmethod
    async def get_full_stats():
        """Полная статистика для Админа (включая юзеров)"""
        async with async_session_factory() as session:
            users_count = await session.scalar(select(func.count(User.id)))
            subs_count = await session.scalar(select(func.count(Subscription.id)))
            active_subs = await session.scalar(select(func.count(Subscription.id)).where(Subscription.is_active == True))

            regions_stat = await StatsRepo._get_formatted_regions(session)

            return {
                "users": users_count,
                "total_subs": subs_count,
                "active_subs": active_subs,
                "regions": regions_stat
            }

    @staticmethod
    async def get_network_stats():
        """Публичная статистика для Юзеров (только серверы и регионы)"""
        async with async_session_factory() as session:
            active_subs = await session.scalar(select(func.count(Subscription.id)).where(Subscription.is_active == True))
            regions_count = await session.scalar(select(func.count(distinct(Subscription.region))).where(Subscription.is_active == True))
            
            regions_stat = await StatsRepo._get_formatted_regions(session)

            return {
                "active": active_subs or 0,
                "regions_count": regions_count or 0,
                "regions_list": regions_stat
            }

    @staticmethod
    async def get_public_stats():
        """Краткая статистика для главного меню (без списка)"""
        async with async_session_factory() as session:
            active_subs = await session.scalar(select(func.count(Subscription.id)).where(Subscription.is_active == True))
            regions_count = await session.scalar(select(func.count(distinct(Subscription.region))).where(Subscription.is_active == True))
            return {
                "active": active_subs or 0,
                "regions": regions_count or 0
            }

    @staticmethod
    async def _get_formatted_regions(session):
        """Вспомогательный метод для форматирования списка стран в 2 колонки"""
        regions = await session.execute(
            select(Subscription.region, func.count(Subscription.id))
            .where(Subscription.is_active == True)
            .group_by(Subscription.region)
            .order_by(func.count(Subscription.id).desc())
        )
        
        rows = [f"{r}: {c}" for r, c in regions.all()]
        
        if not rows:
            return "Нет данных"

        # Разбиваем на 2 колонки
        total_rows = len(rows)
        mid_index = math.ceil(total_rows / 2)
        
        col1 = rows[:mid_index]
        col2 = rows[mid_index:]

        # Вычисляем максимальную ширину первой колонки
        max_width = max(len(s) for s in col1) + 2 if col1 else 0

        lines = []
        for i in range(len(col1)):
            left = col1[i].ljust(max_width)
            right = col2[i] if i < len(col2) else ""
            
            if right:
                lines.append(f"{left} || {right}")
            else:
                lines.append(left)

        return "\n".join(lines)
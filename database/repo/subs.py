import time
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta, timezone
from sqlalchemy import select, delete, update, func, text, desc, or_
from sqlalchemy.orm import load_only
from database.core import async_session_factory
from database.models import Subscription
from database.repo.blacklist import BlacklistRepo
from config import config

logger = logging.getLogger("SubRepo")

_session_factory = async_session_factory

_cache = {}
_cache_ttl = {}


def _get_cached(key: str, ttl: int = 300):
    now = time.time()
    if key in _cache and key in _cache_ttl:
        if now < _cache_ttl[key]:
            return _cache[key]
        else:
            del _cache[key]
            del _cache_ttl[key]
    return None


def _set_cached(key: str, value: Any, ttl: int = 300):
    _cache[key] = value
    _cache_ttl[key] = time.time() + ttl


def _invalidate_cache(pattern: str = None):
    global _cache, _cache_ttl
    if pattern is None:
        _cache.clear()
        _cache_ttl.clear()
    else:
        keys_to_remove = [k for k in _cache.keys() if pattern in k]
        for k in keys_to_remove:
            del _cache[k]
            if k in _cache_ttl:
                del _cache_ttl[k]


class SubRepo:
    @staticmethod
    async def get_all_subscriptions_for_check():
        async with async_session_factory() as session:
            result = await session.execute(
                select(Subscription).options(
                    load_only(
                        Subscription.id,
                        Subscription.vless_key,
                        Subscription.is_active,
                        Subscription.region,
                    )
                )
            )
            return result.scalars().all()

    @staticmethod
    async def get_active_subscriptions_for_check():
        async with async_session_factory() as session:
            result = await session.execute(
                select(Subscription)
                .where(Subscription.is_active == True)
                .options(
                    load_only(
                        Subscription.id,
                        Subscription.vless_key,
                        Subscription.is_active,
                        Subscription.region,
                    )
                )
            )
            return result.scalars().all()

    @staticmethod
    async def get_dead_subscriptions_for_check():
        async with async_session_factory() as session:
            result = await session.execute(
                select(Subscription)
                .where(Subscription.is_active == False)
                .options(
                    load_only(
                        Subscription.id,
                        Subscription.vless_key,
                        Subscription.is_active,
                        Subscription.region,
                    )
                )
            )
            return result.scalars().all()

    @staticmethod
    async def get_candidates_for_stability(limit: int = 200):
        async with async_session_factory() as session:
            result = await session.execute(
                select(Subscription)
                .where(Subscription.is_active == True)
                .order_by(
                    desc(Subscription.stability_streak), desc(Subscription.speed_mbps)
                )
                .limit(limit)
            )
            return result.scalars().all()

    @staticmethod
    async def get_unknown_regions_subs():
        async with async_session_factory() as session:
            result = await session.execute(
                select(Subscription).where(
                    or_(
                        Subscription.region.ilike("%unk%"),
                        Subscription.region.ilike("%unknown%"),
                        Subscription.region == "",
                        Subscription.region.is_(None),
                    )
                )
            )
            return result.scalars().all()

    @staticmethod
    async def get_all_active_keys() -> list:
        async with async_session_factory() as session:
            stmt = (
                select(Subscription.vless_key)
                .where(
                    Subscription.is_active == True,
                    Subscription.speed_mbps > 0,
                )
                .order_by(Subscription.speed_mbps.desc())
            )
            result = await session.execute(stmt)
            return result.scalars().all()

    @staticmethod
    async def get_all_keys_set() -> set:
        cache_key = "all_keys_set"
        cached = _get_cached(cache_key, ttl=config.CACHE_TTL)
        if cached is not None:
            return cached

        async with async_session_factory() as session:
            result = await session.execute(select(Subscription.vless_key))
            keys = set(result.scalars().all())
            _set_cached(cache_key, keys, ttl=config.CACHE_TTL)
            return keys

    @staticmethod
    async def get_smart_keys(
        regions: list | None,
        tags: list | None = None,
        limit: int = 0,
        auto_clean: bool = False,
    ) -> list:
        async with async_session_factory() as session:
            stmt = select(Subscription).where(
                Subscription.is_active == True,
                Subscription.speed_mbps > 0,
            )

            if auto_clean:
                time_threshold = datetime.now(timezone.utc) - timedelta(minutes=30)
                stmt = stmt.where(Subscription.last_checked_at >= time_threshold)

            if regions:
                if "__NONE__" in regions:
                    stmt = stmt.where(1 == 0)
                else:
                    stmt = stmt.where(Subscription.region.in_(regions))

            if tags:
                if "ai" in tags:
                    stmt = stmt.where(Subscription.ai_available == True)

                if "fast" in tags:
                    stmt = stmt.where(Subscription.speed_mbps >= 100.0)

                if "wl" in tags:
                    stmt = stmt.where(
                        (Subscription.vless_key.like("%security=reality%"))
                        | (Subscription.vless_key.like("%flow=xtls-rprx-vision%"))
                    )

                if "stable" in tags:
                    stmt = stmt.where(Subscription.stability_streak >= 144)

                if "no_ads" in tags:
                    stmt = stmt.where(Subscription.no_ads == True)

            stmt = stmt.order_by(Subscription.speed_mbps.desc())

            if limit > 0:
                stmt = stmt.limit(limit)

            result = await session.execute(stmt)
            return result.scalars().all()

    @staticmethod
    async def get_regions(protocol: str = None):
        cache_key = f"regions_{protocol}"
        cached = _get_cached(cache_key, ttl=60)
        if cached is not None:
            return cached

        async with async_session_factory() as session:
            stmt = select(Subscription.region).where(
                Subscription.is_active == True,
                Subscription.speed_mbps > 0,
            )
            stmt = stmt.distinct().order_by(Subscription.region)
            result = await session.execute(stmt)
            regions = result.scalars().all()
            _set_cached(cache_key, regions, ttl=60)
            return regions

    @staticmethod
    async def get_subs_by_region(region: str):
        async with async_session_factory() as session:
            stmt = select(Subscription).where(Subscription.region == region)
            stmt = stmt.order_by(Subscription.speed_mbps.desc())
            result = await session.execute(stmt)
            return result.scalars().all()

    @staticmethod
    async def get_sub_by_id(sub_id: int):
        async with async_session_factory() as session:
            return await session.get(Subscription, sub_id)

    @staticmethod
    async def get_subs_by_ids(sub_ids: List[int]) -> List[Subscription]:
        if not sub_ids:
            return []
        async with async_session_factory() as session:
            stmt = select(Subscription).where(Subscription.id.in_(sub_ids))
            result = await session.execute(stmt)
            return result.scalars().all()

    @staticmethod
    async def batch_update_status(updates: List[Dict[str, Any]]):
        if not updates:
            return

        updates.sort(key=lambda x: x["id"])

        async with async_session_factory() as session:
            case_active = []
            case_latency = []
            case_speed = []
            case_ai = []
            case_no_ads = []
            case_death = []
            ids = []

            for upd in updates:
                ids.append(upd["id"])
                case_active.append(
                    f"WHEN {upd['id']} THEN {str(upd['is_active']).lower()}"
                )
                case_latency.append(f"WHEN {upd['id']} THEN {upd['latency_ms']}")
                case_speed.append(f"WHEN {upd['id']} THEN {upd.get('speed_mbps', 0.0)}")
                case_ai.append(
                    f"WHEN {upd['id']} THEN {str(upd['ai_available']).lower()}"
                )
                case_no_ads.append(
                    f"WHEN {upd['id']} THEN {str(upd.get('no_ads', False)).lower()}"
                )
                if (not upd["is_active"]) and upd.get("was_active", False):
                    case_death.append(f"WHEN {upd['id']} THEN death_count + 1")
                else:
                    case_death.append(f"WHEN {upd['id']} THEN death_count")

            sql = text(f"""
                UPDATE subscriptions
                SET 
                    is_active = CASE id {" ".join(case_active)} END,
                    latency_ms = CASE id {" ".join(case_latency)} END,
                    speed_mbps = CASE id {" ".join(case_speed)} END,
                    ai_available = CASE id {" ".join(case_ai)} END,
                    no_ads = CASE id {" ".join(case_no_ads)} END,
                    death_count = CASE id {" ".join(case_death)} END,
                    last_checked_at = NOW()
                WHERE id IN ({",".join(map(str, ids))})
            """)

            try:
                await session.execute(sql)
                await session.commit()
                _invalidate_cache("subscription")
            except Exception as e:
                logger.error(f"Batch update status failed: {e}")
                await session.rollback()

    @staticmethod
    async def batch_update_regions(updates: List[Dict[str, Any]]):
        if not updates:
            return

        updates.sort(key=lambda x: x["id"])

        async with async_session_factory() as session:
            case_regions = []
            ids = []

            for upd in updates:
                ids.append(upd["id"])
                region = upd["region"].replace("'", "''")
                case_regions.append(f"WHEN {upd['id']} THEN '{region}'")

            sql = text(f"""
                UPDATE subscriptions
                SET region = CASE id {" ".join(case_regions)} END
                WHERE id IN ({",".join(map(str, ids))})
            """)

            try:
                await session.execute(sql)
                await session.commit()
                _invalidate_cache("subscription")
            except Exception as e:
                logger.error(f"Batch update regions failed: {e}")
                await session.rollback()

    @staticmethod
    async def batch_update_stability(updates: List[Dict[str, Any]]):
        if not updates:
            return

        updates.sort(key=lambda x: x["id"])

        async with async_session_factory() as session:
            case_streak = []
            ids = []

            for upd in updates:
                sub_id = upd["id"]
                ids.append(sub_id)
                is_alive = upd.get("is_active", upd.get("is_alive", False))
                if is_alive:
                    case_streak.append(f"WHEN {sub_id} THEN stability_streak + 1")
                else:
                    case_streak.append(f"WHEN {sub_id} THEN 0")

            sql = text(f"""
                UPDATE subscriptions
                SET stability_streak = CASE id {" ".join(case_streak)} END
                WHERE id IN ({",".join(map(str, ids))})
            """)

            try:
                await session.execute(sql)
                await session.commit()
            except Exception as e:
                logger.error(f"Batch update stability failed: {e}")
                await session.rollback()

    @staticmethod
    async def batch_update_keys(updates: List[Dict[str, Any]]):
        if not updates:
            return

        async with async_session_factory() as session:
            for upd in updates:
                try:
                    stmt = (
                        update(Subscription)
                        .where(Subscription.id == upd["id"])
                        .values(vless_key=upd["vless_key"])
                    )
                    await session.execute(stmt)
                    await session.commit()
                except Exception as e:
                    await session.rollback()
                    logger.warning(f"Batch update key skipped for sub {upd['id']}: {e}")

            _invalidate_cache("subscription")

    @staticmethod
    async def update_sub_key(sub_id: int, new_key: str):
        async with async_session_factory() as session:
            stmt = (
                update(Subscription)
                .where(Subscription.id == sub_id)
                .values(vless_key=new_key)
            )
            await session.execute(stmt)
            await session.commit()

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
    async def cleanup_dead_subs(max_deaths: int = 5) -> int:
        async with async_session_factory() as session:
            stmt = delete(Subscription).where(Subscription.death_count >= max_deaths)
            result = await session.execute(stmt)
            await session.commit()
            return result.rowcount

    @staticmethod
    async def move_unknown_to_blacklist():
        async with async_session_factory() as session:
            stmt = select(Subscription).where(
                or_(
                    Subscription.region.ilike("%unk%"),
                    Subscription.region.ilike("%unknown%"),
                    Subscription.region == "",
                    Subscription.region.is_(None),
                )
            )
            result = await session.execute(stmt)
            subs = result.scalars().all()

            if not subs:
                return 0

            from database.models import BlacklistedItem
            from sqlalchemy.dialects.postgresql import insert as pg_insert

            count = 0
            for sub in subs:
                ins = (
                    pg_insert(BlacklistedItem)
                    .values(
                        vless_key=sub.vless_key, reason="Unknown Region (Admin Action)"
                    )
                    .on_conflict_do_nothing()
                )
                await session.execute(ins)
                count += 1

            del_stmt = delete(Subscription).where(
                or_(
                    Subscription.region.ilike("%unk%"),
                    Subscription.region.ilike("%unknown%"),
                    Subscription.region == "",
                    Subscription.region.is_(None),
                )
            )
            await session.execute(del_stmt)
            await session.commit()
            return count

    @staticmethod
    async def delete_subs_by_region(region: str):
        async with async_session_factory() as session:
            stmt = delete(Subscription).where(Subscription.region == region)
            await session.execute(stmt)
            await session.commit()

    @staticmethod
    async def toggle_active(sub_id: int, current_state: bool):
        async with async_session_factory() as session:
            stmt = (
                update(Subscription)
                .where(Subscription.id == sub_id)
                .values(is_active=not current_state)
            )
            await session.execute(stmt)
            await session.commit()

    @staticmethod
    async def update_sub_status(
        sub_id: int,
        is_active: bool,
        latency: int,
        speed_mbps: float,
        ai_available: bool = False,
        no_ads: bool = False,
    ):
        async with async_session_factory() as session:
            stmt = (
                update(Subscription)
                .where(Subscription.id == sub_id)
                .values(
                    is_active=is_active,
                    latency_ms=latency,
                    speed_mbps=speed_mbps,
                    ai_available=ai_available,
                    no_ads=no_ads,
                    last_checked_at=func.now(),
                )
            )
            await session.execute(stmt)
            await session.commit()

    @staticmethod
    async def update_sub_region(sub_id: int, region: str):
        async with async_session_factory() as session:
            stmt = (
                update(Subscription)
                .where(Subscription.id == sub_id)
                .values(region=region)
            )
            await session.execute(stmt)
            await session.commit()

    @staticmethod
    async def add_subscription(
        vless_key: str,
        region: str,
        latency: int,
        speed_mbps: float,
        ai_available: bool = False,
        no_ads: bool = False,
    ):
        async with async_session_factory() as session:
            existing = await session.scalar(
                select(Subscription).where(Subscription.vless_key == vless_key)
            )
            if not existing:
                sub = Subscription(
                    vless_key=vless_key,
                    region=region,
                    latency_ms=latency,
                    speed_mbps=speed_mbps,
                    ai_available=ai_available,
                    no_ads=no_ads,
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
                .order_by(Subscription.is_active.asc(), Subscription.speed_mbps.asc())
                .limit(1)
            )
            result = await session.execute(stmt)
            return result.scalars().first()

    @staticmethod
    async def smart_add_subscription(
        vless_key: str,
        region: str,
        latency: int,
        speed_mbps: float,
        ai_available: bool = False,
        no_ads: bool = False,
    ) -> bool:
        is_banned = await BlacklistRepo.is_blacklisted(vless_key)
        if is_banned:
            return False

        if not region or region.strip() == "":
            region = "🌍 Unk"

        async with async_session_factory() as session:
            existing = await session.scalar(
                select(Subscription.id).where(Subscription.vless_key == vless_key)
            )
            if existing:
                return False

            sub = Subscription(
                vless_key=vless_key,
                region=region,
                latency_ms=latency,
                speed_mbps=speed_mbps,
                ai_available=ai_available,
                no_ads=no_ads,
            )
            session.add(sub)
            await session.commit()

            return True

    @staticmethod
    async def enforce_limits():
        pass

    @staticmethod
    async def get_total_count() -> int:
        async with async_session_factory() as session:
            result = await session.execute(select(func.count(Subscription.id)))
            return result.scalar() or 0

    @staticmethod
    async def get_active_count() -> int:
        async with async_session_factory() as session:
            result = await session.execute(
                select(func.count(Subscription.id)).where(
                    Subscription.is_active == True
                )
            )
            return result.scalar() or 0

    @staticmethod
    async def get_dead_count() -> int:
        async with async_session_factory() as session:
            result = await session.execute(
                select(func.count(Subscription.id)).where(
                    Subscription.is_active == False
                )
            )
            return result.scalar() or 0

    @staticmethod
    async def get_unknown_region_count() -> int:
        async with async_session_factory() as session:
            result = await session.execute(
                select(func.count(Subscription.id)).where(
                    or_(
                        Subscription.region.ilike("%unk%"),
                        Subscription.region.ilike("%unknown%"),
                        Subscription.region == "",
                        Subscription.region.is_(None),
                    )
                )
            )
            return result.scalar() or 0

    @staticmethod
    async def get_stats_summary() -> dict:
        async with async_session_factory() as session:
            total = await session.execute(select(func.count(Subscription.id)))
            active = await session.execute(
                select(func.count(Subscription.id)).where(
                    Subscription.is_active == True
                )
            )
            dead = await session.execute(
                select(func.count(Subscription.id)).where(
                    Subscription.is_active == False
                )
            )
            avg_speed = await session.execute(
                select(func.avg(Subscription.speed_mbps)).where(
                    Subscription.is_active == True
                )
            )

            return {
                "total": total.scalar() or 0,
                "active": active.scalar() or 0,
                "dead": dead.scalar() or 0,
                "avg_speed": round(avg_speed.scalar() or 0, 2),
            }

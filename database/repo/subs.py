import time
import logging
from functools import lru_cache
from typing import List, Dict, Any, Optional
from sqlalchemy import select, delete, update, func, text, bindparam
from database.core import async_session_factory
from database.models import Subscription
from database.repo.blacklist import BlacklistRepo

logger = logging.getLogger("SubRepo")

# Simple in-memory cache with TTL
_cache = {}
_cache_ttl = {}

def _get_cached(key: str, ttl: int = 300):
    """Get cached value if not expired"""
    now = time.time()
    if key in _cache and key in _cache_ttl:
        if now < _cache_ttl[key]:
            return _cache[key]
        else:
            del _cache[key]
            del _cache_ttl[key]
    return None

def _set_cached(key: str, value: Any, ttl: int = 300):
    """Set cached value with TTL"""
    _cache[key] = value
    _cache_ttl[key] = time.time() + ttl

def _invalidate_cache(pattern: str = None):
    """Invalidate cache entries matching pattern"""
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
            result = await session.execute(select(Subscription))
            return result.scalars().all()

    @staticmethod
    async def get_active_subscriptions_for_check():
        async with async_session_factory() as session:
            result = await session.execute(select(Subscription).where(Subscription.is_active == True))
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
        """Get unique regions with caching"""
        cache_key = f"regions_{protocol}"
        cached = _get_cached(cache_key, ttl=60)  # Cache for 60 seconds
        if cached is not None:
            return cached
            
        async with async_session_factory() as session:
            stmt = select(Subscription.region).where(Subscription.is_active == True)
            stmt = stmt.distinct().order_by(Subscription.region)
            result = await session.execute(stmt)
            regions = result.scalars().all()
            _set_cached(cache_key, regions, ttl=60)
            return regions

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
    async def get_subs_by_ids(sub_ids: List[int]) -> List[Subscription]:
        """Fetch multiple subscriptions by IDs in one query"""
        if not sub_ids:
            return []
        async with async_session_factory() as session:
            stmt = select(Subscription).where(Subscription.id.in_(sub_ids))
            result = await session.execute(stmt)
            return result.scalars().all()
    
    @staticmethod
    async def batch_update_status(updates: List[Dict[str, Any]]):
        """Batch update subscription status - reduces N queries to 1"""
        if not updates:
            return
        
        async with async_session_factory() as session:
            logger.info(f"[DB] batch_update_status: {len(updates)} ids")
            case_active = []
            case_latency = []
            case_ai = []
            case_death = []
            ids = []
            
            for upd in updates:
                ids.append(upd["id"])
                case_active.append(f"WHEN {upd['id']} THEN {str(upd['is_active']).lower()}")
                case_latency.append(f"WHEN {upd['id']} THEN {upd['latency_ms']}")
                case_ai.append(f"WHEN {upd['id']} THEN {str(upd['ai_available']).lower()}")
                death_count = upd.get("death_count", 0)
                case_death.append(f"WHEN {upd['id']} THEN {death_count}")
            
            sql = text(f"""
                UPDATE subscriptions
                SET 
                    is_active = CASE id {' '.join(case_active)} END,
                    latency_ms = CASE id {' '.join(case_latency)} END,
                    ai_available = CASE id {' '.join(case_ai)} END,
                    death_count = CASE id {' '.join(case_death)} END
                WHERE id IN ({','.join(map(str, ids))})
            """)
            
            await session.execute(sql)
            await session.commit()
            _invalidate_cache("subscription")
    
    @staticmethod
    async def batch_update_regions(updates: List[Dict[str, Any]]):
        """Batch update subscription regions"""
        if not updates:
            return
        
        async with async_session_factory() as session:
            logger.info(f"[DB] batch_update_regions: {len(updates)} ids")
            case_regions = []
            ids = []
            
            for upd in updates:
                ids.append(upd["id"])
                # Escape single quotes in region names
                region = upd["region"].replace("'", "''")
                case_regions.append(f"WHEN {upd['id']} THEN '{region}'")
            
            sql = text(f"""
                UPDATE subscriptions
                SET region = CASE id {' '.join(case_regions)} END
                WHERE id IN ({','.join(map(str, ids))})
            """)
            
            await session.execute(sql)
            await session.commit()
            _invalidate_cache("subscription")

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
    async def move_unknown_to_blacklist():
        """Move all UNKNOWN subs to blacklist table and delete from subs"""
        async with async_session_factory() as session:
            # 1. Get all unknown subs
            stmt = select(Subscription).where(
                (Subscription.region.like("%Unknown%")) | 
                (Subscription.region.like("%UNK%"))
            )
            result = await session.execute(stmt)
            subs = result.scalars().all()
            
            if not subs:
                return 0
                
            # 2. Add to blacklist repo logic (doing raw here for atomicity)
            # Need to import BlacklistedItem locally to avoid circular import if any
            from database.models import BlacklistedItem
            from sqlalchemy.dialects.postgresql import insert as pg_insert
            
            count = 0
            for sub in subs:
                # Insert ignore duplicate
                ins = pg_insert(BlacklistedItem).values(
                    vless_key=sub.vless_key, 
                    reason="Unknown Region (Admin Action)"
                ).on_conflict_do_nothing()
                await session.execute(ins)
                count += 1
            
            # 3. Delete from subscriptions
            del_stmt = delete(Subscription).where(
                (Subscription.region.like("%Unknown%")) | 
                (Subscription.region.like("%UNK%"))
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
        """Add subscription if not duplicate and not blacklisted."""
        
        # 1. Check Blacklist
        is_banned = await BlacklistRepo.is_blacklisted(vless_key)
        if is_banned:
            logger.debug(f"[ADD] Rejected - Blacklisted: {vless_key[:50]}...")
            return False

        if "Unknown" in region or "UNK" in region:
            logger.warning(f"[ADD] Rejected - Unknown region: {region[:50]}")
            return False

        async with async_session_factory() as session:
            # 2. Check for duplicate
            existing = await session.scalar(select(Subscription.id).where(Subscription.vless_key == vless_key))
            if existing:
                logger.debug(f"[ADD] Rejected - Duplicate: {vless_key[:50]}...")
                return False

            count = await session.scalar(
                select(func.count(Subscription.id)).where(Subscription.region == region)
            )
            count = count or 0
            
            sub = Subscription(
                vless_key=vless_key, 
                region=region, 
                latency_ms=latency,
                ai_available=ai_available
            )
            session.add(sub)
            await session.commit()
            
            logger.info(f"[ADD] SUCCESS - Region: {region}, Count: {count+1}, Latency: {latency}ms, AI: {ai_available}")
            return True

    @staticmethod
    async def enforce_limits():
        logger.info("[CLEANUP] Auto-cleanup is DISABLED. No configs will be deleted automatically.")

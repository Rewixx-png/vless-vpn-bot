import time
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta, timezone
from sqlalchemy import select, delete, update, func, text, or_
from sqlalchemy.orm import load_only
from database.core import async_session_factory
from database.models import Subscription
from database.repo.blacklist import BlacklistRepo
from config import config

logger = logging.getLogger("SubRepo")

_session_factory = async_session_factory

_cache = {}
_cache_ttl = {}
_MIN_ACTIVE_SPEED_MBPS = 10.0
_DEACTIVATE_DEATH_COUNT = 3
_PURGE_DEATH_COUNT = 10

_TAG_PATTERNS = {
    "mts": [
        "mts",
        "\u043c\u0442\u0441",
        "%d0%bc%d1%82%d1%81",
    ],
    "beeline": [
        "beeline",
        "\u0431\u0438\u043b\u0430\u0439\u043d",
        "%d0%b1%d0%b8%d0%bb%d0%b0%d0%b9%d0%bd",
    ],
    "megafon": [
        "megafon",
        "\u043c\u0435\u0433\u0430\u0444\u043e\u043d",
        "%d0%bc%d0%b5%d0%b3%d0%b0%d1%84%d0%be%d0%bd",
    ],
    "tele2": [
        "tele2",
        "\u0442\u0435\u043b\u04352",
        "%d1%82%d0%b5%d0%bb%d0%b52",
    ],
    "wifi": [
        "wifi",
        "wi-fi",
        "wlan",
        "home",
        "fiber",
        "broadband",
        "ftth",
        "\u0432\u0430\u0439\u0444\u0430\u0439",
        "%d0%b2%d0%b0%d0%b9%d1%84%d0%b0%d0%b9",
    ],
}

_MOBILE_EXTRA_PATTERNS = [
    "mobile",
    "cell",
    "lte",
    "4g",
    "5g",
    "sim",
    "gsm",
    "yota",
    "\u043c\u043e\u0431\u0438\u043b",
    "%d0%bc%d0%be%d0%b1%d0%b8%d0%bb",
]


def _build_link_tag_condition(tokens: list[str]):
    lowered_link = func.lower(Subscription.vless_key)
    normalized_tokens = [str(token).strip().lower() for token in tokens if str(token).strip()]
    if not normalized_tokens:
        return None
    return or_(*[lowered_link.like(f"%{token}%") for token in normalized_tokens])


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
                        Subscription.death_count,
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
                        Subscription.death_count,
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
                        Subscription.death_count,
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
                    Subscription.last_checked_at.asc(),
                    Subscription.stability_streak.asc(),
                    Subscription.speed_mbps.asc(),
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
                    Subscription.speed_mbps >= _MIN_ACTIVE_SPEED_MBPS,
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
                Subscription.speed_mbps >= _MIN_ACTIVE_SPEED_MBPS,
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
                normalized_tags = {str(tag).strip().lower() for tag in tags if str(tag).strip()}

                if "ai" in normalized_tags:
                    stmt = stmt.where(Subscription.ai_available == True)

                if "fast" in normalized_tags:
                    stmt = stmt.where(Subscription.speed_mbps >= 100.0)

                if "wl" in normalized_tags:
                    stmt = stmt.where(
                        (Subscription.vless_key.like("%security=reality%"))
                        | (Subscription.vless_key.like("%flow=xtls-rprx-vision%"))
                    )

                if "grpc" in normalized_tags:
                    stmt = stmt.where(
                        (Subscription.vless_key.ilike("%type=grpc%"))
                        | (Subscription.vless_key.ilike("%servicename=%"))
                    )

                if "stable" in normalized_tags:
                    stmt = stmt.where(Subscription.stability_streak >= 144)

                if "no_ads" in normalized_tags:
                    stmt = stmt.where(Subscription.no_ads == True)

                if "mts" in normalized_tags:
                    condition = _build_link_tag_condition(_TAG_PATTERNS.get("mts", []))
                    if condition is not None:
                        stmt = stmt.where(condition)

                if "beeline" in normalized_tags:
                    condition = _build_link_tag_condition(_TAG_PATTERNS.get("beeline", []))
                    if condition is not None:
                        stmt = stmt.where(condition)

                if "megafon" in normalized_tags:
                    condition = _build_link_tag_condition(_TAG_PATTERNS.get("megafon", []))
                    if condition is not None:
                        stmt = stmt.where(condition)

                if "tele2" in normalized_tags:
                    condition = _build_link_tag_condition(_TAG_PATTERNS.get("tele2", []))
                    if condition is not None:
                        stmt = stmt.where(condition)

                if "wifi" in normalized_tags:
                    condition = _build_link_tag_condition(_TAG_PATTERNS.get("wifi", []))
                    if condition is not None:
                        stmt = stmt.where(condition)

                if "mobile" in normalized_tags:
                    mobile_patterns = []
                    for operator_tag in ("mts", "beeline", "megafon", "tele2"):
                        mobile_patterns.extend(_TAG_PATTERNS.get(operator_tag, []))
                    mobile_patterns.extend(_MOBILE_EXTRA_PATTERNS)

                    condition = _build_link_tag_condition(mobile_patterns)
                    if condition is not None:
                        stmt = stmt.where(condition)

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
                Subscription.speed_mbps >= _MIN_ACTIVE_SPEED_MBPS,
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

        normalized_by_id: Dict[int, Dict[str, Any]] = {}
        for upd in updates:
            try:
                sub_id = int(upd.get("id"))
            except Exception:
                continue

            if sub_id <= 0:
                continue

            check_status = str(upd.get("check_status", "") or "").strip().lower()
            if check_status not in {"alive", "dead", "sys_err"}:
                if bool(upd.get("sys_err", False)):
                    check_status = "sys_err"
                elif bool(upd.get("is_active", upd.get("is_alive", False))):
                    check_status = "alive"
                else:
                    check_status = "dead"

            try:
                latency_ms = int(upd.get("latency_ms", upd.get("latency", 9999)) or 9999)
            except Exception:
                latency_ms = 9999

            latency_ms = max(1, min(latency_ms, 9999))

            try:
                speed_mbps = float(upd.get("speed_mbps", 0.0) or 0.0)
            except Exception:
                speed_mbps = 0.0

            if speed_mbps != speed_mbps or speed_mbps < 0.0:
                speed_mbps = 0.0

            normalized_by_id[sub_id] = {
                "id": sub_id,
                "check_status": check_status,
                "latency_ms": latency_ms,
                "speed_mbps": speed_mbps,
                "ai_available": bool(upd.get("ai_available", upd.get("ai", False))),
                "no_ads": bool(upd.get("no_ads", False)),
            }

        if not normalized_by_id:
            return

        normalized_updates = [
            normalized_by_id[sub_id] for sub_id in sorted(normalized_by_id)
        ]

        async with async_session_factory() as session:
            case_active = []
            case_latency = []
            case_speed = []
            case_ai = []
            case_no_ads = []
            case_death = []
            case_checked_at = []
            ids = []

            for upd in normalized_updates:
                sub_id = upd["id"]
                status = upd["check_status"]
                ids.append(sub_id)

                if status == "alive":
                    case_active.append(f"WHEN {sub_id} THEN true")
                    case_latency.append(f"WHEN {sub_id} THEN {upd['latency_ms']}")
                    case_speed.append(f"WHEN {sub_id} THEN {upd['speed_mbps']}")
                    case_ai.append(
                        f"WHEN {sub_id} THEN {str(upd['ai_available']).lower()}"
                    )
                    case_no_ads.append(
                        f"WHEN {sub_id} THEN {str(upd['no_ads']).lower()}"
                    )
                    case_death.append(f"WHEN {sub_id} THEN 0")
                    case_checked_at.append(f"WHEN {sub_id} THEN NOW()")
                    continue

                if status == "dead":
                    case_active.append(
                        "WHEN "
                        f"{sub_id} THEN CASE WHEN death_count + 1 >= {_DEACTIVATE_DEATH_COUNT} "
                        "THEN false ELSE true END"
                    )
                    case_latency.append(
                        "WHEN "
                        f"{sub_id} THEN CASE WHEN death_count + 1 >= {_DEACTIVATE_DEATH_COUNT} "
                        "THEN 9999 ELSE latency_ms END"
                    )
                    case_speed.append(
                        "WHEN "
                        f"{sub_id} THEN CASE WHEN death_count + 1 >= {_DEACTIVATE_DEATH_COUNT} "
                        "THEN 0.0 ELSE speed_mbps END"
                    )
                    case_ai.append(
                        "WHEN "
                        f"{sub_id} THEN CASE WHEN death_count + 1 >= {_DEACTIVATE_DEATH_COUNT} "
                        "THEN false ELSE ai_available END"
                    )
                    case_no_ads.append(
                        "WHEN "
                        f"{sub_id} THEN CASE WHEN death_count + 1 >= {_DEACTIVATE_DEATH_COUNT} "
                        "THEN false ELSE no_ads END"
                    )
                    case_death.append(f"WHEN {sub_id} THEN death_count + 1")
                    case_checked_at.append(f"WHEN {sub_id} THEN NOW()")
                    continue

                case_active.append(f"WHEN {sub_id} THEN is_active")
                case_latency.append(f"WHEN {sub_id} THEN latency_ms")
                case_speed.append(f"WHEN {sub_id} THEN speed_mbps")
                case_ai.append(f"WHEN {sub_id} THEN ai_available")
                case_no_ads.append(f"WHEN {sub_id} THEN no_ads")
                case_death.append(f"WHEN {sub_id} THEN death_count")
                case_checked_at.append(f"WHEN {sub_id} THEN last_checked_at")

            sql = text(
                f"""
                UPDATE subscriptions
                SET
                    is_active = CASE id {' '.join(case_active)} ELSE is_active END,
                    latency_ms = CASE id {' '.join(case_latency)} ELSE latency_ms END,
                    speed_mbps = CASE id {' '.join(case_speed)} ELSE speed_mbps END,
                    ai_available = CASE id {' '.join(case_ai)} ELSE ai_available END,
                    no_ads = CASE id {' '.join(case_no_ads)} ELSE no_ads END,
                    death_count = CASE id {' '.join(case_death)} ELSE death_count END,
                    last_checked_at = CASE id {' '.join(case_checked_at)} ELSE last_checked_at END
                WHERE id IN ({','.join(map(str, ids))})
                """
            )

            try:
                await session.execute(sql)
                await session.commit()
                _invalidate_cache("subscription")
                _invalidate_cache("all_keys_set")
                _invalidate_cache("regions_")
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
    async def delete_subs_by_ids(sub_ids: List[int]) -> int:
        if not sub_ids:
            return 0

        unique_ids_set = set()
        for sub_id in sub_ids:
            try:
                value = int(sub_id)
            except Exception:
                continue
            if value > 0:
                unique_ids_set.add(value)

        unique_ids = sorted(unique_ids_set)
        if not unique_ids:
            return 0

        async with async_session_factory() as session:
            stmt = delete(Subscription).where(Subscription.id.in_(unique_ids))
            result = await session.execute(stmt)
            await session.commit()

        _invalidate_cache("subscription")
        _invalidate_cache("all_keys_set")
        _invalidate_cache("regions_")

        try:
            return int(result.rowcount or 0)
        except Exception:
            return len(unique_ids)

    @staticmethod
    async def move_subs_to_blacklist(
        sub_ids: List[int],
        reason: str = "Admin Bulk Blacklist",
    ) -> int:
        if not sub_ids:
            return 0

        unique_ids_set = set()
        for sub_id in sub_ids:
            try:
                value = int(sub_id)
            except Exception:
                continue
            if value > 0:
                unique_ids_set.add(value)

        unique_ids = sorted(unique_ids_set)
        if not unique_ids:
            return 0

        from database.models import BlacklistedItem
        from sqlalchemy.dialects.postgresql import insert as pg_insert

        async with async_session_factory() as session:
            result = await session.execute(
                select(Subscription.id, Subscription.vless_key).where(
                    Subscription.id.in_(unique_ids)
                )
            )
            rows = result.all()
            if not rows:
                return 0

            existing_ids = []
            for row in rows:
                existing_ids.append(int(row.id))
                stmt = (
                    pg_insert(BlacklistedItem)
                    .values(vless_key=row.vless_key, reason=reason)
                    .on_conflict_do_nothing(index_elements=["vless_key"])
                )
                await session.execute(stmt)

            del_result = await session.execute(
                delete(Subscription).where(Subscription.id.in_(existing_ids))
            )
            await session.commit()

        _invalidate_cache("subscription")
        _invalidate_cache("all_keys_set")
        _invalidate_cache("regions_")

        try:
            deleted = int(del_result.rowcount or 0)
            if deleted >= 0:
                return deleted
        except Exception:
            pass
        return len(existing_ids)

    @staticmethod
    async def delete_all_subs() -> int:
        async with async_session_factory() as session:
            result = await session.execute(delete(Subscription))
            await session.commit()
            _invalidate_cache("subscription")
            _invalidate_cache("all_keys_set")
            _invalidate_cache("regions_")
            try:
                return int(result.rowcount or 0)
            except Exception:
                return 0

    @staticmethod
    async def cleanup_dead_subs(max_deaths: int = _PURGE_DEATH_COUNT) -> int:
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
        if float(speed_mbps or 0.0) < _MIN_ACTIVE_SPEED_MBPS:
            return

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
        if float(speed_mbps or 0.0) < _MIN_ACTIVE_SPEED_MBPS:
            return False

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

from typing import Dict, Any

from celery_app import app
from tasks.base import OptimizedTask, setup_log_rotation, _setup_loop_exception_handler, logger
from utils.checker.geo_ip import GeoIP
from database.repo import SubRepo


@app.task(name="tasks.update_geoip_task", base=OptimizedTask, time_limit=600, soft_time_limit=540)
async def update_geoip_task() -> Dict[str, Any]:
    setup_log_rotation()
    _setup_loop_exception_handler()

    success = await GeoIP.update_database()

    resolved = await _resolve_unk_regions()

    return {
        "status": "updated" if success else "failed",
        "unk_resolved": resolved,
    }


@app.task(name="tasks.resolve_unk_regions_task", base=OptimizedTask, time_limit=900, soft_time_limit=840)
async def resolve_unk_regions_task() -> Dict[str, Any]:
    setup_log_rotation()
    _setup_loop_exception_handler()
    resolved = await _resolve_unk_regions()
    return {"resolved": resolved}


async def _resolve_unk_regions() -> int:
    try:
        unk_subs = await SubRepo.get_unknown_regions_subs()
        if not unk_subs:
            return 0

        vless_keys = [s.vless_key for s in unk_subs if s.vless_key]
        if not vless_keys:
            return 0

        updates_by_key = await GeoIP.resolve_unk_by_mmdb(vless_keys)
        if not updates_by_key:
            return 0

        key_to_id = {s.vless_key: s.id for s in unk_subs}
        db_updates = []
        for item in updates_by_key:
            sub_id = key_to_id.get(item["vless_key"])
            if sub_id:
                db_updates.append({"id": sub_id, "region": item["region"]})

        if not db_updates:
            return 0

        chunk_size = 500
        for i in range(0, len(db_updates), chunk_size):
            await SubRepo.batch_update_regions(db_updates[i : i + chunk_size])

        logger.info(f"resolve_unk_regions: resolved {len(db_updates)} UNK entries via MMDB")
        return len(db_updates)

    except Exception as e:
        logger.error(f"resolve_unk_regions failed: {e}")
        return 0

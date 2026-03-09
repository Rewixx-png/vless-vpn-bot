from typing import Dict, Any

from celery_app import app
from tasks.base import OptimizedTask, setup_log_rotation, _setup_loop_exception_handler
from utils.checker.geo_ip import GeoIP

@app.task(name="tasks.update_geoip_task", base=OptimizedTask, time_limit=600, soft_time_limit=540)
async def update_geoip_task() -> Dict[str, Any]:
    setup_log_rotation()
    _setup_loop_exception_handler()
    success = await GeoIP.update_database()
    return {"status": "updated" if success else "failed"}
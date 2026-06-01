from typing import Dict, Any
from celery_app import app
from tasks.base import OptimizedTask, setup_log_rotation, setup_loop_exception_handler_async

@app.task(name="tasks.check_subs_batch_task", base=OptimizedTask, bind=True, max_retries=3, time_limit=3600, soft_time_limit=3540)
async def check_subs_batch_task(self, sub_ids: list[Any]) -> Dict[str, Any]:
    setup_log_rotation()
    await setup_loop_exception_handler_async()
    return {"status": "disabled"}
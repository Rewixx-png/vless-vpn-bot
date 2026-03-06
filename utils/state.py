import logging
from database.repo import SystemRepo

logger = logging.getLogger("BotState")

class BotState:
    @classmethod
    async def set_maintenance(cls, value: bool):
        val_str = "true" if value else "false"
        await SystemRepo.set_config("maintenance_mode", val_str)
        if value:
            logger.warning("⛔️ MAINTENANCE MODE ENABLED. Background tasks paused.")
        else:
            logger.warning("🟢 MAINTENANCE MODE DISABLED. System resuming.")

    @classmethod
    async def is_maintenance(cls) -> bool:
        val = await SystemRepo.get_config("maintenance_mode")
        return val == "true"
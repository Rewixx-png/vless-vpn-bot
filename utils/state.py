import logging

class BotState:
    _maintenance_mode = False
    
    @classmethod
    def set_maintenance(cls, value: bool):
        cls._maintenance_mode = value
        logger = logging.getLogger("BotState")
        if value:
            logger.warning("⛔️ MAINTENANCE MODE ENABLED. Background tasks paused.")
        else:
            logger.warning("🟢 MAINTENANCE MODE DISABLED. System resuming.")

    @classmethod
    def is_maintenance(cls) -> bool:
        return cls._maintenance_mode
from aiogram import Router
from handlers.admin import menu, stats, inventory, broadcast, settings

admin_router = Router()

admin_router.include_router(menu.router)
admin_router.include_router(stats.router)
admin_router.include_router(inventory.router)
admin_router.include_router(broadcast.router)
admin_router.include_router(settings.router)
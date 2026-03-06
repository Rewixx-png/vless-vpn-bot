from aiogram import Router

from handlers.admin.menu import router as menu_router
from handlers.admin.stats import router as stats_router
from handlers.admin.broadcast import router as broadcast_router
from handlers.admin.settings import router as settings_router
from handlers.admin.recheck import router as recheck_router
from handlers.admin.users import router as users_router
from handlers.admin.stable import router as stable_router
from handlers.admin.sources import router as sources_router

from handlers.admin.inventory import router as inventory_router

admin_router = Router()

admin_router.include_router(menu_router)
admin_router.include_router(stats_router)
admin_router.include_router(inventory_router)
admin_router.include_router(broadcast_router)
admin_router.include_router(settings_router)
admin_router.include_router(recheck_router)
admin_router.include_router(users_router)
admin_router.include_router(stable_router)
admin_router.include_router(sources_router)

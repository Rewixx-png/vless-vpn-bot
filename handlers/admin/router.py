from aiogram import Router

# Импортируем роутеры из модулей
from handlers.admin.menu import router as menu_router
from handlers.admin.stats import router as stats_router
from handlers.admin.broadcast import router as broadcast_router
from handlers.admin.settings import router as settings_router

# Импортируем роутер инвентаря из пакета (handlers/admin/inventory/__init__.py)
from handlers.admin.inventory import router as inventory_router

admin_router = Router()

# Подключаем все дочерние роутеры к главному админскому роутеру
admin_router.include_router(menu_router)
admin_router.include_router(stats_router)
admin_router.include_router(inventory_router)
admin_router.include_router(broadcast_router)
admin_router.include_router(settings_router)
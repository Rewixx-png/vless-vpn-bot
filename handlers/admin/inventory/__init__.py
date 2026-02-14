from aiogram import Router

# 1. Инициализируем роутер пакета
router = Router()

# 2. Импортируем подмодули
from handlers.admin.inventory.menu import router as menu_router
from handlers.admin.inventory.view import router as view_router
from handlers.admin.inventory.add import router as add_router
from handlers.admin.inventory.fix import router as fix_router
from handlers.admin.inventory.delete import router as delete_router

# 3. Подключаем их
router.include_router(menu_router)
router.include_router(view_router)
router.include_router(add_router)
router.include_router(fix_router)
router.include_router(delete_router)
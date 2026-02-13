from aiogram import Router
from handlers.user import start, apps, subscription, payment, stats, groups

user_router = Router()

user_router.include_router(start.router)
user_router.include_router(apps.router)
user_router.include_router(subscription.router)
user_router.include_router(groups.router)
user_router.include_router(payment.router)
user_router.include_router(stats.router)
from aiogram import Router
from handlers.user import start, subscription, payment, stats, groups, donate

user_router = Router()

user_router.include_router(start.router)
user_router.include_router(subscription.router)
user_router.include_router(groups.router)
user_router.include_router(payment.router)
user_router.include_router(stats.router)
user_router.include_router(donate.router)

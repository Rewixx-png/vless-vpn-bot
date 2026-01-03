import base64
import logging
from aiohttp import web
from database.repo import SubRepo, UserRepo
from config import config

logger = logging.getLogger(__name__)

class SubscriptionServer:
    @staticmethod
    async def handle_subscription(request):
        """
        Обработчик запроса /sub?id=123
        Формирует подписку с учетом фильтров пользователя и лимитов.
        """
        try:
            user_id_str = request.query.get('id')

            keys = []

            if user_id_str and user_id_str.isdigit():
                user_id = int(user_id_str)
                # Получаем объект юзера, чтобы знать лимиты и фильтры
                user = await UserRepo.get_user(user_id)

                if user:
                    user_filter = user.country_filter.split(",") if user.country_filter else None
                    user_limit = user.subscription_limit # 0 по дефолту
                    
                    # Умная выборка: Фильтр + Лимит + Сортировка по скорости
                    keys = await SubRepo.get_smart_keys(regions=user_filter, limit=user_limit)
                else:
                    # Юзер не найден в БД, отдаем дефолт (все активные)
                    keys = await SubRepo.get_smart_keys(regions=None, limit=0)
            else:
                # Без ID отдаем всё
                keys = await SubRepo.get_smart_keys(regions=None, limit=0)

            if not keys:
                return web.Response(text="")

            # Кодируем в Base64
            text_data = "\n".join(keys)
            b64_data = base64.b64encode(text_data.encode('utf-8')).decode('utf-8')

            return web.Response(text=b64_data)

        except Exception as e:
            logger.error(f"❌ CRITICAL ERROR in Subscription Server: {e}", exc_info=True)
            return web.Response(status=500, text=f"Internal Server Error")

    @staticmethod
    async def start():
        """Запуск веб-сервера"""
        app = web.Application()

        # Маршрут: http://IP:PORT/sub
        app.add_routes([web.get('/sub', SubscriptionServer.handle_subscription)])

        runner = web.AppRunner(app)
        await runner.setup()

        site = web.TCPSite(runner, '0.0.0.0', config.WEB_PORT)
        await site.start()

        logger.info(f"🌍 Subscription server started on port {config.WEB_PORT}")
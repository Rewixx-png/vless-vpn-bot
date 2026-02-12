import base64
import logging
import aiohttp_cors
from aiohttp import web
from database.repo import SubRepo, UserRepo
from config import config
from utils.parser import LinkParser
from utils.clash import ClashGenerator

# Настройка логгера
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("SubServer")

class SubscriptionServer:
    @staticmethod
    async def handle_subscription(request):
        """
        Обработчик запроса /sub?id=123
        """
        client_ip = request.remote
        method = request.method
        path = request.path
        query = request.query_string
        user_agent = request.headers.get('User-Agent', 'Unknown')

        logger.info(f"📥 REQUEST: {method} {path}?{query} | IP: {client_ip} | UA: {user_agent}")

        try:
            user_id_str = request.query.get('id')
            
            # Проверяем, является ли клиент Clash/FlClash/Meta
            is_clash = any(x in user_agent.lower() for x in ['clash', 'flclash', 'stash', 'meta', 'verge'])
            if is_clash:
                logger.info("🤖 Client detected as Clash/FlClash variant.")

            keys = []
            if user_id_str and user_id_str.isdigit():
                user_id = int(user_id_str)
                user = await UserRepo.get_user(user_id)
                if user:
                    user_filter = user.country_filter.split(",") if user.country_filter else None
                    user_limit = user.subscription_limit 
                    keys = await SubRepo.get_smart_keys(regions=user_filter, limit=user_limit)
                    logger.info(f"👤 User {user_id} found. Limits: {user_limit}, Filter: {user_filter}")
                else:
                    logger.warning(f"⚠️ User {user_id} not found in DB. Returning default keys.")
                    keys = await SubRepo.get_smart_keys(regions=None, limit=0)
            else:
                logger.info("👤 No ID provided (or invalid). Returning public keys.")
                keys = await SubRepo.get_smart_keys(regions=None, limit=0)

            logger.info(f"🔑 Keys retrieved: {len(keys)}")

            if not keys:
                logger.warning("❌ No keys available in database.")
                return web.Response(text="", status=200)

            # Генерация ответа
            if is_clash:
                logger.info("⚙️ Generating YAML config...")
                parsed_configs = []
                for k in keys:
                    cfg = LinkParser.parse_vless(k)
                    if cfg:
                        parsed_configs.append(cfg)
                    else:
                        logger.warning(f"⚠️ Failed to parse key for Clash: {k[:20]}...")
                
                response_text = ClashGenerator.generate_conf(parsed_configs)
                filename = "config.yaml"
                content_type = "text/yaml; charset=utf-8"
                logger.info(f"✅ YAML generated. Size: {len(response_text)} bytes")
            else:
                logger.info("⚙️ Generating Base64 config...")
                text_data = "\n".join(keys)
                response_text = base64.b64encode(text_data.encode('utf-8')).decode('utf-8')
                filename = "config.txt"
                content_type = "text/plain; charset=utf-8"
                logger.info(f"✅ Base64 generated. Size: {len(response_text)} bytes")

            headers = {
                "Content-Type": content_type,
                "Content-Disposition": f'attachment; filename="{filename}"',
                "Profile-Update-Interval": "3600",
                "Subscription-Userinfo": "upload=0; download=0; total=10737418240000000; expire=0",
                "Cache-Control": "no-store"
            }

            return web.Response(text=response_text, headers=headers)

        except Exception as e:
            logger.error(f"❌ CRITICAL ERROR in Subscription Server: {e}", exc_info=True)
            return web.Response(status=500, text=f"Internal Server Error: {e}")

    @staticmethod
    async def start():
        """Запуск веб-сервера"""
        app = web.Application()

        # Настройка CORS
        cors = aiohttp_cors.setup(app, defaults={
            "*": aiohttp_cors.ResourceOptions(
                allow_credentials=True,
                expose_headers="*",
                allow_headers="*",
            )
        })

        resource = app.router.add_resource("/sub")
        cors.add(resource.add_route("GET", SubscriptionServer.handle_subscription))
        
        # Добавляем корневой маршрут для проверки доступности
        async def root_handler(request):
            return web.Response(text="VLESS Bot Online")
            
        app.router.add_get('/', root_handler)

        runner = web.AppRunner(app)
        await runner.setup()

        site = web.TCPSite(runner, '0.0.0.0', config.WEB_PORT)
        
        logger.info("="*40)
        logger.info(f"🌍 SUBSCRIPTION SERVER STARTED")
        logger.info(f"👉 PORT: {config.WEB_PORT}")
        logger.info(f"👉 TEST URL: http://{config.PUBLIC_IP}:{config.WEB_PORT}/sub")
        logger.info("="*40)
        
        await site.start()
import base64
import logging
import urllib.parse
import aiohttp_cors
from aiohttp import web
from database.repo import SubRepo, UserRepo
from config import config
from utils.parser import LinkParser
from utils.clash import ClashGenerator

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("SubServer")

class SubscriptionServer:
    @staticmethod
    def _rename_vless(link: str, new_name: str) -> str:
        if "#" in link:
            base, _ = link.split("#", 1)
            return f"{base}#{urllib.parse.quote(new_name)}"
        return f"{link}#{urllib.parse.quote(new_name)}"

    @staticmethod
    def _is_whitelist_config(link: str) -> bool:
        return "security=reality" in link or "flow=xtls-rprx-vision" in link

    @staticmethod
    async def handle_subscription(request):
        client_ip = request.remote
        user_agent = request.headers.get('User-Agent', 'Unknown')
        
        try:
            user_id_str = request.query.get('id')
            is_clash = any(x in user_agent.lower() for x in ['clash', 'flclash', 'stash', 'meta', 'verge'])

            subs = []
            if user_id_str and user_id_str.isdigit():
                user = await UserRepo.get_user(int(user_id_str))
                if user:
                    user_filter = user.country_filter.split(",") if user.country_filter else None
                    # Получаем теги пользователя
                    user_tags = user.tags_filter.split(",") if user.tags_filter else None
                    
                    subs = await SubRepo.get_smart_keys(
                        regions=user_filter, 
                        tags=user_tags,
                        limit=user.subscription_limit
                    )
                else:
                    subs = await SubRepo.get_smart_keys(regions=None, limit=0)
            else:
                subs = await SubRepo.get_smart_keys(regions=None, limit=0)

            if not subs:
                return web.Response(text="", status=200)

            renamed_links = []
            region_counters = {}

            for sub in subs:
                region_name = sub.region if sub.region else "Unknown"
                if region_name not in region_counters: region_counters[region_name] = 1
                else: region_counters[region_name] += 1
                count = region_counters[region_name]
                
                # Имя уже короткое из базы (🇩🇪 DE)
                final_name = f"➤ {region_name} {count}"
                
                # Тег [Fast] если пинг < 100
                if sub.latency_ms < 100:
                    final_name += " [Fast]"
                
                if sub.ai_available:
                    final_name += " [AI]"
                
                if SubscriptionServer._is_whitelist_config(sub.vless_key):
                    final_name += " [WL]"

                new_link = SubscriptionServer._rename_vless(sub.vless_key, final_name)
                renamed_links.append(new_link)

            if is_clash:
                parsed_configs = []
                for k in renamed_links:
                    cfg = LinkParser.parse_vless(k)
                    if cfg: parsed_configs.append(cfg)
                
                response_text = ClashGenerator.generate_conf(parsed_configs)
                filename = "config.yaml"
                content_type = "text/yaml; charset=utf-8"
            else:
                text_data = "\n".join(renamed_links)
                response_text = base64.b64encode(text_data.encode('utf-8')).decode('utf-8')
                filename = "config.txt"
                content_type = "text/plain; charset=utf-8"

            headers = {
                "Content-Type": content_type,
                "Content-Disposition": f'attachment; filename="{filename}"',
                "Profile-Update-Interval": "3600",
                "Subscription-Userinfo": "upload=0; download=0; total=10737418240000000; expire=0",
                "Cache-Control": "no-store"
            }
            return web.Response(text=response_text, headers=headers)

        except Exception as e:
            logger.error(f"❌ CRITICAL ERROR: {e}", exc_info=True)
            return web.Response(status=500, text=f"Error: {e}")

    @staticmethod
    async def start():
        app = web.Application()
        cors = aiohttp_cors.setup(app, defaults={"*": aiohttp_cors.ResourceOptions(allow_credentials=True, expose_headers="*", allow_headers="*")})
        cors.add(app.router.add_get("/sub", SubscriptionServer.handle_subscription))
        app.router.add_get('/', lambda r: web.Response(text="VLESS Bot Online"))
        
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, '0.0.0.0', config.WEB_PORT)
        await site.start()
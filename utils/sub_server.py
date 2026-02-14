import base64
import logging
import urllib.parse
import aiohttp_cors
from aiohttp import web
from database.repo import SubRepo, UserRepo, SystemRepo, GroupRepo
from config import config
from utils.parser import LinkParser
from utils.clash import ClashGenerator

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
        user_agent = request.headers.get('User-Agent', 'Unknown').lower()

        try:
            user_id_raw = request.query.get('id')
            format_param = request.query.get('format', '').lower()
            # Check for different client types
            is_clash = any(x in user_agent for x in ['clash', 'flclash', 'stash', 'meta', 'verge'])
            is_v2raytun = 'v2raytun' in user_agent or 'v2ray' in user_agent or format_param == 'v2raytun'

            subs = []
            
            if user_id_raw:
                user_id = 0
                group_name = None
                
                if "/" in user_id_raw:
                    try:
                        uid_str, g_name = user_id_raw.split("/", 1)
                        user_id = int(uid_str)
                        group_name = urllib.parse.unquote(g_name)
                    except ValueError:
                        pass
                elif user_id_raw.isdigit():
                    user_id = int(user_id_raw)

                user = await UserRepo.get_user(user_id)
                if user:
                    countries_filter = None
                    tags_filter = None
                    
                    if group_name:
                        group = await GroupRepo.get_group_by_name(user_id, group_name)
                        if group:
                            if group.country_filter:
                                if group.country_filter == "__EMPTY__":
                                    # Если группа пустая, ставим фильтр, который ничего не найдет
                                    countries_filter = ["__NONE__"]
                                else:
                                    countries_filter = group.country_filter.split(",")
                            
                            if group.tags_filter:
                                tags_filter = group.tags_filter.split(",")
                    else:
                        if user.country_filter:
                            countries_filter = user.country_filter.split(",")
                        
                        if user.tags_filter:
                            tags_filter = user.tags_filter.split(",")

                    subs = await SubRepo.get_smart_keys(
                        regions=countries_filter, 
                        tags=tags_filter,
                        limit=user.subscription_limit
                    )
                else:
                    subs = await SubRepo.get_smart_keys(regions=None, limit=10)
            else:
                subs = await SubRepo.get_smart_keys(regions=None, limit=10)

            if not subs:
                return web.Response(text="", status=200)

            renamed_links = []
            region_counters = {}

            for sub in subs:
                region_name = sub.region if sub.region else "Unknown"
                if region_name not in region_counters: region_counters[region_name] = 1
                else: region_counters[region_name] += 1
                count = region_counters[region_name]
                
                final_name = f"➤ {region_name} {count}"
                
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
            elif is_v2raytun:
                # V2RayTun expects plain text list of VLESS links (one per line)
                response_text = "\n".join(renamed_links)
                filename = "sub.txt"
                content_type = "text/plain; charset=utf-8"
            else:
                # Standard base64 encoded subscription for most v2ray clients
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
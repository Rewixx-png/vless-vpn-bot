import base64
import logging
import time
import urllib.parse
from typing import Optional

import aiohttp
import aiohttp_cors
from aiohttp import web
from database.repo import SubRepo, UserRepo, SystemRepo, GroupRepo
from config import config
from utils.parser import LinkParser
from utils.clash import ClashGenerator

logger = logging.getLogger("SubServer")

class SubscriptionServer:
    _external_cache = {"ts": 0.0, "links": []}
    @staticmethod
    def _format_name(region_name: str, count: int, latency_ms: Optional[int], ai_available: bool, whitelist: bool) -> str:
        parts = [region_name, f"{count:02d}"]

        if latency_ms is not None and latency_ms > 0:
            parts.append(f"{latency_ms}ms")

        tags = []
        if latency_ms is not None and latency_ms < 100:
            tags.append("Fast")
        if ai_available:
            tags.append("AI")
        if whitelist:
            tags.append("WL")

        if tags:
            parts.append("|".join(tags))

        return " • ".join(parts)
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
    def _extract_links(text: str, allowed_schemes: set[str]) -> list[str]:
        links = []
        if not text:
            return links

        for line in text.splitlines():
            item = line.strip()
            if not item:
                continue
            if "://" not in item:
                continue

            scheme = item.split("://", 1)[0].lower()
            if scheme in allowed_schemes:
                links.append(item)
        return links

    @staticmethod
    def _decode_subscription_text(raw_text: str) -> str:
        if not raw_text:
            return ""
        if "://" in raw_text:
            return raw_text

        try:
            decoded = base64.b64decode(raw_text.strip() + "===", validate=False)
            text = decoded.decode("utf-8", errors="ignore")
            if "://" in text:
                return text
        except Exception:
            return ""

        return ""

    @classmethod
    async def _get_external_links(cls, allowed_schemes: set[str]) -> list[str]:
        now = time.time()
        if now - cls._external_cache["ts"] < 300:
            return [k for k in cls._external_cache["links"] if k.split("://", 1)[0].lower() in allowed_schemes]

        external_url = await SystemRepo.get_config("external_sub_url")
        if not external_url:
            external_url = getattr(config, "EXTERNAL_SUB_URL", None)

        if not external_url:
            return []

        try:
            timeout = aiohttp.ClientTimeout(total=8)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(external_url) as resp:
                    if resp.status != 200:
                        return []
                    raw_text = await resp.text()

            text = cls._decode_subscription_text(raw_text)
            links = cls._extract_links(text, allowed_schemes)

            cls._external_cache = {"ts": now, "links": links}
            return links
        except Exception as e:
            logger.warning(f"External subscription fetch failed: {e}")
            return []

    @staticmethod
    async def handle_subscription(request):
        client_ip = request.remote
        user_agent = request.headers.get('User-Agent', 'Unknown').lower()

        try:
            user_id_raw = request.query.get('id')
            format_param = request.query.get('format', '').lower()
            types_param = request.query.get('types', '').lower()
            # Check for different client types
            is_clash = any(x in user_agent for x in ['clash', 'flclash', 'stash', 'meta', 'verge'])
            is_v2raytun = 'v2raytun' in user_agent

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
                region_name = sub.region if sub.region else "🌍 UNK"
                if region_name not in region_counters: region_counters[region_name] = 1
                else: region_counters[region_name] += 1
                count = region_counters[region_name]

                is_wl = SubscriptionServer._is_whitelist_config(sub.vless_key)
                final_name = SubscriptionServer._format_name(
                    region_name=region_name,
                    count=count,
                    latency_ms=sub.latency_ms,
                    ai_available=sub.ai_available,
                    whitelist=is_wl
                )

                base_link = (sub.vless_key or "").strip()
                new_link = SubscriptionServer._rename_vless(base_link, final_name)
                renamed_links.append(new_link)

            renamed_links = [k for k in renamed_links if k.startswith("vless://")]

            supported_schemes = {"vless", "vmess", "trojan", "ss", "ssr", "hysteria2", "hy2", "tuic"}
            if types_param:
                if types_param == "all":
                    allowed_schemes = supported_schemes
                else:
                    allowed_schemes = {t.strip() for t in types_param.split(",") if t.strip() in supported_schemes}
            else:
                allowed_schemes = {"vless"}

            if not allowed_schemes:
                allowed_schemes = {"vless"}

            renamed_links = [k for k in renamed_links if k.split("://", 1)[0].lower() in allowed_schemes]

            external_links = await SubscriptionServer._get_external_links(allowed_schemes)
            combined_links = renamed_links + external_links

            if format_param in ["clash", "yaml", "clash-meta"] or is_clash:
                parsed_configs = []
                for k in combined_links:
                    cfg = LinkParser.parse_vless(k)
                    if cfg: parsed_configs.append(cfg)

                response_text = ClashGenerator.generate_conf(parsed_configs)
                filename = "config.yaml"
                content_type = "text/yaml; charset=utf-8"
            elif format_param in ["raw", "plain", "v2raytun"] or is_v2raytun:
                response_text = "\n".join(combined_links)
                filename = "sub.txt"
                content_type = "text/plain; charset=utf-8"
            elif format_param in ["base64", "b64"]:
                text_data = "\n".join(combined_links)
                response_text = base64.b64encode(text_data.encode('utf-8')).decode('utf-8')
                filename = "config.txt"
                content_type = "text/plain; charset=utf-8"
            else:
                text_data = "\n".join(combined_links)
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

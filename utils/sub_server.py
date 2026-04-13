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

_sub_cache = {"ts": 0.0, "data": None, "params_hash": ""}
_SUB_CACHE_TTL = 60


class SubscriptionServer:
    _external_cache = {"ts": 0.0, "links": []}

    _REGION_RU_MAP = {
        "de": "Германия",
        "germany": "Германия",
        "deutschland": "Германия",
        "nl": "Нидерланды",
        "netherlands": "Нидерланды",
        "the netherlands": "Нидерланды",
        "us": "США",
        "usa": "США",
        "united states": "США",
        "america": "США",
        "gb": "Великобритания",
        "uk": "Великобритания",
        "united kingdom": "Великобритания",
        "great britain": "Великобритания",
        "ru": "Россия",
        "russia": "Россия",
        "fr": "Франция",
        "france": "Франция",
        "tr": "Турция",
        "turkey": "Турция",
        "türkiye": "Турция",
        "cy": "Кипр",
        "cyprus": "Кипр",
        "md": "Молдова",
        "moldova": "Молдова",
        "republic of moldova": "Молдова",
        "pl": "Польша",
        "poland": "Польша",
        "it": "Италия",
        "italy": "Италия",
        "es": "Испания",
        "spain": "Испания",
        "fi": "Финляндия",
        "finland": "Финляндия",
        "ee": "Эстония",
        "estonia": "Эстония",
        "lv": "Латвия",
        "latvia": "Латвия",
        "lt": "Литва",
        "lithuania": "Литва",
        "ae": "ОАЭ",
        "uae": "ОАЭ",
        "united arab emirates": "ОАЭ",
        "sg": "Сингапур",
        "singapore": "Сингапур",
        "jp": "Япония",
        "japan": "Япония",
        "ca": "Канада",
        "canada": "Канада",
        "at": "Австрия",
        "austria": "Австрия",
        "ch": "Швейцария",
        "switzerland": "Швейцария",
        "kz": "Казахстан",
        "kazakhstan": "Казахстан",
        "ua": "Украина",
        "ukraine": "Украина",
        "unk": "Неизвестно",
        "unknown": "Неизвестно",
    }

    @classmethod
    def _format_region_ru(cls, region_name: str) -> str:
        raw = (region_name or "").strip()
        if not raw:
            return "🌍 Неизвестно"

        flag = "🌍"
        country_part = raw

        parts = raw.split(" ", 1)
        if len(parts) == 2 and any(ord(ch) > 127 for ch in parts[0]):
            flag = parts[0]
            country_part = parts[1].strip()

        country_key = country_part.lower().strip()
        display_country = cls._REGION_RU_MAP.get(country_key, country_part)
        if not display_country:
            display_country = "Неизвестно"

        return f"{flag} {display_country}".strip()

    @staticmethod
    def _format_name(
        region_name: str,
        count: int,
        speed_mbps: float,
        latency_ms: int,
        ai_available: bool,
        whitelist: bool,
        no_ads: bool,
    ) -> str:
        region_display = SubscriptionServer._format_region_ru(region_name)

        tags = []
        if ai_available:
            tags.append("AI")
        if whitelist:
            tags.append("WL")
        if no_ads:
            tags.append("NoAds")

        tags_text = ", ".join(tags) if tags else "BASE"
        safe_speed = float(speed_mbps or 0.0)

        if safe_speed <= 1.05:
            try:
                lat = int(latency_ms or 0)
            except Exception:
                lat = 0

            if lat > 0:
                estimated = 3200.0 / max(35, lat)
                safe_speed = max(1.0, min(250.0, estimated))

        speed_text = f"{max(safe_speed, 0.0):.0f} Mbps"
        safe_count = max(count, 1)

        return f"{region_display} {safe_count} | {tags_text} | {speed_text}"

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

    @staticmethod
    def _resolve_effective_limit(user_limit: int | None, user_agent: str) -> int:
        _ = user_agent
        try:
            parsed_limit = int(user_limit or 0)
        except Exception:
            parsed_limit = 0

        if parsed_limit > 0:
            return max(1, min(parsed_limit, 5000))

        return 0

    @classmethod
    async def _get_external_links(cls, allowed_schemes: set[str]) -> list[str]:
        now = time.time()
        if now - cls._external_cache["ts"] < 300:
            return [
                k
                for k in cls._external_cache["links"]
                if k.split("://", 1)[0].lower() in allowed_schemes
            ]

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
        user_agent = request.headers.get("User-Agent", "Unknown").lower()

        try:
            user_id_raw = request.query.get("id")
            format_param = request.query.get("format", "").lower()
            if request.path.lower().endswith("/sub64"):
                format_param = "base64"
            types_param = request.query.get("types", "").lower()
            auto_clean_param = request.query.get("auto_clean", "").lower() == "true"

            is_clash = any(
                x in user_agent for x in ["clash", "flclash", "stash", "meta", "verge"]
            )
            is_hiddify = "hiddify" in user_agent
            is_v2raytun = "v2raytun" in user_agent
            is_happ = "happ" in user_agent.lower()

            subs = []
            use_fragment = False
            user = None
            fallback_used = False
            effective_limit = 0

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
                    use_fragment = user.use_fragment
                    effective_limit = SubscriptionServer._resolve_effective_limit(
                        user.subscription_limit,
                        user_agent,
                    )
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
                        limit=effective_limit,
                        auto_clean=auto_clean_param,
                    )
                else:
                    effective_limit = 0
                    subs = await SubRepo.get_smart_keys(
                        regions=None, limit=effective_limit, auto_clean=auto_clean_param
                    )
            else:
                effective_limit = 0
                subs = await SubRepo.get_smart_keys(
                    regions=None, limit=effective_limit, auto_clean=auto_clean_param
                )

            if not subs and user_id_raw:
                fallback_limit = effective_limit if effective_limit > 0 else 0

                subs = await SubRepo.get_smart_keys(
                    regions=None,
                    tags=None,
                    limit=fallback_limit,
                    auto_clean=False,
                )
                if subs:
                    fallback_used = True
                    logger.info(
                        "Subscription fallback used for user_id=%s ip=%s ua=%s",
                        user_id_raw,
                        client_ip,
                        user_agent[:120],
                    )

            renamed_links = []
            region_counters = {}

            for sub in subs:
                region_name = sub.region if sub.region else "🌍 UNK"
                if region_name not in region_counters:
                    region_counters[region_name] = 1
                else:
                    region_counters[region_name] += 1
                count = region_counters[region_name]

                is_wl = SubscriptionServer._is_whitelist_config(sub.vless_key)
                final_name = SubscriptionServer._format_name(
                    region_name=region_name,
                    count=count,
                    speed_mbps=sub.speed_mbps,
                    latency_ms=sub.latency_ms,
                    ai_available=sub.ai_available,
                    whitelist=is_wl,
                    no_ads=sub.no_ads,
                )

                base_link = (sub.vless_key or "").strip()

                if use_fragment:
                    if "security=tls" in base_link or "security=reality" in base_link:
                        if "fragment=" not in base_link:
                            base_link = LinkParser.update_param(
                                base_link, "fragment", "10-30,10-30,tlshello"
                            )

                new_link = SubscriptionServer._rename_vless(base_link, final_name)
                renamed_links.append(new_link)

            renamed_links = [k for k in renamed_links if k.startswith("vless://")]

            supported_schemes = {
                "vless",
                "vmess",
                "trojan",
                "ss",
                "ssr",
                "hysteria2",
                "hy2",
                "tuic",
            }
            if types_param:
                if types_param == "all":
                    allowed_schemes = supported_schemes
                else:
                    allowed_schemes = {
                        t.strip()
                        for t in types_param.split(",")
                        if t.strip() in supported_schemes
                    }
            else:
                allowed_schemes = {"vless"}

            if not allowed_schemes:
                allowed_schemes = {"vless"}

            renamed_links = [
                k
                for k in renamed_links
                if k.split("://", 1)[0].lower() in allowed_schemes
            ]

            external_links = await SubscriptionServer._get_external_links(
                allowed_schemes
            )
            combined_links = renamed_links + external_links

            if not combined_links and not (
                format_param in ["clash", "yaml", "yml"] or is_clash
            ):
                combined_links = ["# no-active-configs"]

            if format_param in ["hiddify", "hdy"] or is_hiddify or is_happ:
                text_data = "\n".join(combined_links)
                response_text = base64.b64encode(text_data.encode("utf-8")).decode(
                    "utf-8"
                )
                filename = "hiddify.txt"
                content_type = "text/plain; charset=utf-8"
            elif format_param in ["clash", "yaml", "yml"] or is_clash:
                parsed_configs = []
                for k in combined_links:
                    cfg = LinkParser.parse_vless(k)
                    if cfg:
                        parsed_configs.append(cfg)

                response_text = ClashGenerator.generate_conf(parsed_configs)
                filename = "config.yaml"
                content_type = "application/x-yaml; charset=utf-8"
            elif format_param in ["raw", "plain", "txt"] or is_v2raytun:
                response_text = "\n".join(combined_links)
                filename = "sub.txt"
                content_type = "text/plain; charset=utf-8"
            elif format_param in ["base64", "b64"]:
                text_data = "\n".join(combined_links)
                response_text = base64.b64encode(text_data.encode("utf-8")).decode(
                    "utf-8"
                )
                filename = "config.txt"
                content_type = "text/plain; charset=utf-8"
            else:
                response_text = "\n".join(combined_links)
                filename = "sub.txt"
                content_type = "text/plain; charset=utf-8"

            headers = {
                "Content-Type": content_type,
                "Content-Disposition": f'attachment; filename="{filename}"',
                "Profile-Update-Interval": "3600",
                "Subscription-Userinfo": "upload=0; download=0; total=10737418240000000; expire=0",
                "Cache-Control": "no-store",
                "X-Subscription-Items": str(len(combined_links)),
                "X-Subscription-Fallback": "1" if fallback_used else "0",
                "X-Subscription-Limit": str(effective_limit),
            }
            return web.Response(text=response_text, headers=headers)

        except Exception as e:
            logger.error(f"❌ CRITICAL ERROR: {e}", exc_info=True)
            return web.Response(status=500, text=f"Error: {e}")

    @staticmethod
    async def start():
        app = web.Application()
        cors = aiohttp_cors.setup(
            app,
            defaults={
                "*": aiohttp_cors.ResourceOptions(
                    allow_credentials=True, expose_headers="*", allow_headers="*"
                )
            },
        )
        cors.add(app.router.add_get("/sub", SubscriptionServer.handle_subscription))
        cors.add(app.router.add_get("/sub64", SubscriptionServer.handle_subscription))
        app.router.add_get("/", lambda r: web.Response(text="VLESS Bot Online"))

        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "0.0.0.0", config.WEB_PORT)
        await site.start()

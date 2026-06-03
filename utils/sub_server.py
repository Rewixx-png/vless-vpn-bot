import asyncio
import base64
import hmac
import logging
import shlex
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
from utils.singbox import SingBoxGenerator
from utils.protocols import (
    ACTIVE_SCHEMES,
    BOTH_PROTOCOL_FILTER_VALUE,
    RENAMED_FRAGMENT_SCHEMES,
    SUPPORTED_SCHEMES,
)

logger = logging.getLogger("SubServer")

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

    @staticmethod
    def _ru_checker_expected_token() -> str:
        return str(config.RU_CHECKER_TOKEN or "").strip()

    @classmethod
    def _ru_checker_authorized(cls, request: web.Request) -> bool:
        expected = cls._ru_checker_expected_token()
        if not expected:
            return False

        supplied = str(request.query.get("token") or "").strip()
        auth_header = str(request.headers.get("Authorization") or "").strip()
        if auth_header.lower().startswith("bearer "):
            supplied = auth_header[7:].strip()
        return bool(supplied) and hmac.compare_digest(supplied, expected)

    @classmethod
    def _ru_checker_base_url(cls, request: web.Request) -> str:
        scheme = request.headers.get("X-Forwarded-Proto") or request.scheme
        host = request.headers.get("X-Forwarded-Host") or request.host
        return f"{scheme}://{host}".rstrip("/")

    @classmethod
    def _ru_checker_disabled_response(cls) -> web.Response:
        return web.json_response(
            {"ok": False, "error": "RU_CHECKER_TOKEN is not configured"},
            status=503,
        )

    @classmethod
    def _ru_checker_auth_response(cls) -> web.Response:
        if not cls._ru_checker_expected_token():
            return cls._ru_checker_disabled_response()
        return web.json_response({"ok": False, "error": "unauthorized"}, status=401)

    @staticmethod
    def _termux_worker_code() -> str:
        return r'''#!/usr/bin/env python3
import asyncio
import json
import os
import platform
import socket
import time
import urllib.error
import urllib.parse
import urllib.request


SERVER = os.environ.get("RU_CHECKER_SERVER", "").rstrip("/")
TOKEN = os.environ.get("RU_CHECKER_TOKEN", "")
BATCH_SIZE = int(os.environ.get("RU_CHECKER_BATCH_SIZE", "30") or "30")
TIMEOUT = float(os.environ.get("RU_CHECKER_CONNECT_TIMEOUT", "6.0") or "6.0")
CONCURRENCY = max(1, int(os.environ.get("RU_CHECKER_CONCURRENCY", "10") or "10"))
WORKER_ID = os.environ.get("RU_CHECKER_WORKER_ID") or f"termux-{platform.node() or 'android'}"


def request_json(path, payload=None, method="GET"):
    if not SERVER or not TOKEN:
        raise RuntimeError("RU_CHECKER_SERVER or RU_CHECKER_TOKEN is empty")
    url = f"{SERVER}{path}"
    data = None
    headers = {"Authorization": f"Bearer {TOKEN}", "User-Agent": f"ru-termux-worker/{WORKER_ID}"}
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=30) as resp:
        body = resp.read().decode("utf-8", errors="replace")
    return json.loads(body or "{}")


def log_to_server(message, level="info"):
    try:
        request_json("/ru-check/worker-log", {"worker_id": WORKER_ID, "level": level, "message": str(message)[-4000:]}, method="POST")
    except Exception:
        pass


def parse_endpoint(url):
    parsed = urllib.parse.urlsplit(url.strip())
    scheme = (parsed.scheme or "").lower()
    if scheme not in {"vless", "trojan"}:
        return scheme, None, None
    return scheme, parsed.hostname, parsed.port


async def check_item(item, semaphore):
    sub_id = int(item.get("id") or 0)
    url = str(item.get("url") or "")
    scheme, host, port = parse_endpoint(url)
    if not host or not port:
        return {"id": sub_id, "status": "unsupported", "latency_ms": None, "error": f"unsupported_or_invalid:{scheme}"}
    async with semaphore:
        started = time.perf_counter()
        try:
            reader, writer = await asyncio.wait_for(asyncio.open_connection(host, port), timeout=TIMEOUT)
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass
            latency = int((time.perf_counter() - started) * 1000)
            return {"id": sub_id, "status": "tcp_alive", "latency_ms": latency, "error": None}
        except (asyncio.TimeoutError, socket.timeout):
            return {"id": sub_id, "status": "timeout", "latency_ms": None, "error": f"connect_timeout:{TIMEOUT}s"}
        except Exception as exc:
            return {"id": sub_id, "status": "error", "latency_ms": None, "error": str(exc)[:300]}


async def run_once():
    batch = request_json(f"/ru-check/batch?limit={BATCH_SIZE}")
    items = list(batch.get("items") or [])
    if not items:
        log_to_server("batch empty")
        return 0
    semaphore = asyncio.Semaphore(CONCURRENCY)
    results = await asyncio.gather(*(check_item(item, semaphore) for item in items))
    report = {"worker_id": WORKER_ID, "results": results}
    response = request_json("/ru-check/report", report, method="POST")
    log_to_server(f"checked={len(results)} updated={response.get('updated')}")
    return len(results)


def main():
    try:
        count = asyncio.run(run_once())
        print(json.dumps({"ok": True, "checked": count}, ensure_ascii=False))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        log_to_server(f"http_error={exc.code} body={body}", "error")
        raise
    except Exception as exc:
        log_to_server(f"worker_error={exc}", "error")
        raise


if __name__ == "__main__":
    main()
'''

    @classmethod
    def _termux_install_script(cls, request: web.Request) -> str:
        base_url = cls._ru_checker_base_url(request)
        token = cls._ru_checker_expected_token()
        token_url = urllib.parse.quote(token, safe="")
        return f'''#!/usr/bin/env bash
set -u

SERVER={shlex.quote(base_url)}
TOKEN={shlex.quote(token)}
TOKEN_URL={shlex.quote(token_url)}
DIR="$HOME/ru-checker"
LOG="$DIR/install.log"
mkdir -p "$DIR"
exec > >(tee -a "$LOG") 2>&1

send_log() {{
  if command -v curl >/dev/null 2>&1; then
    curl -fsS -X POST "$SERVER/ru-check/worker-log?token=$TOKEN_URL" --data-binary "@$LOG" >/dev/null 2>&1 || true
  fi
}}

trap 'send_log' EXIT

echo "ru-checker install started $(date)"
if ! command -v pkg >/dev/null 2>&1; then
  echo "Termux pkg command not found"
  exit 2
fi

pkg update -y
pkg install -y python curl

cat > "$DIR/env" <<EOF
export RU_CHECKER_SERVER=$SERVER
export RU_CHECKER_TOKEN=$TOKEN
export RU_CHECKER_BATCH_SIZE={int(config.RU_CHECKER_BATCH_SIZE)}
export RU_CHECKER_CONNECT_TIMEOUT={float(config.RU_CHECKER_CONNECT_TIMEOUT)}
export RU_CHECKER_CONCURRENCY={int(config.RU_CHECKER_CONCURRENCY)}
export RU_CHECKER_INTERVAL_SECONDS={int(config.RU_CHECKER_INTERVAL_SECONDS)}
EOF

curl -fsSL "$SERVER/ru-check/worker.py?token=$TOKEN_URL" -o "$DIR/worker.py"
chmod +x "$DIR/worker.py"

cat > "$DIR/run.sh" <<'EOF'
#!/usr/bin/env bash
set -u
DIR="$HOME/ru-checker"
set -a
. "$DIR/env"
set +a
while true; do
  python "$DIR/worker.py" >> "$DIR/worker.log" 2>&1 || true
  sleep "${{RU_CHECKER_INTERVAL_SECONDS:-120}}"
done
EOF

chmod +x "$DIR/run.sh"
if [ -f "$DIR/worker.pid" ]; then
  OLD_PID=$(cat "$DIR/worker.pid" 2>/dev/null || true)
  if [ -n "$OLD_PID" ]; then
    kill "$OLD_PID" >/dev/null 2>&1 || true
  fi
fi
nohup "$DIR/run.sh" >> "$DIR/worker.log" 2>&1 &
echo $! > "$DIR/worker.pid"
STARTED_PID=$(cat "$DIR/worker.pid")
echo "ru-checker started pid=$STARTED_PID"
echo "logs: $DIR/worker.log"
'''

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
        return (
            "security=reality" in link
            or "flow=xtls-rprx-vision" in link
            or "obfs=salamander" in link
        )

    @staticmethod
    def _extract_links(text: str, allowed_schemes: set[str] | frozenset[str]) -> list[str]:
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
    async def _get_external_links(cls, allowed_schemes: set[str] | frozenset[str]) -> list[str]:
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
            is_singbox = any(
                x in user_agent for x in ["sing-box", "singbox", "nekobox", "nekoray", "hiddify-next"]
            ) or format_param in ("singbox", "sing-box", "sb")
            is_hiddify = "hiddify" in user_agent and not is_singbox
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

                    protocol_filter = None
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

                            if group.protocol_filter:
                                protocol_filter = group.protocol_filter
                    else:
                        if user.country_filter:
                            countries_filter = user.country_filter.split(",")

                        if user.tags_filter:
                            tags_filter = user.tags_filter.split(",")

                        if user.protocol_filter:
                            protocol_filter = user.protocol_filter

                    if not types_param and protocol_filter:
                        if protocol_filter == "both":
                            types_param = BOTH_PROTOCOL_FILTER_VALUE
                        elif protocol_filter == "hy2":
                            types_param = "hy2,hysteria2,tuic"
                        else:
                            types_param = protocol_filter

                    subs = await SubRepo.get_smart_keys(
                        regions=countries_filter,
                        tags=tags_filter,
                        limit=effective_limit,
                        auto_clean=auto_clean_param,
                    )
                else:
                    return web.Response(
                        status=404,
                        text="# Not found: user not registered",
                        content_type="text/plain",
                    )
            else:
                return web.Response(
                    status=401,
                    text="# Unauthorized: subscription ID required",
                    content_type="text/plain",
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

                scheme = base_link.split("://", 1)[0].lower() if "://" in base_link else ""
                if scheme in RENAMED_FRAGMENT_SCHEMES:
                    clean_link = base_link.split("#", 1)[0]
                    renamed_links.append(f"{clean_link}#{urllib.parse.quote(final_name)}")
                else:
                    new_link = SubscriptionServer._rename_vless(base_link, final_name)
                    renamed_links.append(new_link)

            renamed_links = [
                k for k in renamed_links
                if k.split("://", 1)[0].lower() in ACTIVE_SCHEMES
            ]

            supported_schemes = SUPPORTED_SCHEMES
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
                allowed_schemes = ACTIVE_SCHEMES

            if not allowed_schemes:
                allowed_schemes = ACTIVE_SCHEMES

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

            if is_singbox:
                parsed_configs = []
                for k in combined_links:
                    scheme = k.split("://", 1)[0].lower() if "://" in k else ""
                    if scheme in ("hy2", "hysteria2"):
                        cfg = SingBoxGenerator.parse_hysteria2(k)
                    elif scheme == "trojan":
                        cfg = LinkParser.parse_trojan(k)
                    else:
                        cfg = LinkParser.parse_vless(k)
                    if cfg:
                        parsed_configs.append(cfg)

                response_text = SingBoxGenerator.generate(parsed_configs)
                filename = "config.json"
                content_type = "application/json; charset=utf-8"
            elif format_param in ["hiddify", "hdy"] or is_hiddify or is_happ:
                text_data = "\n".join(combined_links)
                response_text = base64.b64encode(text_data.encode("utf-8")).decode(
                    "utf-8"
                )
                filename = "hiddify.txt"
                content_type = "text/plain; charset=utf-8"
            elif format_param in ["clash", "yaml", "yml"] or is_clash:
                parsed_configs = []
                for k in combined_links:
                    scheme = k.split("://", 1)[0].lower() if "://" in k else ""
                    if scheme == "trojan":
                        cfg = LinkParser.parse_trojan(k)
                    else:
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
            return web.Response(status=500, text="Internal server error")

    @staticmethod
    async def handle_redirect(request: web.Request) -> web.Response:
        app_type = request.query.get("app")
        sub_url = request.query.get("url")
        
        if not app_type or not sub_url:
            return web.Response(status=400, text="Bad Request: Missing parameters")
            
        encoded_url = urllib.parse.quote(sub_url, safe="")
        schemes = {
            "hiddify": f"hiddify://install-config?url={encoded_url}",
            "v2raytun": f"v2raytun://import/{encoded_url}",
            "streisand": f"streisand://import/{encoded_url}",
            "singbox": f"sing-box://import-remote-profile?url={encoded_url}",
        }
        
        target = schemes.get(app_type.lower())
        if not target:
            return web.Response(status=400, text="Bad Request: Unsupported app")

        return web.Response(
            status=302,
            headers={"Location": target},
            text="Redirecting...",
        )

    @classmethod
    async def handle_ru_check_batch(cls, request: web.Request) -> web.Response:
        if not cls._ru_checker_authorized(request):
            return cls._ru_checker_auth_response()

        try:
            limit = int(request.query.get("limit") or config.RU_CHECKER_BATCH_SIZE)
        except Exception:
            limit = int(config.RU_CHECKER_BATCH_SIZE)

        items = await SubRepo.get_ru_check_batch(limit=limit)
        return web.json_response(
            {
                "ok": True,
                "items": items,
                "interval_seconds": int(config.RU_CHECKER_INTERVAL_SECONDS),
                "connect_timeout": float(config.RU_CHECKER_CONNECT_TIMEOUT),
                "concurrency": int(config.RU_CHECKER_CONCURRENCY),
            }
        )

    @classmethod
    async def handle_ru_check_report(cls, request: web.Request) -> web.Response:
        if not cls._ru_checker_authorized(request):
            return cls._ru_checker_auth_response()

        try:
            payload = await request.json()
        except Exception:
            return web.json_response({"ok": False, "error": "invalid json"}, status=400)

        if isinstance(payload, dict):
            results = payload.get("results") or []
            worker_id = str(payload.get("worker_id") or "unknown")[:120]
        else:
            results = []
            worker_id = "unknown"

        if not isinstance(results, list):
            return web.json_response({"ok": False, "error": "results must be list"}, status=400)

        updated = await SubRepo.apply_ru_check_results(results[:200])
        logger.info("RU checker report worker=%s results=%s updated=%s", worker_id, len(results), updated)
        return web.json_response({"ok": True, "updated": updated})

    @classmethod
    async def handle_ru_check_worker_log(cls, request: web.Request) -> web.Response:
        if not cls._ru_checker_authorized(request):
            return cls._ru_checker_auth_response()

        worker_id = "unknown"
        level = "info"
        message = ""
        try:
            if request.content_type == "application/json":
                payload = await request.json()
                if isinstance(payload, dict):
                    worker_id = str(payload.get("worker_id") or "unknown")[:120]
                    level = str(payload.get("level") or "info")[:30]
                    message = str(payload.get("message") or "")[-4000:]
            else:
                message = (await request.text())[-4000:]
        except Exception as e:
            message = f"failed to read worker log: {e}"
            level = "error"

        log_message = "RU checker worker=%s level=%s msg=%s"
        if level.lower() in {"error", "critical"}:
            logger.error(log_message, worker_id, level, message)
        else:
            logger.info(log_message, worker_id, level, message)
        return web.json_response({"ok": True})

    @classmethod
    async def handle_ru_check_worker_py(cls, request: web.Request) -> web.Response:
        if not cls._ru_checker_authorized(request):
            return cls._ru_checker_auth_response()
        return web.Response(
            text=cls._termux_worker_code(),
            headers={"Content-Type": "text/x-python; charset=utf-8"},
        )

    @classmethod
    async def handle_ru_check_install(cls, request: web.Request) -> web.Response:
        if not cls._ru_checker_authorized(request):
            return cls._ru_checker_auth_response()
        return web.Response(
            text=cls._termux_install_script(request),
            headers={"Content-Type": "text/x-shellscript; charset=utf-8"},
        )

    _runner: web.AppRunner | None = None

    @classmethod
    async def start(cls) -> None:
        app = web.Application()
        cors = aiohttp_cors.setup(
            app,
            defaults={
                "*": aiohttp_cors.ResourceOptions(
                    allow_credentials=False, expose_headers="*", allow_headers="*"
                )
            },
        )
        cors.add(app.router.add_get("/sub", SubscriptionServer.handle_subscription))
        cors.add(app.router.add_get("/sub64", SubscriptionServer.handle_subscription))
        app.router.add_get("/redirect", SubscriptionServer.handle_redirect)
        app.router.add_get("/ru-check/batch", SubscriptionServer.handle_ru_check_batch)
        app.router.add_post("/ru-check/report", SubscriptionServer.handle_ru_check_report)
        app.router.add_post("/ru-check/worker-log", SubscriptionServer.handle_ru_check_worker_log)
        app.router.add_get("/ru-check/worker.py", SubscriptionServer.handle_ru_check_worker_py)
        app.router.add_get("/ru-check/install.sh", SubscriptionServer.handle_ru_check_install)
        app.router.add_get("/", lambda r: web.Response(text="VLESS Bot Online"))

        runner = web.AppRunner(app)
        cls._runner = runner
        await runner.setup()
        site = web.TCPSite(runner, "0.0.0.0", config.WEB_PORT)
        await site.start()
        logger.info(f"Subscription server started on port {config.WEB_PORT}")
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            logger.info("Subscription server shutting down...")
        finally:
            await runner.cleanup()
            cls._runner = None

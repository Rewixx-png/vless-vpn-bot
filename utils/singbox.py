import json
import logging
import re
import urllib.parse

from utils.protocols import RU_DOMAIN_SUFFIXES as _RU_DOMAIN_SUFFIXES

logger = logging.getLogger("SingBoxGen")

class SingBoxGenerator:
    @staticmethod
    def parse_hysteria2(link: str) -> dict | None:
        try:
            scheme, rest = link.split("://", 1)
            if "#" in rest:
                rest, fragment = rest.rsplit("#", 1)
                name = urllib.parse.unquote(fragment)
            else:
                name = ""

            if "@" in rest:
                auth_part, hostport = rest.rsplit("@", 1)
            else:
                auth_part = ""
                hostport = rest

            if "?" in hostport:
                hostport, query_str = hostport.split("?", 1)
                params = dict(urllib.parse.parse_qsl(query_str))
            else:
                params = {}

            if ":" in hostport and not hostport.startswith("["):
                host, port_str = hostport.rsplit(":", 1)
            elif hostport.startswith("["):
                bracket_end = hostport.index("]")
                host = hostport[1:bracket_end]
                port_str = hostport[bracket_end + 2:] if bracket_end + 2 < len(hostport) else "443"
            else:
                return None

            return {
                "_protocol": "hysteria2",
                "server": host.strip("[]"),
                "port": int(port_str),
                "password": urllib.parse.unquote(auth_part) if auth_part else "",
                "sni": params.get("sni", ""),
                "insecure": params.get("insecure", "0") == "1",
                "obfs": params.get("obfs", ""),
                "obfs_password": params.get("obfs-password", ""),
                "name": name or f"HY2-{host}",
            }
        except Exception:
            return None

    @staticmethod
    def _is_valid_short_id(sid: str) -> bool:
        if not sid:
            return True
        return bool(re.match(r"^[0-9a-fA-F]+$", sid))

    @staticmethod
    def _unique_tag(base: str, seen: dict) -> str:
        if base not in seen:
            seen[base] = 1
            return base
        seen[base] += 1
        return f"{base} {seen[base]}"

    @staticmethod
    def generate(configs: list) -> str:
        outbounds = []
        proxy_tags: list[str] = []
        seen_tags: dict[str, int] = {}

        for cfg in configs:
            try:
                if cfg.get("_protocol") == "hysteria2":
                    name = (cfg.get("name") or f"HY2-{cfg['server']}").strip()
                    tag = SingBoxGenerator._unique_tag(name, seen_tags)
                    outbound: dict = {
                        "type": "hysteria2",
                        "tag": tag,
                        "server": cfg["server"],
                        "server_port": int(cfg["port"]),
                        "password": cfg.get("password", ""),
                        "tls": {
                            "enabled": True,
                            "server_name": cfg.get("sni") or cfg["server"],
                            "insecure": bool(cfg.get("insecure", False)),
                        },
                    }
                    if cfg.get("obfs"):
                        outbound["obfs"] = {
                            "type": cfg["obfs"],
                            "password": cfg.get("obfs_password", ""),
                        }
                    outbounds.append(outbound)
                    proxy_tags.append(tag)
                    continue

                if cfg.get("_protocol") == "trojan":
                    name = (cfg.get("name") or f"TROJAN-{cfg['server']}").strip()
                    tag = SingBoxGenerator._unique_tag(name, seen_tags)
                    outbound = {
                        "type": "trojan",
                        "tag": tag,
                        "server": cfg["server"],
                        "server_port": int(cfg["port"]),
                        "password": cfg["password"],
                    }
                    security = str(cfg.get("security", "tls") or "tls").strip().lower()
                    if security in ("tls", "xtls"):
                        outbound["tls"] = {
                            "enabled": True,
                            "server_name": cfg.get("sni") or cfg.get("host") or cfg["server"],
                            "insecure": True,
                        }
                    network = str(cfg.get("type", "tcp") or "tcp").strip().lower()
                    if network == "ws":
                        outbound["transport"] = {
                            "type": "ws",
                            "path": cfg.get("path", "/") or "/",
                            "headers": {
                                "Host": cfg.get("host") or cfg.get("sni") or cfg["server"]
                            },
                        }
                    elif network == "grpc":
                        outbound["transport"] = {
                            "type": "grpc",
                            "service_name": cfg.get("serviceName", "") or "",
                        }
                    outbounds.append(outbound)
                    proxy_tags.append(tag)
                    continue

                name = (cfg.get("name") or cfg.get("ps") or f"VLESS-{cfg['server']}").strip()
                tag = SingBoxGenerator._unique_tag(name, seen_tags)

                security = str(cfg.get("security", "none") or "none").strip().lower()
                network = str(cfg.get("type", "tcp") or "tcp").strip().lower()

                outbound = {
                    "type": "vless",
                    "tag": tag,
                    "server": cfg["server"],
                    "server_port": int(cfg["port"]),
                    "uuid": cfg["uuid"],
                    "packet_encoding": "xudp",
                }

                flow = str(cfg.get("flow", "") or "").strip().lower()
                if flow:
                    outbound["flow"] = flow

                if security in ("tls", "reality"):
                    tls_block: dict = {
                        "enabled": True,
                        "server_name": cfg.get("sni") or cfg.get("host") or cfg["server"],
                        "insecure": True,
                        "utls": {
                            "enabled": True,
                            "fingerprint": cfg.get("fp") or "chrome",
                        },
                    }
                    if security == "reality":
                        pbk = str(cfg.get("pbk", "") or "").strip()
                        sid = str(cfg.get("sid", "") or "").strip()
                        if not SingBoxGenerator._is_valid_short_id(sid):
                            logger.warning(f"Skipping {tag}: invalid short-id '{sid}'")
                            continue
                        tls_block["reality"] = {
                            "enabled": True,
                            "public_key": pbk,
                            "short_id": sid,
                        }
                    outbound["tls"] = tls_block

                if network == "ws":
                    outbound["transport"] = {
                        "type": "ws",
                        "path": cfg.get("path", "/") or "/",
                        "headers": {
                            "Host": cfg.get("host") or cfg.get("sni") or cfg["server"]
                        },
                    }
                elif network == "grpc":
                    outbound["transport"] = {
                        "type": "grpc",
                        "service_name": cfg.get("serviceName", "") or "",
                    }
                elif network == "h2":
                    outbound["transport"] = {
                        "type": "http",
                        "host": [cfg.get("host") or cfg.get("sni") or cfg["server"]],
                        "path": cfg.get("path", "/") or "/",
                    }
                elif network == "httpupgrade":
                    outbound["transport"] = {
                        "type": "httpupgrade",
                        "host": cfg.get("host") or cfg.get("sni") or cfg["server"],
                        "path": cfg.get("path", "/") or "/",
                    }
                elif network == "splithttp":
                    outbound["transport"] = {
                        "type": "splithttp",
                        "host": cfg.get("host") or cfg.get("sni") or cfg["server"],
                        "path": cfg.get("path", "/") or "/",
                    }
                elif network == "xhttp":
                    outbound["transport"] = {
                        "type": "splithttp",
                        "host": cfg.get("host") or cfg.get("sni") or cfg["server"],
                        "path": cfg.get("path", "/") or "/",
                        "method": "packet",
                    }

                outbounds.append(outbound)
                proxy_tags.append(tag)

            except Exception as e:
                logger.error(f"SingBox: error processing config: {e}")
                continue

        if not proxy_tags:
            proxy_tags = []

        outbounds_section = [
            {
                "type": "selector",
                "tag": "proxy",
                "outbounds": ["auto"] + proxy_tags,
                "default": "auto",
            },
            {
                "type": "urltest",
                "tag": "auto",
                "outbounds": proxy_tags if proxy_tags else ["direct"],
                "url": "https://www.gstatic.com/generate_204",
                "interval": "3m",
                "tolerance": 50,
            },
            *outbounds,
            {"type": "direct", "tag": "direct"},
            {"type": "block", "tag": "block"},
        ]

        ru_direct_rule = {
            "type": "logical",
            "mode": "or",
            "rules": [
                {"geoip": ["ru"]},
                {"geosite": ["category-ru"]},
                {"domain_suffix": _RU_DOMAIN_SUFFIXES},
            ],
            "outbound": "direct",
        }

        config = {
            "log": {"level": "warn", "timestamp": True},
            "dns": {
                "servers": [
                    {
                        "tag": "remote",
                        "address": "https://1.1.1.1/dns-query",
                        "strategy": "prefer_ipv4",
                    },
                    {
                        "tag": "local",
                        "address": "https://dns.google/dns-query",
                        "detour": "direct",
                        "strategy": "prefer_ipv4",
                    },
                ],
                "rules": [
                    {
                        "geosite": ["category-ru"],
                        "server": "local",
                    }
                ],
                "final": "remote",
                "independent_cache": True,
            },
            "inbounds": [
                {
                    "type": "mixed",
                    "tag": "mixed-in",
                    "listen": "127.0.0.1",
                    "listen_port": 2080,
                    "sniff": True,
                    "sniff_override_destination": True,
                }
            ],
            "outbounds": outbounds_section,
            "route": {
                "rules": [
                    {"ip_is_private": True, "outbound": "direct"},
                    {"protocol": "dns", "outbound": "block"},
                    ru_direct_rule,
                ],
                "final": "proxy",
                "auto_detect_interface": True,
            },
            "experimental": {
                "clash_api": {
                    "external_controller": "127.0.0.1:9090",
                    "secret": "",
                },
                "cache_file": {
                    "enabled": True,
                },
            },
        }

        return json.dumps(config, ensure_ascii=False, indent=2)

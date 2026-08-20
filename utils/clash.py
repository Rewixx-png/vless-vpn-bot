import logging
import re

from utils.protocols import RU_DOMAIN_SUFFIXES as _RU_DOMAIN_SUFFIXES

logger = logging.getLogger("ClashGen")

class ClashGenerator:
    @staticmethod
    def is_valid_short_id(sid: str) -> bool:
        if not sid:
            return True
        return bool(re.match(r"^[0-9a-fA-F]+$", sid))

    @staticmethod
    def _extract_speed_mbps(name: str) -> float:
        match = re.search(r"(\d+(?:\.\d+)?)\s*Mbps", name, re.IGNORECASE)
        if not match:
            return 0.0
        try:
            return float(match.group(1))
        except ValueError:
            return 0.0

    @staticmethod
    def _extract_country_label(name: str) -> str:
        left = name.split("|", 1)[0].strip()
        left = re.sub(r"\s+\d+$", "", left).strip()
        return left or "Other"

    @staticmethod
    def generate_conf(configs: list) -> str:
        proxies = []
        name_counter = {}

        for cfg in configs:
            try:
                base_name = cfg.get("name") or cfg.get("ps") or f"VLESS-{cfg['server']}"

                if base_name in name_counter:
                    name_counter[base_name] += 1
                    final_name = f"{base_name} {name_counter[base_name]}"
                else:
                    name_counter[base_name] = 1
                    final_name = base_name

                if cfg.get("_protocol") == "trojan":
                    proxy = {
                        "name": final_name,
                        "type": "trojan",
                        "server": cfg["server"],
                        "port": cfg["port"],
                        "password": cfg["password"],
                        "udp": True,
                        "skip-cert-verify": True,
                        "network": cfg.get("type", "tcp") or "tcp",
                    }
                else:
                    proxy = {
                        "name": final_name,
                        "type": "vless",
                        "server": cfg["server"],
                        "port": cfg["port"],
                        "uuid": cfg["uuid"],
                        "cipher": "auto",
                        "udp": True,
                        "tls": False,
                        "network": cfg.get("type", "tcp"),
                        "skip-cert-verify": True,
                    }

                if cfg.get("_protocol") == "trojan":
                    security = cfg.get("security", "tls")
                    if security != "none":
                        proxy["tls"] = True
                        proxy["servername"] = cfg.get("sni") or cfg.get("host") or cfg["server"]
                else:
                    if cfg.get("flow"):
                        proxy["flow"] = cfg["flow"]

                    security = cfg.get("security", "none")

                    if security in ["tls", "reality"]:
                        proxy["tls"] = True
                        proxy["servername"] = cfg.get("sni") or cfg.get("host") or cfg["server"]
                        proxy["client-fingerprint"] = cfg.get("fp", "chrome")

                        if security == "reality":
                            pbk = cfg.get("pbk", "")
                            sid = cfg.get("sid", "")

                            if not ClashGenerator.is_valid_short_id(sid):
                                logger.warning(
                                    f"Skipping config {final_name}: invalid short-id '{sid}'"
                                )
                                continue

                            proxy["reality-opts"] = {
                                "public-key": pbk,
                                "short-id": sid,
                            }

                if proxy["network"] == "ws":
                    proxy["ws-opts"] = {
                        "path": cfg.get("path", "/"),
                        "headers": {
                            "Host": cfg.get("host") or cfg.get("sni") or cfg["server"]
                        },
                    }
                elif proxy["network"] == "grpc":
                    proxy["grpc-opts"] = {
                        "grpc-service-name": cfg.get("serviceName", "")
                    }
                elif proxy["network"] == "httpupgrade":
                    proxy["httpupgrade-opts"] = {
                        "path": cfg.get("path", "/"),
                        "host": cfg.get("host") or cfg.get("sni") or cfg["server"],
                    }
                elif proxy["network"] in ("splithttp", "xhttp"):
                    proxy["network"] = "splithttp"
                    proxy["splithttp-opts"] = {
                        "path": cfg.get("path", "/"),
                        "host": cfg.get("host") or cfg.get("sni") or cfg["server"],
                    }

                proxies.append(proxy)
            except Exception as error:
                logger.error(f"Error processing config for Clash: {error}")
                continue

        yaml_lines = [
            "mixed-port: 7890",
            "allow-lan: false",
            "mode: rule",
            "log-level: warning",
            "ipv6: true",
            "",
            "proxies:",
        ]

        proxy_names = []
        for proxy in proxies:
            proxy_names.append(proxy["name"])
            yaml_lines.append(
                f"  - name: \"{ClashGenerator.escape_yaml_str(proxy['name'])}\""
            )
            yaml_lines.append(f"    type: {proxy['type']}")
            yaml_lines.append(f"    server: {proxy['server']}")
            yaml_lines.append(f"    port: {proxy['port']}")
            if proxy["type"] == "vless":
                yaml_lines.append(f"    uuid: {proxy['uuid']}")
                yaml_lines.append(f"    cipher: {proxy['cipher']}")
            elif proxy["type"] == "trojan":
                yaml_lines.append(f"    password: {proxy['password']}")
            yaml_lines.append(f"    udp: {str(proxy['udp']).lower()}")
            yaml_lines.append(f"    tls: {str(proxy.get('tls', False)).lower()}")
            yaml_lines.append(f"    network: {proxy['network']}")
            yaml_lines.append(
                f"    skip-cert-verify: {str(proxy['skip-cert-verify']).lower()}"
            )

            if "flow" in proxy:
                yaml_lines.append(f"    flow: {proxy['flow']}")
            if "servername" in proxy and proxy["servername"]:
                yaml_lines.append(f"    servername: {proxy['servername']}")
            if "client-fingerprint" in proxy:
                yaml_lines.append(
                    f"    client-fingerprint: {proxy['client-fingerprint']}"
                )

            if "reality-opts" in proxy:
                yaml_lines.append("    reality-opts:")
                yaml_lines.append(
                    f"      public-key: {proxy['reality-opts']['public-key']}"
                )
                yaml_lines.append(
                    f"      short-id: \"{proxy['reality-opts']['short-id']}\""
                )

            if "ws-opts" in proxy:
                yaml_lines.append("    ws-opts:")
                yaml_lines.append(f"      path: \"{proxy['ws-opts']['path']}\"")
                if proxy["ws-opts"]["headers"]["Host"]:
                    yaml_lines.append("      headers:")
                    yaml_lines.append(
                        f"        Host: {proxy['ws-opts']['headers']['Host']}"
                    )

            if "grpc-opts" in proxy:
                yaml_lines.append("    grpc-opts:")
                yaml_lines.append(
                    f"      grpc-service-name: \"{proxy['grpc-opts']['grpc-service-name']}\""
                )

            if "httpupgrade-opts" in proxy:
                yaml_lines.append("    httpupgrade-opts:")
                yaml_lines.append(f"      path: \"{proxy['httpupgrade-opts']['path']}\"")
                yaml_lines.append(f"      host: {proxy['httpupgrade-opts']['host']}")

            if "splithttp-opts" in proxy:
                yaml_lines.append("    splithttp-opts:")
                yaml_lines.append(f"      path: \"{proxy['splithttp-opts']['path']}\"")
                yaml_lines.append(f"      host: {proxy['splithttp-opts']['host']}")

        if proxy_names:
            country_map = {}
            for name in proxy_names:
                country = ClashGenerator._extract_country_label(name)
                country_map.setdefault(country, []).append(name)

            speed_sorted = sorted(
                proxy_names,
                key=ClashGenerator._extract_speed_mbps,
                reverse=True,
            )

            yaml_lines.append("")
            yaml_lines.append("proxy-groups:")

            yaml_lines.append("  - name: \"Best Ping\"")
            yaml_lines.append("    type: url-test")
            yaml_lines.append("    url: \"http://www.gstatic.com/generate_204\"")
            yaml_lines.append("    interval: 180")
            yaml_lines.append("    tolerance: 20")
            yaml_lines.append("    proxies:")
            for name in proxy_names:
                yaml_lines.append(f"      - \"{ClashGenerator.escape_yaml_str(name)}\"")

            yaml_lines.append("")
            yaml_lines.append("  - name: \"Best Speed\"")
            yaml_lines.append("    type: select")
            yaml_lines.append("    proxies:")
            for name in speed_sorted:
                yaml_lines.append(f"      - \"{ClashGenerator.escape_yaml_str(name)}\"")

            country_group_names = []
            for country in sorted(country_map.keys()):
                group_name = f"Country: {country}"
                country_group_names.append(group_name)
                yaml_lines.append("")
                yaml_lines.append(
                    f"  - name: \"{ClashGenerator.escape_yaml_str(group_name)}\""
                )
                yaml_lines.append("    type: select")
                yaml_lines.append("    proxies:")
                for name in country_map[country]:
                    yaml_lines.append(
                        f"      - \"{ClashGenerator.escape_yaml_str(name)}\""
                    )

            yaml_lines.append("")
            yaml_lines.append("  - name: \"Proxy\"")
            yaml_lines.append("    type: select")
            yaml_lines.append("    proxies:")
            yaml_lines.append("      - \"Best Ping\"")
            yaml_lines.append("      - \"Best Speed\"")
            for group_name in country_group_names:
                yaml_lines.append(
                    f"      - \"{ClashGenerator.escape_yaml_str(group_name)}\""
                )
            for name in proxy_names:
                yaml_lines.append(f"      - \"{ClashGenerator.escape_yaml_str(name)}\"")

            yaml_lines.append("")
            yaml_lines.append("  - name: \"Direct\"")
            yaml_lines.append("    type: select")
            yaml_lines.append("    proxies:")
            yaml_lines.append("      - DIRECT")
            yaml_lines.append("      - \"Proxy\"")

            yaml_lines.append("")
            yaml_lines.append("rules:")
            for domain_suffix in _RU_DOMAIN_SUFFIXES:
                yaml_lines.append(f"  - DOMAIN-SUFFIX,{domain_suffix},DIRECT")
            yaml_lines.append("  - GEOIP,RU,DIRECT,no-resolve")
            yaml_lines.append("  - GEOSITE,category-ru,DIRECT")
            yaml_lines.append("  - IP-CIDR,192.168.0.0/16,DIRECT,no-resolve")
            yaml_lines.append("  - IP-CIDR,10.0.0.0/8,DIRECT,no-resolve")
            yaml_lines.append("  - IP-CIDR,172.16.0.0/12,DIRECT,no-resolve")
            yaml_lines.append("  - MATCH,Proxy")

        return "\n".join(yaml_lines)

    @staticmethod
    def escape_yaml_str(value: str) -> str:
        escaped = value.replace('"', "")
        escaped = escaped.replace("\\", "")
        escaped = escaped.replace("•", "-")
        return escaped

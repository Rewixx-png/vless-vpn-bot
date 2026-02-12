import logging
from urllib.parse import parse_qs, unquote

logger = logging.getLogger("LinkParser")

class LinkParser:
    @staticmethod
    def parse_vless(link: str):
        try:
            if not link.startswith("vless://"):
                return None
                
            full_link = link
            rest = link[8:]
            
            remarks = "VLESS Config"
            if "#" in rest:
                rest, remarks_raw = rest.split("#", 1)
                remarks = unquote(remarks_raw).strip()
            
            params_str = ""
            if "?" in rest:
                rest, params_str = rest.split("?", 1)
                
            if "@" in rest:
                userinfo, host_port = rest.split("@", 1)
            else:
                return None
            
            # ИСПРАВЛЕНИЕ: Используем rsplit для корректного отделения порта
            if ":" in host_port:
                server, port_str = host_port.rsplit(":", 1)
                
                # Обработка IPv6 в скобках [::1]
                if server.startswith("[") and server.endswith("]"):
                    server = server[1:-1]
                
                try:
                    port = int(port_str)
                except ValueError:
                    logger.warning(f"Invalid port: {port_str} in link {link[:30]}...")
                    return None
            else:
                # Нет порта - некорректная ссылка VLESS
                logger.warning(f"No port found in link: {link[:30]}...")
                return None
                
            params = parse_qs(params_str)
            
            def get_p(key, default=""):
                return params.get(key, [default])[0]
            
            config = {
                "uuid": userinfo,
                "server": server,
                "port": port,
                "type": get_p("type", "tcp"),
                "security": get_p("security", "none"),
                "flow": get_p("flow", ""),
                "sni": get_p("sni", ""),
                "fp": get_p("fp", ""),
                "pbk": get_p("pbk", ""),
                "sid": get_p("sid", ""),
                "path": get_p("path", ""),
                "host": get_p("host", ""),
                "serviceName": get_p("serviceName", ""),
                "mode": get_p("mode", ""),
                "ps": remarks,
                "name": remarks,
                "full_config": full_link,
                "original": full_link
            }
            return config
        except Exception as e:
            logger.error(f"Parser Error processing link: {link[:50]}... Exception: {e}")
            return None
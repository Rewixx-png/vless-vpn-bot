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
            # Убираем пробелы и переносы
            link = link.strip()
            rest = link[8:]
            
            remarks = "VLESS Config"
            if "#" in rest:
                rest, remarks_raw = rest.split("#", 1)
                remarks = unquote(remarks_raw).strip()
            
            params_str = ""
            if "?" in rest:
                rest, params_str = rest.split("?", 1)
            
            rest = rest.rstrip("/")

            if "@" in rest:
                userinfo, host_port = rest.split("@", 1)
            else:
                return None
            
            if ":" in host_port:
                server, port_str = host_port.rsplit(":", 1)
                
                # IPv6 fix
                if server.startswith("[") and server.endswith("]"):
                    server = server[1:-1]
                
                port_str = port_str.split("/")[0].split("?")[0].split("#")[0]

                try:
                    port = int(port_str)
                except ValueError:
                    return None
            else:
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
        except Exception:
            return None
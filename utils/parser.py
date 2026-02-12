import re
import logging
from urllib.parse import parse_qs, unquote

logger = logging.getLogger("LinkParser")

class LinkParser:
    @staticmethod
    def parse_vless(link: str):
        try:
            if not link.startswith("vless://"):
                return None
                
            rest = link[8:]
            
            remarks = "VLESS Config"
            if "#" in rest:
                rest, remarks_raw = rest.split("#", 1)
                remarks = unquote(remarks_raw).strip()
                if not remarks:
                    remarks = "VLESS Config"
                
            params_str = ""
            if "?" in rest:
                rest, params_str = rest.split("?", 1)
                
            if "@" in rest:
                userinfo, server_port = rest.split("@", 1)
            else:
                return None
                
            if ":" in server_port:
                server, port = server_port.split(":", 1)
                try:
                    port = int(port)
                except:
                    logger.warning(f"Invalid port in link: {link[:30]}...")
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
                "full_config": link,
                "original": link
            }
            return config
        except Exception as e:
            logger.error(f"Error parsing link: {link[:50]}... Error: {e}")
            return None
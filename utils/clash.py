import logging
import re

logger = logging.getLogger("ClashGen")

class ClashGenerator:
    @staticmethod
    def is_valid_short_id(sid: str) -> bool:
        """
        Проверяет валидность Short ID для Reality.
        Должен быть hex-строкой.
        """
        if not sid:
            return True # Пустой sid допустим
        # Проверка на Hex символы
        return bool(re.match(r'^[0-9a-fA-F]+$', sid))

    @staticmethod
    def generate_conf(configs: list) -> str:
        proxies = []
        name_counter = {}
        
        for cfg in configs:
            try:
                base_name = cfg.get('name') or cfg.get('ps') or f"VLESS-{cfg['server']}"
                
                if base_name in name_counter:
                    name_counter[base_name] += 1
                    final_name = f"{base_name} {name_counter[base_name]}"
                else:
                    name_counter[base_name] = 1
                    final_name = base_name
                
                proxy = {
                    "name": final_name,
                    "type": "vless",
                    "server": cfg['server'],
                    "port": cfg['port'],
                    "uuid": cfg['uuid'],
                    "cipher": "auto",
                    "udp": True,
                    "tls": False,
                    "network": cfg.get('type', 'tcp'),
                    "skip-cert-verify": True
                }

                if cfg.get('flow'):
                    proxy['flow'] = cfg['flow']

                security = cfg.get('security', 'none')
                
                if security in ['tls', 'reality']:
                    proxy['tls'] = True
                    proxy['servername'] = cfg.get('sni') or cfg.get('host') or cfg['server']
                    proxy['client-fingerprint'] = cfg.get('fp', 'chrome')
                    
                    if security == 'reality':
                        pbk = cfg.get('pbk', '')
                        sid = cfg.get('sid', '')
                        
                        # ВАЖНО: Валидация short-id
                        if not ClashGenerator.is_valid_short_id(sid):
                            logger.warning(f"Skipping config {final_name}: Invalid short-id '{sid}'")
                            continue # Пропускаем этот конфиг, чтобы не сломать весь файл

                        proxy['reality-opts'] = {
                            "public-key": pbk,
                            "short-id": sid
                        }

                if proxy['network'] == 'ws':
                    ws_opts = {
                        "path": cfg.get('path', '/'),
                        "headers": {
                            "Host": cfg.get('host') or cfg.get('sni') or cfg['server']
                        }
                    }
                    proxy['ws-opts'] = ws_opts
                
                elif proxy['network'] == 'grpc':
                    grpc_opts = {
                        "grpc-service-name": cfg.get('serviceName', '')
                    }
                    proxy['grpc-opts'] = grpc_opts

                proxies.append(proxy)
            except Exception as e:
                logger.error(f"Error processing config for Clash: {e}")
                continue

        yaml_lines = [
            "mixed-port: 7890",
            "allow-lan: false",
            "mode: rule",
            "log-level: warning",
            "ipv6: true",
            "",
            "proxies:"
        ]
        proxy_names = []

        for p in proxies:
            proxy_names.append(p['name'])
            yaml_lines.append(f"  - name: \"{ClashGenerator.escape_yaml_str(p['name'])}\"")
            yaml_lines.append(f"    type: {p['type']}")
            yaml_lines.append(f"    server: {p['server']}")
            yaml_lines.append(f"    port: {p['port']}")
            yaml_lines.append(f"    uuid: {p['uuid']}")
            yaml_lines.append(f"    cipher: {p['cipher']}")
            yaml_lines.append(f"    udp: {str(p['udp']).lower()}")
            yaml_lines.append(f"    tls: {str(p['tls']).lower()}")
            yaml_lines.append(f"    network: {p['network']}")
            yaml_lines.append(f"    skip-cert-verify: {str(p['skip-cert-verify']).lower()}")
            
            if 'flow' in p:
                yaml_lines.append(f"    flow: {p['flow']}")
            if 'servername' in p and p['servername']:
                yaml_lines.append(f"    servername: {p['servername']}")
            if 'client-fingerprint' in p:
                yaml_lines.append(f"    client-fingerprint: {p['client-fingerprint']}")
                
            if 'reality-opts' in p:
                yaml_lines.append("    reality-opts:")
                yaml_lines.append(f"      public-key: {p['reality-opts']['public-key']}")
                yaml_lines.append(f"      short-id: \"{p['reality-opts']['short-id']}\"") # short-id лучше в кавычки
                
            if 'ws-opts' in p:
                yaml_lines.append("    ws-opts:")
                yaml_lines.append(f"      path: \"{p['ws-opts']['path']}\"")
                if p['ws-opts']['headers']['Host']:
                    yaml_lines.append("      headers:")
                    yaml_lines.append(f"        Host: {p['ws-opts']['headers']['Host']}")
                    
            if 'grpc-opts' in p:
                yaml_lines.append("    grpc-opts:")
                yaml_lines.append(f"      grpc-service-name: \"{p['grpc-opts']['grpc-service-name']}\"")

        if proxy_names:
            yaml_lines.append("")
            yaml_lines.append("proxy-groups:")
            
            yaml_lines.append("  - name: \"🚀 Auto Select\"")
            yaml_lines.append("    type: url-test")
            yaml_lines.append("    url: \"http://www.gstatic.com/generate_204\"")
            yaml_lines.append("    interval: 300")
            yaml_lines.append("    tolerance: 50")
            yaml_lines.append("    proxies:")
            for name in proxy_names:
                yaml_lines.append(f"      - \"{ClashGenerator.escape_yaml_str(name)}\"")
            
            yaml_lines.append("")
            yaml_lines.append("  - name: \"🌍 Proxy\"")
            yaml_lines.append("    type: select")
            yaml_lines.append("    proxies:")
            yaml_lines.append("      - \"🚀 Auto Select\"")
            for name in proxy_names:
                yaml_lines.append(f"      - \"{ClashGenerator.escape_yaml_str(name)}\"")

            yaml_lines.append("")
            yaml_lines.append("rules:")
            yaml_lines.append("  - MATCH, \"🌍 Proxy\"")

        return "\n".join(yaml_lines)

    @staticmethod
    def escape_yaml_str(s):
        return s.replace('"', '\\"').replace('\\', '\\\\')

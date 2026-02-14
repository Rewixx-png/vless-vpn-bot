import json
import asyncio
import os
import random
import logging
from utils.parser import LinkParser

logger = logging.getLogger("XrayCore")

class XrayExecutor:
    XRAY_BIN = "/usr/local/bin/xray"
    
    @staticmethod
    def _generate_config(parsed: dict, local_port: int) -> dict:
        outbound = {
            "protocol": "vless",
            "settings": {
                "vnext": [{
                    "address": parsed['server'],
                    "port": parsed['port'],
                    "users": [{"id": parsed['uuid'], "encryption": "none", "flow": parsed.get('flow', '')}]
                }]
            },
            "streamSettings": {
                "network": parsed['type'],
                "security": parsed['security']
            }
        }
        stream = outbound["streamSettings"]
        
        if parsed['security'] in ['tls', 'reality']:
            tls_settings = {
                "serverName": parsed.get('sni') or parsed.get('host', ''),
                "fingerprint": parsed.get('fp', 'chrome'),
                "allowInsecure": True
            }
            if parsed['security'] == 'reality':
                tls_settings['show'] = False
                tls_settings['publicKey'] = parsed.get('pbk', '')
                tls_settings['shortId'] = parsed.get('sid', '')
                tls_settings['spiderX'] = "/"
                stream['realitySettings'] = tls_settings
            else:
                stream['tlsSettings'] = tls_settings

        if parsed['type'] == 'ws':
            stream['wsSettings'] = {"path": parsed.get('path', '/'), "headers": {"Host": parsed.get('host') or parsed.get('sni', '')}}
        elif parsed['type'] == 'grpc':
            stream['grpcSettings'] = {"serviceName": parsed.get('serviceName', ''), "multiMode": (parsed.get('mode') == 'multi')}
        elif parsed['type'] == 'tcp' and parsed.get('type') == 'http':
             stream['tcpSettings'] = {"header": {"type": "http", "request": {"headers": {"Host": [parsed.get('host', '')]}}}}

        return {
            "log": {"loglevel": "none"},
            "inbounds": [{"port": local_port, "protocol": "socks", "settings": {"auth": "noauth", "udp": True}, "sniffing": {"enabled": True, "destOverride": ["http", "tls"]}}],
            "outbounds": [outbound, {"protocol": "freedom", "tag": "direct"}]
        }

    @classmethod
    async def start_xray(cls, config_url: str) -> tuple[asyncio.subprocess.Process | None, int, str]:
        parsed = LinkParser.parse_vless(config_url)
        if not parsed:
            return None, 0, "Invalid Link"

        local_port = random.randint(10000, 60000)
        config_path = f"/tmp/xray_check_{local_port}.json"

        try:
            xray_conf = cls._generate_config(parsed, local_port)
            with open(config_path, 'w') as f:
                json.dump(xray_conf, f)

            process = await asyncio.create_subprocess_exec(
                cls.XRAY_BIN, "-c", config_path,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL
            )
            
            try:
                await asyncio.wait_for(process.wait(), timeout=0.2)
                return None, 0, "Xray failed startup"
            except asyncio.TimeoutError:
                pass 

            return process, local_port, config_path
        except Exception as e:
            return None, 0, str(e)

    @staticmethod
    def cleanup(process, config_path):
        if process and process.returncode is None:
            try:
                process.terminate()
            except: pass
            
            async def force_kill():
                try:
                    await asyncio.sleep(0.1)
                    if process.returncode is None:
                        process.kill()
                        await process.wait()
                except: pass
            
            asyncio.create_task(force_kill())

        if config_path and os.path.exists(config_path):
            try: os.remove(config_path)
            except: pass
import json
import asyncio
import os
import random
import logging
import uuid
from utils.parser import LinkParser

logger = logging.getLogger("XrayCore")

class XrayExecutor:
    XRAY_BIN = "/usr/local/bin/xray"
    
    @staticmethod
    def _generate_config(parsed: dict, local_port: int) -> dict:
        encryption = parsed.get('encryption', 'none')
        if encryption == 'auto':
            encryption = 'none'
        
        flow = parsed.get('flow', '')
        if parsed['security'] == 'reality' and not flow and parsed['type'] == 'tcp':
             flow = 'xtls-rprx-vision'

        outbound = {
            "protocol": "vless",
            "settings": {
                "vnext": [{
                    "address": parsed['server'],
                    "port": parsed['port'],
                    "users": [{"id": parsed['uuid'], "encryption": encryption, "flow": flow}]
                }]
            },
            "streamSettings": {
                "network": parsed['type'],
                "security": parsed['security']
            },
            "tag": "proxy"
        }
        stream = outbound["streamSettings"]
        
        if parsed['security'] in['tls', 'reality']:
            fp = parsed.get('fp', '')
            if not fp or fp == 'random':
                fp = random.choice(['chrome', 'firefox', 'edge'])
                
            tls_settings = {
                "serverName": parsed.get('sni') or parsed.get('host') or parsed['server'],
                "fingerprint": fp,
                "allowInsecure": True
            }
            if parsed['security'] == 'reality':
                tls_settings['show'] = False
                tls_settings['publicKey'] = parsed.get('pbk', '')
                tls_settings['shortId'] = parsed.get('sid', '')
                tls_settings['spiderX'] = parsed.get('spx', '/')
                stream['realitySettings'] = tls_settings
            else:
                stream['tlsSettings'] = tls_settings

        if parsed['type'] == 'ws':
            stream['wsSettings'] = {
                "path": parsed.get('path', '/'), 
                "headers": {"Host": parsed.get('host') or parsed.get('sni', '')}
            }
        elif parsed['type'] == 'grpc':
            stream['grpcSettings'] = {
                "serviceName": parsed.get('serviceName', ''), 
                "multiMode": (parsed.get('mode') == 'multi')
            }

        return {
            "log": {"loglevel": "none"},
            "inbounds":[{
                "port": local_port, 
                "protocol": "socks", 
                "settings": {"auth": "noauth", "udp": True}, 
                "sniffing": {"enabled": True, "destOverride": ["http", "tls"]}
            }],
            "outbounds": [outbound] 
        }

    @classmethod
    async def start_xray(cls, config_url: str) -> tuple[asyncio.subprocess.Process | None, int, str]:
        parsed = LinkParser.parse_vless(config_url)
        if not parsed:
            return None, 0, "CONFIG_ERR: Invalid Link Format"
        
        import re
        uuid_pattern = r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
        if not re.match(uuid_pattern, parsed.get('uuid', ''), re.IGNORECASE):
            return None, 0, "CONFIG_ERR: Invalid UUID Format"

        local_port = random.randint(20000, 60000)
        unique_id = uuid.uuid4().hex
        config_path = f"/tmp/xray_{unique_id}.json"

        try:
            xray_conf = cls._generate_config(parsed, local_port)
            with open(config_path, 'w') as f:
                json.dump(xray_conf, f)

            process = await asyncio.create_subprocess_exec(
                cls.XRAY_BIN, "-c", config_path,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
                start_new_session=True
            )
            
            try:
                await asyncio.wait_for(process.wait(), timeout=0.5)
                cls._cleanup_file(config_path)
                return None, 0, "CONFIG_ERR: Xray Crashed on Start"
            except asyncio.TimeoutError:
                pass

            port_open = False
            start_wait = asyncio.get_event_loop().time()
            while asyncio.get_event_loop().time() - start_wait < 3.0:
                if process.returncode is not None:
                    await cls.cleanup(process, config_path)
                    return None, 0, "CONFIG_ERR: Xray Crashed during bind"
                try:
                    _, writer = await asyncio.open_connection('127.0.0.1', local_port)
                    writer.close()
                    await writer.wait_closed()
                    port_open = True
                    break
                except Exception:
                    await asyncio.sleep(0.05)

            if not port_open:
                await cls.cleanup(process, config_path)
                return None, 0, "SYS_ERR: Xray Port Bind Timeout"

            return process, local_port, config_path
        except Exception as e:
            await cls.cleanup(None, config_path)
            return None, 0, f"SYS_ERR: {str(e)}"

    @staticmethod
    def _cleanup_file(config_path: str):
        if config_path and os.path.exists(config_path):
            try:
                os.remove(config_path)
            except Exception:
                pass
    
    @staticmethod
    def cleanup_zombies():
        try:
            import subprocess
            subprocess.run(["pkill", "-9", "-f", "xray_.*.json"],
                capture_output=True
            )
        except Exception:
            pass
    
    @classmethod
    async def cleanup(cls, process, config_path):
        if process:
            try:
                if process.returncode is None:
                    process.terminate()
                    try:
                        await asyncio.wait_for(process.wait(), timeout=1.0)
                    except asyncio.TimeoutError:
                        process.kill()
                        await process.wait()
            except Exception:
                pass
        
        cls._cleanup_file(config_path)
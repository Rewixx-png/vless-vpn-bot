import json
import asyncio
import os
import random
import logging
import signal
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

    XRAY_STARTUP_TIMEOUT = 0.5  # Increased slightly for stability
    XRAY_MAX_LIFETIME = 10.0    # Maximum lifetime for xray process
    
    @classmethod
    async def start_xray(cls, config_url: str) -> tuple[asyncio.subprocess.Process | None, int, str]:
        parsed = LinkParser.parse_vless(config_url)
        if not parsed:
            return None, 0, "Invalid Link"

        local_port = random.randint(20000, 55000)  # More conservative port range
        config_path = f"/tmp/xray_check_{local_port}.json"

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
            
            # Wait and check if process started successfully
            try:
                await asyncio.wait_for(process.wait(), timeout=cls.XRAY_STARTUP_TIMEOUT)
                # If we get here, process exited immediately
                cls._cleanup_file(config_path)
                return None, 0, "Xray failed startup (crashed immediately)"
            except asyncio.TimeoutError:
                # Process is still running, good!
                pass 

            return process, local_port, config_path
        except Exception as e:
            cls._cleanup_file(config_path)
            return None, 0, str(e)

    @staticmethod
    def _cleanup_file(config_path: str):
        """Safely remove config file"""
        if config_path and os.path.exists(config_path):
            try:
                os.remove(config_path)
            except Exception:
                pass
    
    @classmethod
    async def cleanup(cls, process, config_path):
        """Enhanced cleanup with timeout and zombie prevention"""
        if process:
            try:
                if process.returncode is None:
                    # Try graceful termination first
                    try:
                        os.killpg(os.getpgid(process.pid), signal.SIGTERM)
                        # Wait a bit for graceful shutdown
                        try:
                            await asyncio.wait_for(process.wait(), timeout=0.5)
                        except asyncio.TimeoutError:
                            # Force kill if still running
                            os.killpg(os.getpgid(process.pid), signal.SIGKILL)
                    except ProcessLookupError:
                        pass  # Already dead
                    except Exception:
                        # Fallback to direct kill
                        try:
                            process.kill()
                            await asyncio.wait_for(process.wait(), timeout=1.0)
                        except Exception:
                            pass
            except Exception:
                pass
        
        cls._cleanup_file(config_path)
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
    def _build_upstream_outbound(upstream_proxy: dict) -> dict | None:
        if not isinstance(upstream_proxy, dict):
            return None

        scheme = str(upstream_proxy.get("scheme", "") or "").strip().lower()
        host = str(upstream_proxy.get("host", "") or "").strip()
        username = str(upstream_proxy.get("username", "") or "").strip()
        password = str(upstream_proxy.get("password", "") or "").strip()

        try:
            port = int(upstream_proxy.get("port", 0) or 0)
        except Exception:
            port = 0

        if not host or port < 1 or port > 65535:
            return None

        if scheme.startswith("http"):
            protocol = "http"
        elif scheme.startswith("socks"):
            protocol = "socks"
        else:
            return None

        server = {
            "address": host,
            "port": port,
        }
        if username:
            server["users"] = [{"user": username, "pass": password}]

        return {
            "protocol": protocol,
            "settings": {
                "servers": [server],
            },
            "tag": "ru-upstream",
        }

    @staticmethod
    def _generate_config(parsed: dict, local_port: int, upstream_proxy: dict | None = None) -> dict:
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
            "tag": "vless-main"
        }
        stream = outbound["streamSettings"]

        outbounds = [outbound]
        upstream_outbound = XrayExecutor._build_upstream_outbound(upstream_proxy or {})
        if upstream_outbound:
            outbound["proxySettings"] = {
                "tag": upstream_outbound["tag"],
                "transportLayer": False,
            }
            outbounds.append(upstream_outbound)

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
            "outbounds": outbounds
        }

    @classmethod
    async def start_xray(
        cls,
        config_url: str,
        upstream_proxy: dict | None = None,
    ) -> tuple[asyncio.subprocess.Process | None, int, str]:
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
            xray_conf = cls._generate_config(parsed, local_port, upstream_proxy=upstream_proxy)
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
    def cleanup_zombies(max_age_sec: int = 300):
        try:
            import re
            import time
            import psutil

            now = time.time()
            pattern = re.compile(r"/tmp/xray_[0-9a-f]+\.json", re.IGNORECASE)

            for proc in psutil.process_iter(["name", "cmdline", "create_time"]):
                try:
                    cmdline = proc.info.get("cmdline") or []
                    if not cmdline:
                        continue

                    cmdline_str = " ".join(cmdline)
                    proc_name = (proc.info.get("name") or "").lower()

                    if "xray" not in proc_name and "/xray" not in cmdline_str:
                        continue

                    match = pattern.search(cmdline_str)
                    if not match:
                        continue

                    config_path = match.group(0)
                    proc_age = now - float(proc.info.get("create_time") or now)
                    config_age = proc_age

                    if os.path.exists(config_path):
                        try:
                            config_age = now - os.path.getmtime(config_path)
                        except Exception:
                            config_age = proc_age

                    if proc_age < max_age_sec and config_age < max_age_sec:
                        continue

                    try:
                        proc.terminate()
                        proc.wait(timeout=0.8)
                    except Exception:
                        try:
                            proc.kill()
                        except Exception:
                            pass
                except Exception:
                    continue
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

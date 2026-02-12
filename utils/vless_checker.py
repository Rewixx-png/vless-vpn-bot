import json
import asyncio
import aiohttp
import time
import os
import random
import logging
from aiohttp_socks import ProxyConnector
from utils.parser import LinkParser

logger = logging.getLogger("XrayChecker")

class VlessChecker:
    XRAY_BIN = "/usr/local/bin/xray"
    
    HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    GEOIP_PROVIDERS = [
        {"url": "http://ip-api.com/json/?fields=country,countryCode", "code_key": "countryCode", "name_key": None}, # name_key None = используем код
        {"url": "http://ipwho.is/", "code_key": "country_code", "name_key": None},
        {"url": "https://api.myip.com", "code_key": "cc", "name_key": None},
        {"url": "https://ipinfo.io/json", "code_key": "country", "name_key": None},
        {"url": "https://ifconfig.co/json", "code_key": "country_iso", "name_key": None}
    ]

    @staticmethod
    def _get_flag_emoji(country_code: str) -> str:
        if not country_code or len(country_code) != 2:
            return "🌍"
        return "".join(chr(ord(c.upper()) + 127397) for c in country_code)

    @staticmethod
    def parse_config(config_url: str):
        return LinkParser.parse_vless(config_url)

    @staticmethod
    def _generate_xray_config(parsed: dict, local_port: int) -> dict:
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
    async def process_subscription(cls, config_url: str) -> tuple[bool, str, int, bool, str]:
        parsed = cls.parse_config(config_url)
        if not parsed:
            return False, "", 0, False, "Invalid Link Format"

        local_port = random.randint(10000, 60000)
        config_path = f"/tmp/xray_check_{local_port}.json"
        
        try:
            xray_conf = cls._generate_xray_config(parsed, local_port)
            with open(config_path, 'w') as f:
                json.dump(xray_conf, f)
        except Exception as e:
            return False, "", 0, False, f"Config Gen Error: {e}"

        process = None
        try:
            process = await asyncio.create_subprocess_exec(
                cls.XRAY_BIN, "-c", config_path,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL
            )
            await asyncio.sleep(0.2)
            if process.returncode is not None:
                 return False, "", 0, False, "Xray failed to start"

            connector = ProxyConnector.from_url(f"socks5://127.0.0.1:{local_port}")
            timeout = aiohttp.ClientTimeout(total=6, connect=3)
            
            async with aiohttp.ClientSession(connector=connector, timeout=timeout) as proxy_session:
                start_time = time.monotonic()
                latency = 9999
                
                try:
                    async with proxy_session.get('http://cp.cloudflare.com/generate_204', allow_redirects=False) as resp:
                        if resp.status in [200, 204]:
                            latency = int((time.monotonic() - start_time) * 1000)
                        else:
                            raise Exception(f"Status {resp.status}")
                except Exception as e:
                    return False, "", 0, False, f"Connection Failed: {str(e)}"

                region = "🌍 UNK"
                ai_available = False

                if latency < 2000:
                    try:
                        ai_timeout = aiohttp.ClientTimeout(total=2.5)
                        async with proxy_session.get('https://api.openai.com/v1/models', timeout=ai_timeout) as ai_resp:
                            if ai_resp.status in [200, 401, 403]:
                                ai_available = True
                    except: pass

                    for provider in cls.GEOIP_PROVIDERS:
                        try:
                            async with proxy_session.get(provider["url"], timeout=2.5) as geo_resp:
                                if geo_resp.status == 200:
                                    data = await geo_resp.json()
                                    code = data.get(provider["code_key"])
                                    # ИЗМЕНЕНИЕ: Формат региона теперь "🇩🇪 DE"
                                    if code and len(code) == 2:
                                        region = f"{cls._get_flag_emoji(code)} {code.upper()}"
                                        break
                        except: continue

            return True, region, latency, ai_available, "OK"

        except Exception as e:
            return False, "", 0, False, f"System Error: {e}"
        finally:
            if process:
                try:
                    process.terminate()
                    try: await asyncio.wait_for(process.wait(), timeout=0.1)
                    except: process.kill()
                except: pass
            if os.path.exists(config_path):
                try: os.remove(config_path)
                except: pass

    @classmethod
    async def get_regions_batch(cls, ips: list[str], session: aiohttp.ClientSession) -> dict[str, str]:
        results = {}
        if not ips: return results
        try:
            for i in range(0, len(ips), 100):
                chunk = ips[i:i+100]
                try:
                    payload = [{"query": ip, "fields": "status,query,country,countryCode"} for ip in chunk]
                    async with session.post("http://ip-api.com/batch", json=payload, timeout=10) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            for item in data:
                                if item.get("status") == "success":
                                    code = item.get("countryCode")
                                    # Формат региона в batch
                                    results[item.get("query")] = f"{cls._get_flag_emoji(code)} {code}"
                except: pass
        except: pass
        return results

    @staticmethod
    async def verify_domain(domain: str) -> tuple[bool, str]:
        try:
            loop = asyncio.get_running_loop()
            try:
                ip = await loop.getaddrinfo(domain, 80)
                ip_addr = ip[0][4][0]
            except: return False, "DNS Resolve Failed"
            return True, f"OK ({ip_addr})"
        except Exception as e: return False, str(e)
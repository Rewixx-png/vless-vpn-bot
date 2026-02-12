import re
import time
import asyncio
import aiohttp
import base64
import json
import ssl
import uuid
import struct
import socket
from urllib.parse import urlparse, parse_qs
from typing import Optional, Tuple, Dict, List

class VlessChecker:
    HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    @staticmethod
    def _get_flag_emoji(country_code: str) -> str:
        if not country_code or len(country_code) != 2:
            return "🌍"
        return "".join(chr(ord(c.upper()) + 127397) for c in country_code)

    @staticmethod
    def parse_config(config_url: str) -> Optional[Dict[str, str]]:
        config_url = config_url.strip()
        try:
            if config_url.startswith("vmess://"):
                b64_part = config_url.replace("vmess://", "")
                missing_padding = len(b64_part) % 4
                if missing_padding:
                    b64_part += '=' * (4 - missing_padding)
                decoded = base64.b64decode(b64_part).decode('utf-8')
                data = json.loads(decoded)
                return {
                    "host": data.get("add"),
                    "port": int(data.get("port")),
                    "protocol": "vmess",
                    "uuid": data.get("id"),
                    "security": data.get("tls", ""),
                    "sni": data.get("sni", "") or data.get("host", ""),
                    "path": data.get("path", "/"),
                    "full_url": config_url
                }
            elif config_url.startswith(("vless://", "trojan://", "ss://")):
                parsed = urlparse(config_url)
                params = parse_qs(parsed.query)
                host = parsed.hostname
                port = parsed.port
                if not host or not port: return None
                
                protocol = "vless"
                if config_url.startswith("trojan://"): protocol = "trojan"
                elif config_url.startswith("ss://"): protocol = "ss"
                
                security = params.get("security", [""])[0]
                sni = params.get("sni", [""])[0] or params.get("host", [""])[0]
                path = params.get("path", ["/"])[0]
                
                return {
                    "host": host,
                    "port": port,
                    "protocol": protocol,
                    "uuid": parsed.username, 
                    "security": security,
                    "sni": sni,
                    "path": path,
                    "full_url": config_url
                }
            return None
        except: return None

    @classmethod
    async def check_connection(cls, config_data: Dict) -> int:
        protocol = config_data.get("protocol")
        if protocol == "vless":
            return await cls._deep_check_vless(config_data)
        return await cls._simple_tcp_check(config_data)

    @staticmethod
    async def _deep_check_vless(conf: Dict) -> int:
        host = conf["host"]
        port = conf["port"]
        user_uuid = conf.get("uuid")
        sni = conf.get("sni") or host
        
        if not user_uuid:
            return -1

        try:
            uid_bytes = uuid.UUID(user_uuid).bytes
        except ValueError:
            return -1

        target_host = "cp.cloudflare.com"
        target_port = 80
        
        addr_bytes = target_host.encode()
        
        vless_header = (
            b'\x00' +                 
            uid_bytes +               
            b'\x00' +                 
            b'\x01' +                 
            struct.pack('>H', target_port) + 
            b'\x02' +                 
            struct.pack('B', len(addr_bytes)) + 
            addr_bytes                
        )

        http_request = (
            f"HEAD /generate_204 HTTP/1.1\r\n"
            f"Host: {target_host}\r\n"
            f"User-Agent: Mozilla/5.0\r\n"
            f"Connection: close\r\n\r\n"
        ).encode()

        start_time = time.monotonic()
        
        writer = None
        try:
            ssl_ctx = ssl.create_default_context()
            ssl_ctx.check_hostname = False
            ssl_ctx.verify_mode = ssl.CERT_NONE
            
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(host, port, ssl=ssl_ctx, server_hostname=sni),
                timeout=5.0
            )

            writer.write(vless_header + http_request)
            await writer.drain()

            data = await asyncio.wait_for(reader.read(512), timeout=5.0)
            
            latency = int((time.monotonic() - start_time) * 1000)
            
            if len(data) < 2:
                return -1

            if data.startswith(b'HTTP') or data.startswith(b'<html') or data.startswith(b'<!DOC'):
                return -1
            
            if b'HTTP/1.1 204' in data or b'HTTP/1.0 204' in data:
                 return latency
            
            if len(data) > 2:
                if b'HTTP' in data:
                    if b'204 No Content' in data or b'200 OK' in data:
                        return latency

            return -1 

        except Exception:
            return -1
        finally:
            if writer:
                try: writer.close()
                except: pass

    @staticmethod
    async def _simple_tcp_check(conf: Dict) -> int:
        host = conf["host"]
        port = conf["port"]
        sni = conf.get("sni", "") or host
        security = conf.get("security", "")

        start_time = time.monotonic()
        
        ssl_ctx = None
        if security in ["tls", "reality", "auto"] or port == 443:
            ssl_ctx = ssl.create_default_context()
            ssl_ctx.check_hostname = False
            ssl_ctx.verify_mode = ssl.CERT_NONE

        writer = None
        try:
            _, writer = await asyncio.wait_for(
                asyncio.open_connection(host, port, ssl=ssl_ctx, server_hostname=sni if ssl_ctx else None),
                timeout=3.0
            )
            latency = int((time.monotonic() - start_time) * 1000)
            writer.close()
            try: await writer.wait_closed()
            except: pass
            return latency
        except:
            if writer:
                try: writer.close()
                except: pass
            return -1

    @classmethod
    async def get_regions_batch(cls, ips: List[str], session: aiohttp.ClientSession) -> Dict[str, str]:
        results = {}
        if not ips: return results
        try:
            for _ in range(2):
                try:
                    payload = [{"query": ip, "fields": "status,query,country,countryCode"} for ip in ips]
                    async with session.post("http://ip-api.com/batch", json=payload, timeout=5) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            for item in data:
                                if item.get("status") == "success":
                                    results[item.get("query")] = f"{cls._get_flag_emoji(item.get('countryCode'))} {item.get('country')}"
                            break 
                except:
                    await asyncio.sleep(1)
        except: pass
        return results

    @classmethod
    async def get_region(cls, host: str, session: aiohttp.ClientSession = None) -> str:
        try:
            if session:
                res = await cls.get_regions_batch([host], session)
                return res.get(host, "🌍 Unknown")
        except: pass
        return "🌍 Unknown"

    @classmethod
    async def process_subscription(cls, config_url: str, session: aiohttp.ClientSession = None) -> Tuple[bool, str, int, str]:
        parsed = cls.parse_config(config_url)
        if not parsed: return False, "", 0, "Format Error"
        
        try:
            # Оборачиваем всю проверку в жесткий таймаут, чтобы избежать зависаний на 99%
            latency = await asyncio.wait_for(cls.check_connection(parsed), timeout=12.0)
        except asyncio.TimeoutError:
            latency = -1
        except Exception:
            latency = -1
        
        if latency == -1: return False, "", 0, "Dead (Deep Check)"
        
        region = await cls.get_region(parsed["host"], session)
        return True, region, latency, "OK"

    @staticmethod
    async def get_server_public_ip() -> str | None:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get('https://api.ipify.org', timeout=5) as resp:
                    return await resp.text()
        except:
            return None

    @staticmethod
    async def verify_domain(domain: str) -> Tuple[bool, str]:
        """
        Проверка домена:
        1. DNS резолв (должен совпадать с публичным IP сервера)
        2. SSL handshake (порт 443)
        """
        try:
            # 1. Получаем IP домена
            domain_ip = socket.gethostbyname(domain)
            
            # 2. Получаем свой внешний IP
            my_ip = await VlessChecker.get_server_public_ip()
            
            if not my_ip:
                # Если не удалось узнать свой IP, пробуем проверить локально настроенный
                # Но лучше вернуть ошибку, чтобы пользователь убедился
                return False, "Не удалось определить внешний IP сервера."
            
            if domain_ip != my_ip:
                return False, f"DNS домена указывает на {domain_ip}, а IP сервера: {my_ip}"

            # 3. Проверка SSL (Порт 443)
            ctx = ssl.create_default_context()
            ctx.check_hostname = False # Проверяем само наличие SSL, валидность сертификата - вторично, но лучше проверить
            ctx.verify_mode = ssl.CERT_NONE # Для теста соединения достаточно
            
            try:
                conn = asyncio.open_connection(domain, 443, ssl=ctx)
                reader, writer = await asyncio.wait_for(conn, timeout=5.0)
                writer.close()
                await writer.wait_closed()
            except Exception as e:
                return False, f"Ошибка подключения к порту 443 (SSL): {e}"

            return True, "OK"

        except socket.gaierror:
            return False, "Не удалось разрешить DNS имя (Домен не существует?)"
        except Exception as e:
            return False, f"Ошибка проверки: {e}"
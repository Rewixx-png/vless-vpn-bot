import re
import time
import asyncio
import aiohttp
import base64
import json
import ssl
import uuid
import struct
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
                    "uuid": parsed.username, # UUID находится в username части url
                    "security": security,
                    "sni": sni,
                    "path": path,
                    "full_url": config_url
                }
            return None
        except: return None

    @classmethod
    async def check_connection(cls, config_data: Dict) -> int:
        """
        Умная проверка:
        1. Если VLESS/Reality -> Выполняет реальный URL Test (Deep Check).
        2. Если VMess/Trojan -> Выполняет TCP/SSL Handshake (Legacy).
        """
        protocol = config_data.get("protocol")
        
        # Для VLESS используем глубокую проверку (URL Test)
        if protocol == "vless":
            return await cls._deep_check_vless(config_data)
        
        # Для остальных пока оставляем TCP Handshake (можно доработать позже)
        return await cls._simple_tcp_check(config_data)

    @staticmethod
    async def _deep_check_vless(conf: Dict) -> int:
        """
        Реализация VLESS URL Test на чистом Python.
        Отправляет VLESS Request Header и пытается получить ответ от cp.cloudflare.com/generate_204
        """
        host = conf["host"]
        port = conf["port"]
        user_uuid = conf.get("uuid")
        sni = conf.get("sni") or host
        
        if not user_uuid:
            return -1

        try:
            # Преобразуем UUID в байты
            uid_bytes = uuid.UUID(user_uuid).bytes
        except ValueError:
            return -1

        # Целевой URL для проверки (Google generate_204 или Cloudflare)
        # Используем HTTP (порт 80), так как HTTPS внутри туннеля требует еще одного слоя TLS
        target_host = "cp.cloudflare.com"
        target_port = 80
        
        # Формируем VLESS Request Header
        # Ver(1) + UUID(16) + AddonsLen(1) + Cmd(1) + Port(2) + AddrType(1) + AddrLen(1) + Addr(N)
        
        # Cmd: 1 = TCP
        # AddrType: 2 = Domain
        addr_bytes = target_host.encode()
        
        vless_header = (
            b'\x00' +                 # Version
            uid_bytes +               # UUID
            b'\x00' +                 # Addons Length (0)
            b'\x01' +                 # Command (TCP)
            struct.pack('>H', target_port) + # Port (Big Endian)
            b'\x02' +                 # Address Type (Domain)
            struct.pack('B', len(addr_bytes)) + # Address Length
            addr_bytes                # Address
        )

        # HTTP Request Payload
        http_request = (
            f"HEAD /generate_204 HTTP/1.1\r\n"
            f"Host: {target_host}\r\n"
            f"User-Agent: Mozilla/5.0\r\n"
            f"Connection: close\r\n\r\n"
        ).encode()

        start_time = time.monotonic()
        
        writer = None
        try:
            # 1. Establish TCP/SSL Connection
            ssl_ctx = ssl.create_default_context()
            ssl_ctx.check_hostname = False
            ssl_ctx.verify_mode = ssl.CERT_NONE
            
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(host, port, ssl=ssl_ctx, server_hostname=sni),
                timeout=4.0
            )

            # 2. Send VLESS Header + HTTP Request
            writer.write(vless_header + http_request)
            await writer.drain()

            # 3. Read Response Header (VLESS Response)
            # VLESS Response: Ver(1) + AddonsLen(1) + Addons(N)
            # Обычно 1-й байт версии ответа совпадает с версией запроса (0)
            
            # Читаем начало ответа. 
            # В Reality при ошибке UUID сервер может вернуть HTML Fallback сайта,
            # а при успехе - VLESS заголовок, а за ним HTTP ответ.
            
            # Читаем первые 512 байт
            data = await asyncio.wait_for(reader.read(512), timeout=4.0)
            
            latency = int((time.monotonic() - start_time) * 1000)
            
            # Анализируем ответ
            # Успешный VLESS ответ должен начинаться с байта версии (0x00)
            # И содержать внутри HTTP ответ от нашего таргета
            
            if len(data) < 2:
                return -1

            # Если вернулся чистый HTTP (начинается с 'HTTP' или '<html'), значит это Fallback -> UUID неверный
            if data.startswith(b'HTTP') or data.startswith(b'<html') or data.startswith(b'<!DOC'):
                return -1
            
            # Проверяем наличие 204 ответа внутри бинарного потока (после заголовка VLESS)
            # Заголовок VLESS ответа: 1 байт версия, 1 байт длина аддонов.
            # Если аддонов 0, то данные начинаются с 3-го байта.
            
            if b'HTTP/1.1 204' in data or b'HTTP/1.0 204' in data:
                 return latency
            
            # Иногда данные приходят кусками, попробуем дочитать если не нашли
            if len(data) > 2:
                # Попробуем найти HTTP ответ
                if b'HTTP' in data:
                    # Проверяем код
                    if b'204 No Content' in data or b'200 OK' in data:
                        return latency

            return -1 # Ответ непонятный, считаем сломанным

        except Exception:
            return -1
        finally:
            if writer:
                try: writer.close()
                except: pass

    @staticmethod
    async def _simple_tcp_check(conf: Dict) -> int:
        """Старая проверка (для VMess/Trojan) - просто хендшейк"""
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

    # --- BATCH GEOIP ---
    @classmethod
    async def get_regions_batch(cls, ips: List[str], session: aiohttp.ClientSession) -> Dict[str, str]:
        results = {}
        if not ips: return results
        try:
            # Используем retry для ip-api, так как он часто сбоит
            for _ in range(2):
                try:
                    payload = [{"query": ip, "fields": "status,query,country,countryCode"} for ip in ips]
                    async with session.post("http://ip-api.com/batch", json=payload, timeout=5) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            for item in data:
                                if item.get("status") == "success":
                                    results[item.get("query")] = f"{cls._get_flag_emoji(item.get('countryCode'))} {item.get('country')}"
                            break # Успех
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
        
        # Deep Check
        latency = await cls.check_connection(parsed)
        
        if latency == -1: return False, "", 0, "Dead (Deep Check)"
        
        region = await cls.get_region(parsed["host"], session)
        return True, region, latency, "OK"
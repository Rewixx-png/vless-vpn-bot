import re
import time
import asyncio
import aiohttp
import base64
import json
import socket
import ssl
from urllib.parse import urlparse, parse_qs
from typing import Optional, Tuple, Dict

class VlessChecker:
    @staticmethod
    def _get_flag_emoji(country_code: str) -> str:
        if not country_code or len(country_code) != 2:
            return "🌍"
        return "".join(chr(ord(c.upper()) + 127397) for c in country_code)

    @staticmethod
    def parse_config(config_url: str) -> Optional[Dict[str, str]]:
        config_url = config_url.strip()
        try:
            # --- VMESS ---
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
                    "security": data.get("tls", ""),
                    "sni": data.get("sni", "") or data.get("host", ""),
                    "path": data.get("path", "/"),
                    "full_url": config_url
                }

            # --- VLESS / TROJAN ---
            elif config_url.startswith("vless://") or config_url.startswith("trojan://"):
                parsed = urlparse(config_url)
                params = parse_qs(parsed.query)
                
                host = parsed.hostname
                port = parsed.port
                
                if not host or not port:
                    return None
                
                protocol = "vless" if config_url.startswith("vless://") else "trojan"
                security = params.get("security", [""])[0]
                sni = params.get("sni", [""])[0]
                if not sni:
                    sni = params.get("host", [""])[0]
                
                path = params.get("path", ["/"])[0]
                
                return {
                    "host": host,
                    "port": port,
                    "protocol": protocol,
                    "security": security,
                    "sni": sni,
                    "path": path,
                    "full_url": config_url
                }
            return None
        except Exception:
            return None

    @classmethod
    async def check_connection(cls, config_data: Dict) -> int:
        """
        Строгая проверка.
        """
        host = config_data["host"]
        port = config_data["port"]
        security = config_data.get("security", "")
        sni = config_data.get("sni", "")
        path = config_data.get("path", "/")
        
        start_time = time.monotonic()

        # 1. DNS Check (Быстро)
        if not re.match(r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$", host):
            try:
                await asyncio.wait_for(
                    asyncio.get_running_loop().getaddrinfo(host, port), 
                    timeout=1.0
                )
            except:
                return -1

        reader = None
        writer = None
        
        # Настройка SSL
        ssl_ctx = None
        target_server_name = sni if sni else host

        if security in ["tls", "reality", "auto"] or port == 443:
            ssl_ctx = ssl.create_default_context()
            ssl_ctx.check_hostname = False
            ssl_ctx.verify_mode = ssl.CERT_NONE
            ssl_ctx.set_alpn_protocols(["h2", "http/1.1"])

        try:
            # === ЭТАП 1: ПОДКЛЮЧЕНИЕ (ЖЕСТКИЙ ТАЙМАУТ) ===
            # Если тут будет Timeout -> значит сервер МЕРТВ
            try:
                if ssl_ctx:
                    # SSL Connect
                    reader, writer = await asyncio.wait_for(
                        asyncio.open_connection(host, port, ssl=ssl_ctx, server_hostname=target_server_name),
                        timeout=1.5 # 1.5 сек на хендшейк. Дольше - в мусорку.
                    )
                else:
                    # TCP Connect
                    reader, writer = await asyncio.wait_for(
                        asyncio.open_connection(host, port),
                        timeout=1.5
                    )
            except (asyncio.TimeoutError, ConnectionRefusedError, OSError, ssl.SSLError):
                # Сервер не ответил за 1.5 сек -> МЕРТВ
                return -1

            # === ЭТАП 2: ОТПРАВКА ДАННЫХ ===
            # Если мы тут - порт открыт и SSL (если был) прошел.
            
            request = (
                f"GET {path} HTTP/1.1\r\n"
                f"Host: {target_server_name}\r\n"
                f"User-Agent: Mozilla/5.0\r\n"
                f"Connection: close\r\n\r\n"
            )
            
            writer.write(request.encode())
            await writer.drain()
            
            # === ЭТАП 3: ЧТЕНИЕ (LOOSE TIMEOUT) ===
            # Здесь логика другая. Если сервер молчит - это ХОРОШО (для VLESS).
            # Если сервер закрывает соединение (EOF) - это ТОЖЕ ХОРОШО (значит он нас услышал).
            # Плохо только если ConnectionReset (RST).
            
            try:
                data = await asyncio.wait_for(reader.read(1024), timeout=1.5)
                
                # Любой ответ (даже пустой, даже 400 Bad Request) означает, что сервер жив
                # и мы смогли с ним поговорить.
                
                # Если 502/503 - это ошибки шлюза, значит бэкенда нет
                if data:
                    resp = data.decode(errors='ignore')
                    if "502 Bad Gateway" in resp or "503 Service Unavailable" in resp:
                        return -1

            except asyncio.TimeoutError:
                # Таймаут НА ЧТЕНИИ = ЖИВ. Сервер принял данные и держит канал.
                pass
            except ConnectionResetError:
                # Сервер жестко сбросил -> скорее всего мертв или забанен
                return -1
            
            end_time = time.monotonic()
            return int((end_time - start_time) * 1000)

        except Exception:
            return -1
        finally:
            if writer:
                try:
                    writer.close()
                    await writer.wait_closed()
                except:
                    pass

    @classmethod
    async def get_region(cls, host: str) -> str:
        api_url = f"http://ip-api.com/json/{host}?fields=status,country,countryCode"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(api_url, timeout=2) as response:
                    if response.status == 200:
                        data = await response.json()
                        if data.get("status") == "success":
                            code = data.get("countryCode", "")
                            name = data.get("country", "Unknown")
                            flag = cls._get_flag_emoji(code)
                            return f"{flag} {name}"
        except Exception:
            pass
        return "🌍 Unknown"

    @classmethod
    async def process_subscription(cls, config_url: str) -> Tuple[bool, str, int, str]:
        parsed = cls.parse_config(config_url)
        if not parsed:
            return False, "", 0, "Некорректный формат."

        latency = await cls.check_connection(parsed)
        
        if latency == -1:
            return False, "", 0, f"Недоступен."

        region = await cls.get_region(parsed["host"])
        return True, region, latency, "OK"
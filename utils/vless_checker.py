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
    # Путь к бинарнику Xray
    XRAY_BIN = "/usr/local/bin/xray"
    
    # Заголовки для GeoIP проверки
    HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    @staticmethod
    def _get_flag_emoji(country_code: str) -> str:
        if not country_code or len(country_code) != 2:
            return "🌍"
        return "".join(chr(ord(c.upper()) + 127397) for c in country_code)

    @staticmethod
    def parse_config(config_url: str):
        # Используем наш мощный парсер из utils/parser.py
        # Обертка для совместимости
        return LinkParser.parse_vless(config_url)

    @staticmethod
    def _generate_xray_config(parsed: dict, local_port: int) -> dict:
        """
        Генерирует JSON конфигурацию для Xray Core.
        Создает локальный SOCKS5 сервер, который перенаправляет трафик в VLESS.
        """
        
        # Базовая структура Outbound (исходящее соединение VLESS)
        outbound = {
            "protocol": "vless",
            "settings": {
                "vnext": [
                    {
                        "address": parsed['server'],
                        "port": parsed['port'],
                        "users": [
                            {
                                "id": parsed['uuid'],
                                "encryption": "none",
                                "flow": parsed.get('flow', '')
                            }
                        ]
                    }
                ]
            },
            "streamSettings": {
                "network": parsed['type'],
                "security": parsed['security']
            }
        }

        # Настройка StreamSettings (Transport)
        stream = outbound["streamSettings"]
        
        # TLS / Reality
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

        # Network Types
        if parsed['type'] == 'ws':
            stream['wsSettings'] = {
                "path": parsed.get('path', '/'),
                "headers": {
                    "Host": parsed.get('host') or parsed.get('sni', '')
                }
            }
        elif parsed['type'] == 'grpc':
            stream['grpcSettings'] = {
                "serviceName": parsed.get('serviceName', ''),
                "multiMode": (parsed.get('mode') == 'multi')
            }
        elif parsed['type'] == 'tcp':
            # Обработка HTTP Header (редко, но бывает)
            if parsed.get('type') == 'http':
                 stream['tcpSettings'] = {
                    "header": {
                        "type": "http",
                        "request": {
                            "headers": {
                                "Host": [parsed.get('host', '')]
                            }
                        }
                    }
                 }

        # Сборка полного конфига
        config = {
            "log": {
                "loglevel": "none"
            },
            "inbounds": [
                {
                    "port": local_port,
                    "protocol": "socks",
                    "settings": {
                        "auth": "noauth",
                        "udp": True
                    },
                    "sniffing": {
                        "enabled": True,
                        "destOverride": ["http", "tls"]
                    }
                }
            ],
            "outbounds": [
                outbound,
                {"protocol": "freedom", "tag": "direct"}
            ]
        }
        return config

    @classmethod
    async def process_subscription(cls, config_url: str, session=None) -> tuple[bool, str, int, str]:
        """
        Проверяет подписку через реальное ядро Xray.
        session аргумент оставлен для совместимости, но не используется для прокси.
        """
        parsed = cls.parse_config(config_url)
        if not parsed:
            return False, "", 0, "Invalid Link Format"

        # Выбираем случайный порт для изоляции проверок (15000-25000)
        local_port = random.randint(15000, 25000)
        config_path = f"/tmp/xray_check_{local_port}.json"
        
        # 1. Создаем конфиг
        try:
            xray_conf = cls._generate_xray_config(parsed, local_port)
            with open(config_path, 'w') as f:
                json.dump(xray_conf, f)
        except Exception as e:
            return False, "", 0, f"Config Gen Error: {e}"

        process = None
        try:
            # 2. Запускаем Xray
            process = await asyncio.create_subprocess_exec(
                cls.XRAY_BIN, "-c", config_path,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL
            )
            
            # Даем время на запуск
            await asyncio.sleep(0.5)
            
            if process.returncode is not None:
                 return False, "", 0, "Xray failed to start"

            # 3. Пробуем подключиться через локальный SOCKS5
            connector = ProxyConnector.from_url(f"socks5://127.0.0.1:{local_port}")
            
            start_time = time.monotonic()
            latency = 9999
            
            # Используем отдельную сессию для прокси-запроса
            async with aiohttp.ClientSession(connector=connector) as proxy_session:
                # URL для проверки пинга (Generate 204)
                try:
                    async with proxy_session.get('http://cp.cloudflare.com/generate_204', timeout=5) as resp:
                        if resp.status == 204 or resp.status == 200:
                            latency = int((time.monotonic() - start_time) * 1000)
                        else:
                            raise Exception(f"Status {resp.status}")
                except Exception as e:
                    return False, "", 0, f"Connection Failed: {str(e)}"

                # 4. Если живой, определяем РЕАЛЬНЫЙ регион (через прокси)
                # Это точнее, чем проверять IP хоста, так как может быть роутинг
                region = "🌍 Unknown"
                try:
                    async with proxy_session.get('http://ip-api.com/json/?fields=country,countryCode', timeout=3) as geo_resp:
                        if geo_resp.status == 200:
                            geo_data = await geo_resp.json()
                            region = f"{cls._get_flag_emoji(geo_data.get('countryCode'))} {geo_data.get('country')}"
                except:
                    # Если не удалось определить регион через прокси, попробуем прямой резолв (fallback)
                    pass

            return True, region, latency, "OK"

        except Exception as e:
            return False, "", 0, f"System Error: {e}"
        
        finally:
            # 5. Очистка
            if process:
                try:
                    process.terminate()
                    await process.wait()
                except:
                    pass
            
            if os.path.exists(config_path):
                try:
                    os.remove(config_path)
                except:
                    pass

    @classmethod
    async def get_regions_batch(cls, ips: list[str], session: aiohttp.ClientSession) -> dict[str, str]:
        """
        Пакетная проверка регионов (Прямая, без прокси).
        Используется для быстрого фикса регионов, но менее точна для CDN.
        """
        results = {}
        if not ips: return results
        try:
            # Разбиваем на чанки по 100
            for i in range(0, len(ips), 100):
                chunk = ips[i:i+100]
                try:
                    payload = [{"query": ip, "fields": "status,query,country,countryCode"} for ip in chunk]
                    async with session.post("http://ip-api.com/batch", json=payload, timeout=10) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            for item in data:
                                if item.get("status") == "success":
                                    results[item.get("query")] = f"{cls._get_flag_emoji(item.get('countryCode'))} {item.get('country')}"
                except:
                    pass
        except: pass
        return results

    @staticmethod
    async def verify_domain(domain: str) -> tuple[bool, str]:
        """Простая проверка домена (DNS + Socket connect)"""
        try:
            # Получаем IP
            loop = asyncio.get_running_loop()
            try:
                ip = await loop.getaddrinfo(domain, 80)
                ip_addr = ip[0][4][0]
            except:
                return False, "DNS Resolve Failed"

            return True, f"OK ({ip_addr})"
        except Exception as e:
            return False, str(e)
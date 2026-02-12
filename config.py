from pydantic_settings import BaseSettings
from typing import List
from pydantic import SecretStr

class Settings(BaseSettings):
    BOT_TOKEN: SecretStr
    ADMIN_IDS: List[int]
    DB_URL: str
    CRYPTO_BOT_TOKEN: SecretStr
    
    # Публичный IP сервера
    PUBLIC_IP: str = "108.165.164.160"
    
    # Порт веб-сервера подписок
    # ВАЖНО: Используйте 2082 для Cloudflare (HTTP), так как 2096 требует SSL (HTTPS)
    # Порты Cloudflare HTTP: 80, 8080, 2052, 2082, 2095
    # Порты Cloudflare HTTPS: 443, 2053, 2083, 2096
    WEB_PORT: int = 2082
    
    # Если вы хотите принудительно использовать HTTPS ссылки при работе через HTTP порт (за Cloudflare)
    # установите этот домен (например: vpn.example.com)
    public_domain: str | None = None

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

config = Settings()
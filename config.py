from pydantic_settings import BaseSettings
from typing import List
from pydantic import SecretStr

class Settings(BaseSettings):
    BOT_TOKEN: SecretStr
    ADMIN_IDS: List[int]
    DB_URL: str
    CRYPTO_BOT_TOKEN: SecretStr
    
    # URL подключения к Redis (для Celery)
    # Если Redis на другом сервере или с паролем, измените этот параметр
    REDIS_URL: str = "redis://localhost:6379/0"

    # Публичный IP сервера
    PUBLIC_IP: str = "108.165.164.160"
    
    # Порт веб-сервера подписок
    WEB_PORT: int = 2082
    
    # Если вы хотите принудительно использовать HTTPS ссылки при работе через HTTP порт (за Cloudflare)
    # установите этот домен (например: vpn.example.com)
    public_domain: str | None = None

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

config = Settings()
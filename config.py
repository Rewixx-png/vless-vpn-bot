from pydantic_settings import BaseSettings
from typing import List
from pydantic import SecretStr

class Settings(BaseSettings):
    BOT_TOKEN: SecretStr
    ADMIN_IDS: List[int]
    DB_URL: str
    CRYPTO_BOT_TOKEN: SecretStr
    
    # URL подключения к Redis (для Celery)
    REDIS_URL: str = "redis://localhost:6379/0"

    # Публичный IP сервера
    PUBLIC_IP: str = "108.165.164.160"
    
    # Порт веб-сервера подписок (для пользователей)
    WEB_PORT: int = 2082
    
    # Порт внутреннего микросервиса чекера (Localhost only)
    CHECKER_PORT: int = 8081
    CHECKER_URL: str = "http://127.0.0.1:8081"
    
    # Если вы хотите принудительно использовать HTTPS ссылки при работе через HTTP порт (за Cloudflare)
    public_domain: str | None = None

    # Дополнительная подписка, которая будет подмешана к выдаче
    EXTERNAL_SUB_URL: str | None = None

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

config = Settings()

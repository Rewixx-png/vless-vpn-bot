from pydantic_settings import BaseSettings
from typing import List
from pydantic import SecretStr

class Settings(BaseSettings):
    BOT_TOKEN: SecretStr
    ADMIN_IDS: List[int]
    DB_URL: str
    CRYPTO_BOT_TOKEN: SecretStr
    
    # Новые настройки для подписки
    PUBLIC_IP: str = "127.0.0.1"
    WEB_PORT: int = 8000

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

config = Settings()
from pydantic_settings import BaseSettings
from typing import List
from pydantic import SecretStr

class Settings(BaseSettings):
    BOT_TOKEN: SecretStr
    ADMIN_IDS: List[int]
    DB_URL: str
    CRYPTO_BOT_TOKEN: SecretStr
    
    REDIS_URL: str = "redis://localhost:6379/0"

    PUBLIC_IP: str = "108.165.164.160"
    
    WEB_PORT: int = 2082
    
    CHECKER_PORT: int = 8081
    CHECKER_URL: str = "http://127.0.0.1:8081"
    
    public_domain: str | None = None

    EXTERNAL_SUB_URL: str | None = None
    
    DNS_CACHE_TTL: int = 86400

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

config = Settings()

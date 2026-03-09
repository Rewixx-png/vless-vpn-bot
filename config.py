from pydantic_settings import BaseSettings
from typing import List
from pydantic import SecretStr

class Settings(BaseSettings):
    BOT_TOKEN: SecretStr
    ADMIN_IDS: List[int]
    DB_URL: str
    CRYPTO_BOT_TOKEN: SecretStr

    REDIS_URL: str = "redis://localhost:6379/0"
    PUBLIC_IP: str = "127.0.0.1"
    WEB_PORT: int = 2082

    CHECKER_PORT: int = 8081
    CHECKER_URL: str = "http://127.0.0.1:8081"

    REPORT_CHAT_ID: int = -1003724265330

    VIDEO_SOURCE_URL: str = "https://github.com/Rewixx-png/rew-host-assets/raw/main/%D0%9D%D0%BE%D0%B2%D1%8B%D0%B9%20%D0%BF%D1%80%D0%BE%D0%BA%D1%82%20114%20%5B33803A3%5D.mp4"

    CHECKER_TIMEOUT: float = 25.0
    CONNECTIVITY_TIMEOUT: float = 8.0
    SPEED_TEST_TIMEOUT: float = 5.0
    BATCH_TIMEOUT_PER_ITEM: float = 60.0

    MIN_SPEED_MBPS: float = 25.0
    MEMORY_LIMIT_MB: int = 450
    MAX_WORKERS: int = 80
    MIN_WORKERS: int = 10

    MEMORY_CHECK_INTERVAL: int = 60
    COLLECTOR_INTERVAL: int = 1800
    STABILITY_CHECK_INTERVAL: int = 1800
    
    RECHECK_TIMEOUT_PER_PASS: int = 480
    
    DB_POOL_RECYCLE: int = 3600
    
    CACHE_TTL: int = 300
    DNS_CACHE_TTL: int = 300
    
    GEOIP_CACHE_TTL: int = 86400

    public_domain: str | None = None
    EXTERNAL_SUB_URL: str | None = None

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

config = Settings()

from pydantic_settings import BaseSettings
from typing import List
from pydantic import SecretStr

class Settings(BaseSettings):
    # Core settings
    BOT_TOKEN: SecretStr
    ADMIN_IDS: List[int]
    DB_URL: str
    CRYPTO_BOT_TOKEN: SecretStr

    # Infrastructure
    REDIS_URL: str = "redis://localhost:6379/0"
    PUBLIC_IP: str = "108.165.164.160"
    WEB_PORT: int = 2082

    # Checker service
    CHECKER_PORT: int = 8081
    CHECKER_URL: str = "http://127.0.0.1:8081"

    # Monitoring and reporting
    REPORT_CHAT_ID: int = -1003724265330  # For admin reports

    # Timeouts (seconds)
    CHECKER_TIMEOUT: float = 25.0
    CONNECTIVITY_TIMEOUT: float = 8.0
    SPEED_TEST_TIMEOUT: float = 5.0
    BATCH_TIMEOUT_PER_ITEM: float = 60.0

    # Limits
    MIN_SPEED_MBPS: float = 25.0
    MEMORY_LIMIT_MB: int = 450
    MAX_WORKERS: int = 80
    MIN_WORKERS: int = 10

    # Intervals (seconds)
    MEMORY_CHECK_INTERVAL: int = 60
    COLLECTOR_INTERVAL: int = 1800  # 30 minutes
    STABILITY_CHECK_INTERVAL: int = 1800
    
    # Recheck timeouts
    RECHECK_TIMEOUT_PER_PASS: int = 480  # 8 minutes per pass

    # GeoIP
    DNS_CACHE_TTL: int = 86400

    # Optional
    public_domain: str | None = None
    EXTERNAL_SUB_URL: str | None = None

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

config = Settings()

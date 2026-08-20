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

    CHECKER_PORT: int = 8082
    CHECKER_URL: str = "http://127.0.0.1:8082"

    REPORT_CHAT_ID: int | None = None

    VIDEO_SOURCE_URL: str | None = None

    CHECKER_TIMEOUT: float = 25.0
    CONNECTIVITY_TIMEOUT: float = 8.0
    SPEED_TEST_TIMEOUT: float = 10.0
    BATCH_TIMEOUT_PER_ITEM: float = 60.0

    MAX_CONFIGS_PER_REGION: int = 300

    MIN_SPEED_MBPS: float = 25.0
    MEMORY_LIMIT_MB: int = 450
    MAX_WORKERS: int = 80
    MIN_WORKERS: int = 10

    MEMORY_CHECK_INTERVAL: int = 60
    COLLECTOR_INTERVAL: int = 3600
    STABILITY_CHECK_INTERVAL: int = 1800

    RECHECK_TIMEOUT_PER_PASS: int = 480

    DB_POOL_RECYCLE: int = 3600

    CACHE_TTL: int = 300
    DNS_CACHE_TTL: int = 300

    GEOIP_CACHE_TTL: int = 86400

    public_domain: str | None = None
    EXTERNAL_SUB_URL: str | None = None
    RU_PAID_PROXIES: str | None = None
    CHECKER_USE_RU_PROXY_CHAIN: bool = False

    RU_CHECKER_TOKEN: str | None = None
    RU_CHECKER_BATCH_SIZE: int = 60
    RU_CHECKER_INTERVAL_SECONDS: int = 30
    RU_CHECKER_CONNECT_TIMEOUT: float = 6.0
    RU_CHECKER_CONCURRENCY: int = 12
    RU_CHECKER_VPN_CONCURRENCY: int = 4
    RU_CHECKER_URL_TEST: str = "http://cp.cloudflare.com/generate_204"

    STRICT_RKN_FILTER: bool = False
    BLOCKED_SNIS: List[str] =[
        "discord.com", "discord.gg", "rutracker.org", 
        "googlevideo.com", "youtube.com", "ytimg.com",
        "instagram.com", "facebook.com", "twitter.com", "x.com",
        "t.co", "linkedin.com", "netflix.com"
    ]

    # Payment info (shown to users)
    PAYMENT_PHONE: str = ""
    PAYMENT_CARD_RAIFFEISEN: str = ""

    BACKUP_ZIP_PASSWORD: str = "changeme"

    # Support contacts
    SUPPORT_USERNAME: str = "@RewiX_X"
    FEEDBACK_BOT_USERNAME: str = "@RewFeedBackBot"


    TELEGRAM_API_URL: str = "https://api.telegram.org"
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

config = Settings()

from aiogram import Bot
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.telegram import TelegramAPIServer

def make_bot() -> Bot:
    api = TelegramAPIServer(
        base=config.TELEGRAM_API_URL + "/bot{token}/{method}",
        file=config.TELEGRAM_API_URL + "/file/bot{token}/{path}",
    )
    return Bot(token=config.BOT_TOKEN.get_secret_value(), session=AiohttpSession(api=api))


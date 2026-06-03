import logging
import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import text
from sqlalchemy.pool import NullPool
from config import config
from database.models import Base

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("Database")

engine = create_async_engine(
    config.DB_URL, 
    echo=False,
    pool_size=30,
    max_overflow=20,
    pool_timeout=30,
    pool_recycle=config.DB_POOL_RECYCLE,
    pool_pre_ping=True,
    pool_use_lifo=True
)

async_session_factory = sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)

async def init_db():
    logger.info("⏳ Connecting to database...")
    
    try:
        async with engine.begin() as conn:
            logger.info("🛠 Checking tables schema...")
            await conn.run_sync(Base.metadata.create_all)
        
        logger.info("✅ Tables schema checked.")

        async with engine.begin() as conn:
            logger.info("🔄 Checking migrations...")
            
            migrations =[
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS country_filter TEXT DEFAULT NULL",
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS subscription_limit INTEGER DEFAULT 0",
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS tags_filter TEXT DEFAULT NULL",
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS language VARCHAR DEFAULT 'ru'",
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS use_fragment BOOLEAN DEFAULT FALSE",
                "ALTER TABLE subscriptions ADD COLUMN IF NOT EXISTS ai_available BOOLEAN DEFAULT FALSE",
                "ALTER TABLE subscriptions ADD COLUMN IF NOT EXISTS no_ads BOOLEAN DEFAULT FALSE",
                "ALTER TABLE subscriptions ADD COLUMN IF NOT EXISTS death_count INTEGER DEFAULT 0",
                "ALTER TABLE user_groups ADD COLUMN IF NOT EXISTS tags_filter TEXT DEFAULT NULL",
                "ALTER TABLE subscriptions ADD COLUMN IF NOT EXISTS stable_state INTEGER DEFAULT 0",
                "ALTER TABLE subscriptions ADD COLUMN IF NOT EXISTS stability_streak INTEGER DEFAULT 0",
                "ALTER TABLE subscriptions ADD COLUMN IF NOT EXISTS speed_mbps FLOAT DEFAULT 0.0",
                "ALTER TABLE subscriptions ADD COLUMN IF NOT EXISTS last_checked_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()",
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS protocol_filter VARCHAR DEFAULT NULL",
                "ALTER TABLE user_groups ADD COLUMN IF NOT EXISTS protocol_filter VARCHAR DEFAULT NULL",
                "ALTER TABLE subscriptions ADD COLUMN IF NOT EXISTS ru_status VARCHAR DEFAULT 'unknown'",
                "ALTER TABLE subscriptions ADD COLUMN IF NOT EXISTS ru_latency_ms INTEGER DEFAULT NULL",
                "ALTER TABLE subscriptions ADD COLUMN IF NOT EXISTS ru_checked_at TIMESTAMP WITH TIME ZONE DEFAULT NULL",
                "ALTER TABLE subscriptions ADD COLUMN IF NOT EXISTS ru_error TEXT DEFAULT NULL",
                "ALTER TABLE subscriptions ADD COLUMN IF NOT EXISTS ru_success_count INTEGER DEFAULT 0",
                "ALTER TABLE subscriptions ADD COLUMN IF NOT EXISTS ru_fail_count INTEGER DEFAULT 0",
            ]

            for sql in migrations:
                try:
                    await conn.execute(text(sql))
                except Exception as e:
                    if "duplicate column" not in str(e).lower() and "exists" not in str(e).lower():
                         logger.warning(f"⚠️ Migration warning: {e}")

            logger.info("✅ Migrations completed.")

        async with engine.connect() as conn:
            logger.info("🔄 Checking concurrent index migrations...")
            concurrent_migrations = [
                "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_subs_is_active ON subscriptions (is_active)",
                "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_subs_speed_mbps ON subscriptions (speed_mbps)",
                "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_subs_last_checked ON subscriptions (last_checked_at)",
                "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_subs_death_count ON subscriptions (death_count)",
                "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_subs_ru_status ON subscriptions (ru_status)",
                "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_subs_ru_checked_at ON subscriptions (ru_checked_at)",
            ]
            for sql in concurrent_migrations:
                try:
                    await conn.execute(text(sql))
                except Exception as e:
                    if "exists" not in str(e).lower():
                        logger.warning(f"⚠️ Concurrent migration warning: {e}")
            logger.info("✅ Concurrent index migrations completed.")

    except Exception as e:
        logger.critical(f"❌ CRITICAL DATABASE ERROR: {e}")
        raise e

async def get_session() -> AsyncSession:
    async with async_session_factory() as session:
        yield session

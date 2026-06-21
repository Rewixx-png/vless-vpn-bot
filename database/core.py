import logging
from sqlalchemy import text
from sqlalchemy.engine.url import make_url
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

from config import config
from database.models import Base

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("Database")

_DB_BACKEND = make_url(config.DB_URL).get_backend_name()
IS_SQLITE = _DB_BACKEND.startswith("sqlite")

if IS_SQLITE:
    engine = create_async_engine(
        config.DB_URL,
        echo=False,
        poolclass=NullPool,
        connect_args={"timeout": 30},
    )
else:
    engine = create_async_engine(
        config.DB_URL,
        echo=False,
        pool_size=20,
        max_overflow=30,
        pool_timeout=30,
        pool_recycle=config.DB_POOL_RECYCLE,
        pool_pre_ping=True,
        pool_use_lifo=True,
    )

async_session_factory = sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)

_POSTGRES_MIGRATIONS = [
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
]

_SQLITE_MIGRATIONS = [
    ("users", "country_filter", "TEXT DEFAULT NULL"),
    ("users", "subscription_limit", "INTEGER DEFAULT 0"),
    ("users", "tags_filter", "TEXT DEFAULT NULL"),
    ("users", "language", "VARCHAR DEFAULT 'ru'"),
    ("users", "use_fragment", "BOOLEAN DEFAULT 0"),
    ("subscriptions", "ai_available", "BOOLEAN DEFAULT 0"),
    ("subscriptions", "no_ads", "BOOLEAN DEFAULT 0"),
    ("subscriptions", "death_count", "INTEGER DEFAULT 0"),
    ("user_groups", "tags_filter", "TEXT DEFAULT NULL"),
    ("subscriptions", "stable_state", "INTEGER DEFAULT 0"),
    ("subscriptions", "stability_streak", "INTEGER DEFAULT 0"),
    ("subscriptions", "speed_mbps", "FLOAT DEFAULT 0.0"),
    (
        "subscriptions",
        "last_checked_at",
        "DATETIME DEFAULT CURRENT_TIMESTAMP",
    ),
]


async def _apply_sqlite_migrations(conn):
    for table_name, column_name, column_def in _SQLITE_MIGRATIONS:
        try:
            info_result = await conn.execute(text(f'PRAGMA table_info("{table_name}")'))
            rows = info_result.fetchall()
            existing_columns = {str(row[1]) for row in rows if len(row) > 1}
            if column_name in existing_columns:
                continue

            await conn.execute(
                text(
                    f'ALTER TABLE "{table_name}" '
                    f'ADD COLUMN "{column_name}" {column_def}'
                )
            )
        except Exception as e:
            logger.warning(
                "⚠️ SQLite migration warning (%s.%s): %s",
                table_name,
                column_name,
                e,
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

            if IS_SQLITE:
                await _apply_sqlite_migrations(conn)
            else:
                for sql in _POSTGRES_MIGRATIONS:
                    try:
                        await conn.execute(text(sql))
                    except Exception as e:
                        if (
                            "duplicate column" not in str(e).lower()
                            and "exists" not in str(e).lower()
                        ):
                            logger.warning(f"⚠️ Migration warning: {e}")

            logger.info("✅ Migrations completed.")

    except Exception as e:
        logger.critical(f"❌ CRITICAL DATABASE ERROR: {e}")
        raise


async def get_session() -> AsyncSession:
    async with async_session_factory() as session:
        yield session

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy import text
from sqlalchemy.pool import NullPool
from config import config
from database.models import Base

engine = create_async_engine(
    config.DB_URL, 
    echo=False,
    poolclass=NullPool
)

async_session_factory = async_sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)

async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

        try:
            await conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS country_filter TEXT DEFAULT NULL"))
            await conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS subscription_limit INTEGER DEFAULT 0"))
            
            await conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS tags_filter TEXT DEFAULT NULL"))
            
            await conn.execute(text("ALTER TABLE subscriptions ADD COLUMN IF NOT EXISTS ai_available BOOLEAN DEFAULT FALSE"))
        except Exception as e:
            print(f"Migration warning: {e}")

async def get_session() -> AsyncSession:
    async with async_session_factory() as session:
        yield session
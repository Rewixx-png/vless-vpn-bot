from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy import text
from config import config
from database.models import Base

engine = create_async_engine(config.DB_URL, echo=False)

async_session_factory = async_sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)

async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

        try:
            await conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS country_filter TEXT DEFAULT NULL"))
            await conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS subscription_limit INTEGER DEFAULT 0"))
            
            # Миграция для SystemConfig (если таблицы нет, она создастся create_all, но на всякий случай)
            # В данном контексте create_all выше уже создаст таблицу system_config, так как она добавлена в models.py
            pass
        except Exception as e:
            print(f"⚠️ Migration warning: {e}")

async def get_session() -> AsyncSession:
    async with async_session_factory() as session:
        yield session
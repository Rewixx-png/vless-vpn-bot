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
        # Создаем таблицы, если их нет
        await conn.run_sync(Base.metadata.create_all)

        # --- AUTO-MIGRATION (HOTFIX) ---
        # Ручные миграции для добавления колонок без потери данных
        try:
            # 1. Добавляем country_filter
            await conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS country_filter TEXT DEFAULT NULL"))
            
            # 2. Добавляем subscription_limit (0 = все)
            await conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS subscription_limit INTEGER DEFAULT 0"))
            
        except Exception as e:
            # Игнорируем ошибку, если колонка уже есть
            print(f"⚠️ Migration warning: {e}")

async def get_session() -> AsyncSession:
    async with async_session_factory() as session:
        yield session
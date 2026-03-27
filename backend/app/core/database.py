from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings

# Railway Postgres gives postgresql://, asyncpg needs postgresql+asyncpg://
_db_url = settings.DATABASE_URL
if _db_url.startswith("postgresql://"):
    _db_url = _db_url.replace("postgresql://", "postgresql+asyncpg://", 1)
elif not _db_url.startswith("postgresql+asyncpg://"):
    _db_url = f"postgresql+asyncpg://{_db_url}"

engine = create_async_engine(
    _db_url,
    echo=False,
    pool_size=10,
    max_overflow=20,
)

async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db():
    async with async_session() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise

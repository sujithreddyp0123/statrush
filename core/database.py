import os
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from core.config import get_settings

cfg = get_settings()

def _fix_db_url(url: str) -> str:
    if not url:
        return url
    url = url.replace("postgres://", "postgresql+asyncpg://")
    url = url.replace("postgresql://", "postgresql+asyncpg://")
    if "postgresql+asyncpg+asyncpg" in url:
        url = url.replace("postgresql+asyncpg+asyncpg", "postgresql+asyncpg")
    return url

_db_url = _fix_db_url(cfg.DATABASE_URL)

_is_sqlite = _db_url.startswith("sqlite")
engine = create_async_engine(
    _db_url,
    pool_pre_ping=True,
    echo=cfg.ENV == "dev",
    **({} if _is_sqlite else {
        "pool_size":    cfg.DB_POOL_SIZE,
        "max_overflow": cfg.DB_MAX_OVERFLOW,
        "pool_timeout": cfg.DB_POOL_TIMEOUT,
    })
)

SessionFactory = async_sessionmaker(
    engine, class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)

class Base(DeclarativeBase):
    pass

async def get_db():
    async with SessionFactory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()

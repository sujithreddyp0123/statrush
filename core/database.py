from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase
from core.config import get_settings

cfg = get_settings()

_is_sqlite = cfg.DATABASE_URL.startswith("sqlite")
engine = create_async_engine(
    cfg.DATABASE_URL,
    echo=False,
    **({} if _is_sqlite else {
        "pool_size":    cfg.DB_POOL_SIZE,
        "max_overflow": cfg.DB_MAX_OVERFLOW,
        "pool_timeout": cfg.DB_POOL_TIMEOUT,
    })
)

SessionFactory = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncSession:
    async with SessionFactory() as session:
        yield session

from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings

# Convert sync DATABASE_URL to async
# We use make_url to parse the connection string and safely replace the driver
sync_url = make_url(settings.DATABASE_URL)
async_database_url = sync_url.set(drivername="postgresql+asyncpg")

engine = create_async_engine(
    async_database_url,
    echo=False,
    future=True,
)
async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


class Base(DeclarativeBase):
    pass


async def get_db():
    """Get async database session for FastAPI dependency injection."""
    async with async_session_factory() as session:
        yield session

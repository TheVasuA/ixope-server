from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import text
from .config import settings

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,
    pool_size=20,
    max_overflow=10,
    pool_pre_ping=True,
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    pass


async def get_db():
    """Dependency: yields an async DB session."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


async def init_db():
    """Create all tables (dev only — use Alembic in prod).

    Also runs lightweight, idempotent column additions for tables that gained
    columns after they were first created, since create_all() only creates
    missing tables and never alters existing ones.
    """
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await _apply_lightweight_migrations(conn)


async def _apply_lightweight_migrations(conn):
    """Add per-device credential columns to existing 'devices' tables.

    Uses Postgres 'ADD COLUMN IF NOT EXISTS' so it's safe to run on every
    startup and on databases created before these columns existed.
    """
    statements = [
        "ALTER TABLE devices ADD COLUMN IF NOT EXISTS username VARCHAR(100)",
        "ALTER TABLE devices ADD COLUMN IF NOT EXISTS hashed_password VARCHAR(255)",
        "ALTER TABLE devices ADD COLUMN IF NOT EXISTS is_active BOOLEAN DEFAULT TRUE",
        "CREATE UNIQUE INDEX IF NOT EXISTS ix_devices_username ON devices (username)",
    ]
    for stmt in statements:
        try:
            await conn.execute(text(stmt))
        except Exception:
            # Non-Postgres backends or races — safe to ignore; models still work.
            pass

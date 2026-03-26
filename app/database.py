"""Async SQLAlchemy engine, session factory, and database utilities."""

from collections.abc import AsyncGenerator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import declarative_base

from app.config import settings
from app.utils.logger import logger

Base = declarative_base()


def _normalize_async_database_url(url: str) -> str:
    """Ensure the URL uses the asyncpg driver for SQLAlchemy async."""
    stripped = url.strip()
    if not stripped:
        return stripped
    if stripped.startswith("postgresql+asyncpg://"):
        return stripped
    if stripped.startswith("postgresql://"):
        return stripped.replace("postgresql://", "postgresql+asyncpg://", 1)
    return stripped


def _create_engine() -> AsyncEngine | None:
    """Build the async engine, or return None if DATABASE_URL is unset."""
    url = _normalize_async_database_url(settings.database_url)
    if not url:
        return None
    return create_async_engine(
        url,
        pool_pre_ping=True,
        echo=settings.app_env.lower() == "development",
    )


async_engine: AsyncEngine | None = _create_engine()

AsyncSessionLocal: async_sessionmaker[AsyncSession] | None
if async_engine is not None:
    AsyncSessionLocal = async_sessionmaker(
        async_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )
else:
    AsyncSessionLocal = None


def _require_session_factory() -> async_sessionmaker[AsyncSession]:
    if AsyncSessionLocal is None:
        msg = "DATABASE_URL is not configured; cannot create a database session"
        raise RuntimeError(msg)
    return AsyncSessionLocal


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency that yields an async database session."""
    factory = _require_session_factory()
    async with factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


async def init_db() -> None:
    """
    Verify database connectivity.

    Schema changes are applied only via Alembic migrations, not ``create_all``.
    """
    if async_engine is None:
        raise ValueError("DATABASE_URL is not set; cannot initialize the database")

    if not await check_database_connection():
        msg = "Database connection failed"
        raise RuntimeError(msg)

    logger.info("Database connection verified")


async def check_database_connection() -> bool:
    """Return True if a simple query succeeds."""
    if async_engine is None:
        return False
    try:
        async with async_engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False

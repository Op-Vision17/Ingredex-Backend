"""Alembic migration environment — async SQLAlchemy (asyncpg) for online migrations."""

from __future__ import annotations

import asyncio
import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import create_async_engine

from app.config import settings
from app.database import Base

# Import ORM package so all models register on `Base.metadata` for autogenerate.
# Includes User, OTP, ProductScan, RefreshToken (see app.models.__init__).
import app.models  # noqa: F401

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def get_database_url() -> str:
    """Resolve DB URL: prefer ``DATABASE_URL`` env, then ``Settings`` (from ``.env``)."""
    env_url = os.environ.get("DATABASE_URL", "").strip()
    if env_url:
        return env_url
    return settings.database_url.strip()


def _normalize_async_url(url: str) -> str:
    """Ensure asyncpg driver for online async migrations."""
    if not url:
        return url
    if url.startswith("postgresql+asyncpg://"):
        return url
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return url


def _normalize_sync_url(url: str) -> str:
    """Use psycopg2 for offline SQL rendering (no async connection)."""
    if not url:
        return url
    if "+asyncpg" in url:
        return url.replace("+asyncpg", "+psycopg2")
    return url


def do_run_migrations(connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Run migrations with an async engine (asyncpg)."""
    raw = get_database_url()
    if not raw:
        msg = "DATABASE_URL is not set; cannot run Alembic migrations."
        raise RuntimeError(msg)

    url = _normalize_async_url(raw)
    config.set_main_option("sqlalchemy.url", url)

    connectable = create_async_engine(url, poolclass=pool.NullPool)

    try:
        async with connectable.connect() as connection:
            await connection.run_sync(do_run_migrations)
    finally:
        await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    asyncio.run(run_async_migrations())


def run_migrations_offline() -> None:
    """Generate SQL without connecting (sync dialect URL)."""
    raw = get_database_url()
    if not raw:
        msg = "DATABASE_URL is not set; cannot run Alembic offline migrations."
        raise RuntimeError(msg)

    url = _normalize_sync_url(raw)
    config.set_main_option("sqlalchemy.url", url)

    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

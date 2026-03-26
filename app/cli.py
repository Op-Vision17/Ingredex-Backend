"""Poetry script entry points (``poetry run dev``, ``poetry run migrate``)."""

from __future__ import annotations

from pathlib import Path


def _alembic_ini() -> Path:
    return Path(__file__).resolve().parent.parent / "alembic.ini"


def dev() -> None:
    """Run uvicorn with auto-reload (development)."""
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )


def migrate() -> None:
    """Apply Alembic migrations to ``head`` (run from project root)."""
    from alembic import command
    from alembic.config import Config

    cfg = Config(str(_alembic_ini()))
    command.upgrade(cfg, "head")

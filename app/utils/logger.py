"""Structured logging with Loguru, file rotation, and per-request correlation IDs."""

import sys
from contextvars import ContextVar, Token
from pathlib import Path

from loguru import logger as _logger

# ---------------------------------------------------------------------------
# Request ID (correlation) — set by middleware for each HTTP request
# ---------------------------------------------------------------------------

request_id_ctx: ContextVar[str | None] = ContextVar("request_id", default=None)


def get_request_id() -> str:
    """Return the current request ID, or a dash when not inside a request."""
    rid = request_id_ctx.get()
    return rid if rid else "-"


def set_request_id_for_tests(request_id: str | None) -> Token[str | None]:
    """Set the request ID (mainly for tests). Returns a token for ``reset_request_id``."""
    return request_id_ctx.set(request_id)


def reset_request_id(token: Token[str | None]) -> None:
    """Restore the previous request ID context."""
    request_id_ctx.reset(token)


def _patch_request_id(record: dict) -> None:
    """Inject ``request_id`` into log records for formatting."""
    record["extra"]["request_id"] = get_request_id()


def _ensure_logs_dir() -> Path:
    root = Path(__file__).resolve().parents[2]
    logs_dir = root / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    return logs_dir


def configure_logging() -> None:
    """Configure console and rotating file sinks. Safe to call once at import time."""
    _logger.remove()
    _logger.configure(patcher=_patch_request_id)

    console_fmt = (
        "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
        "<level>{level: <8}</level> | "
        "<cyan>{extra[request_id]}</cyan> | "
        "<level>{message}</level>"
    )
    file_fmt = (
        "{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {extra[request_id]} | {message}"
    )

    _logger.add(
        sys.stderr,
        level="INFO",
        colorize=True,
        format=console_fmt,
        enqueue=True,
    )

    logs_dir = _ensure_logs_dir()

    _logger.add(
        logs_dir / "app.log",
        rotation="10 MB",
        retention="7 days",
        level="DEBUG",
        format=file_fmt,
        encoding="utf-8",
        enqueue=True,
        catch=True,
    )

    _logger.add(
        logs_dir / "errors.log",
        rotation="10 MB",
        retention="30 days",
        level="ERROR",
        format=file_fmt,
        encoding="utf-8",
        enqueue=True,
        catch=True,
    )


configure_logging()

# Public logger — use this across the application
logger = _logger

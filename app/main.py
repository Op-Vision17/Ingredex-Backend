"""FastAPI application entrypoint."""

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request as StarletteRequest
from starlette.responses import Response

from app.config import settings
from app.database import check_database_connection, init_db
from app.features.auth.router import router as auth_router
from app.features.scan.router import router as scan_router
from app.features.analyze.router import router as analyze_router
from app.features.history.router import router as history_router
from app.features.profile.router import router as profile_router
from app.shared.services.cache_service import cache
from app.utils.logger import logger, request_id_ctx


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Attach a stable request ID for logs and response header ``X-Request-ID``."""

    async def dispatch(self, request: StarletteRequest, call_next) -> Response:
        header = request.headers.get("X-Request-ID")
        rid = header.strip() if header and header.strip() else str(uuid.uuid4())
        token = request_id_ctx.set(rid)
        try:
            response = await call_next(request)
            response.headers["X-Request-ID"] = rid
            return response
        finally:
            request_id_ctx.reset(token)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Startup: DB tables + Redis cache; shutdown: release resources."""
    try:
        await init_db()
    except Exception:
        logger.exception("Database initialization failed")
        raise
    try:
        await cache.connect()
    except Exception:
        logger.exception(
            "Redis cache connect failed; API will run without cache until Redis is up",
        )
    logger.info(
        "Ingredex API startup complete (env={}, app={})",
        settings.app_env,
        settings.app_name,
    )
    yield
    await cache.disconnect()
    logger.info("Ingredex API shutdown complete")


app = FastAPI(
    title="Ingredex API",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(RequestIDMiddleware)

app.include_router(auth_router, prefix="/auth", tags=["auth"])
app.include_router(scan_router, prefix="/scan", tags=["scan"])
app.include_router(analyze_router, prefix="/analyze", tags=["analyze"])
app.include_router(history_router, prefix="/history", tags=["history"])
app.include_router(profile_router, prefix="/profile", tags=["profile"])


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Let FastAPI handle HTTP and validation errors; log and mask everything else."""
    if isinstance(exc, HTTPException):
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail},
            headers=exc.headers,
        )
    if isinstance(exc, RequestValidationError):
        return JSONResponse(
            status_code=422,
            content={"detail": exc.errors()},
        )
    logger.exception(
        "Unhandled exception {} {}: {}",
        request.method,
        request.url.path,
        exc,
    )
    return JSONResponse(
        status_code=500,
        content={"error": "Internal server error"},
    )


@app.get("/")
async def root() -> dict[str, str]:
    return {"status": "ok", "app": "Ingredex"}


@app.get("/health")
async def health() -> dict[str, Any]:
    """Liveness plus dependency checks for Postgres and Redis."""
    db_ok = await check_database_connection()
    redis_ok = await cache.health_check()

    if db_ok and redis_ok:
        overall = "ok"
    elif not db_ok and not redis_ok:
        overall = "unhealthy"
    else:
        overall = "degraded"

    if overall != "ok":
        logger.warning(
            "Health check: overall={} database={} redis={}",
            overall,
            "ok" if db_ok else "error",
            "ok" if redis_ok else "error",
        )

    return {
        "status": overall,
        "database": "ok" if db_ok else "error",
        "redis": "ok" if redis_ok else "error",
    }

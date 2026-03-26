"""JWT creation and validation using python-jose."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import HTTPException, status
from jose import JWTError, jwt

from app.config import settings


def create_access_token(data: dict[str, Any]) -> str:
    """Encode a short-lived access JWT with ``token_type: access``."""
    if not settings.jwt_secret_key.strip():
        msg = "JWT_SECRET_KEY is not configured"
        raise RuntimeError(msg)
    to_encode = dict(data)
    to_encode["token_type"] = "access"
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=settings.access_token_expire_minutes,
    )
    to_encode["exp"] = expire
    return jwt.encode(to_encode, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def create_refresh_token(data: dict[str, Any]) -> str:
    """Encode a long-lived refresh JWT with ``token_type: refresh``."""
    if not settings.jwt_secret_key.strip():
        msg = "JWT_SECRET_KEY is not configured"
        raise RuntimeError(msg)
    to_encode = dict(data)
    to_encode["token_type"] = "refresh"
    expire = datetime.now(timezone.utc) + timedelta(
        days=settings.refresh_token_expire_days,
    )
    to_encode["exp"] = expire
    return jwt.encode(to_encode, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def verify_token(token: str, token_type: str = "access") -> dict[str, Any]:
    """
    Decode JWT and ensure ``token_type`` matches.

    Legacy access tokens without ``token_type`` are accepted when ``token_type`` is ``access``.
    """
    if not settings.jwt_secret_key.strip():
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Server JWT configuration error",
        )
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
        )
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    pt = payload.get("token_type")
    if pt is None:
        if token_type != "access":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token type",
                headers={"WWW-Authenticate": "Bearer"},
            )
    elif pt != token_type:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return payload


def get_token_data(token: str) -> dict[str, Any]:
    """Return ``user_id`` (UUID) and ``email`` from a valid access token."""
    payload = verify_token(token, "access")
    sub = payload.get("sub")
    email = payload.get("email")
    if email is None:
        email = payload.get("identifier")
    if not sub or email is None or (isinstance(email, str) and not email.strip()):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        user_id = uuid.UUID(str(sub))
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid user id in token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
    return {"user_id": user_id, "email": str(email)}

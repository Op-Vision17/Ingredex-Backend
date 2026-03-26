"""User lookup, creation, and refresh-token persistence for auth."""

from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.refresh_token import RefreshToken
from app.models.user import User
from app.utils.jwt_handler import verify_token
from app.utils.logger import logger


def _hash_refresh_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


async def get_or_create_user(db: AsyncSession, email: str) -> tuple[User, bool]:
    """
    Find user by email, or create a new account with that email.

    ``email`` must be the normalized form produced by the auth schema validators.
    """
    stmt = select(User).where(User.email == email)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()
    if user is not None:
        logger.info("Existing user login: user_id={} email={}", user.id, email)
        return user, False

    user = User(email=email, phone=None)
    db.add(user)
    await db.commit()
    await db.refresh(user)
    logger.info("New user created: user_id={} email={}", user.id, email)
    return user, True


async def save_refresh_token(
    db: AsyncSession,
    user_id: uuid.UUID,
    token: str,
    device_info: str | None = None,
) -> RefreshToken:
    """Persist SHA256 hash of the refresh JWT with expiry aligned to settings."""
    logger.info("save_refresh_token: persisting hash for user_id={}", user_id)
    token_hash = _hash_refresh_token(token)
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(days=settings.refresh_token_expire_days)
    row = RefreshToken(
        user_id=user_id,
        token_hash=token_hash,
        expires_at=expires_at,
        is_revoked=False,
        device_info=device_info,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    logger.info(
        "save_refresh_token: stored refresh_token id={} user_id={} expires_at={}",
        row.id,
        user_id,
        expires_at,
    )
    return row


async def verify_refresh_token(db: AsyncSession, token: str) -> User:
    """
    Validate refresh JWT signature and DB row (not revoked, not expired); return user.
    """
    logger.info("verify_refresh_token: validating JWT (refresh)")
    payload = verify_token(token, "refresh")
    sub = payload.get("sub")
    if not sub:
        logger.warning("verify_refresh_token: missing sub in JWT")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
        )
    try:
        jwt_user_id = uuid.UUID(str(sub))
    except ValueError:
        logger.warning("verify_refresh_token: invalid sub in JWT")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
        ) from None

    token_hash = _hash_refresh_token(token)
    now = datetime.now(timezone.utc)
    stmt = select(RefreshToken).where(
        RefreshToken.token_hash == token_hash,
        RefreshToken.is_revoked.is_(False),
        RefreshToken.expires_at > now,
    )
    result = await db.execute(stmt)
    row = result.scalar_one_or_none()
    if row is None:
        logger.warning("verify_refresh_token: no matching active DB row for token hash")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
        )
    if row.user_id != jwt_user_id:
        logger.warning(
            "verify_refresh_token: JWT sub does not match stored row user_id={} jwt={}",
            row.user_id,
            jwt_user_id,
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
        )
    user = await db.get(User, row.user_id)
    if user is None:
        logger.error("verify_refresh_token: user missing for refresh_token user_id={}", row.user_id)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
        )
    if not user.is_active:
        logger.warning("verify_refresh_token: inactive user user_id={}", user.id)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
        )
    logger.info("verify_refresh_token: OK user_id={}", user.id)
    return user


async def revoke_refresh_token(db: AsyncSession, token: str) -> bool:
    """Mark the refresh token row revoked by SHA256 hash of the JWT."""
    token_hash = _hash_refresh_token(token)
    logger.info("revoke_refresh_token: revoking by hash prefix={}...", token_hash[:12])
    stmt = (
        update(RefreshToken)
        .where(RefreshToken.token_hash == token_hash)
        .values(is_revoked=True)
    )
    res = await db.execute(stmt)
    await db.commit()
    revoked = res.rowcount > 0
    logger.info("revoke_refresh_token: rowcount={} revoked={}", res.rowcount, revoked)
    return revoked


async def revoke_all_user_tokens(db: AsyncSession, user_id: uuid.UUID) -> int:
    """Revoke all non-revoked refresh tokens for the user; return count updated."""
    logger.info("revoke_all_user_tokens: user_id={}", user_id)
    stmt = (
        update(RefreshToken)
        .where(
            RefreshToken.user_id == user_id,
            RefreshToken.is_revoked.is_(False),
        )
        .values(is_revoked=True)
    )
    res = await db.execute(stmt)
    await db.commit()
    count = res.rowcount
    logger.info("revoke_all_user_tokens: revoked count={} user_id={}", count, user_id)
    return count

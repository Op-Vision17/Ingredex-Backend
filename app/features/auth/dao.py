"""Auth DAO — database queries for users, OTPs, and refresh tokens."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.otp import OTP
from app.models.refresh_token import RefreshToken
from app.models.user import User


# ── User queries ─────────────────────────────────────────────────────────────

async def find_user_by_email(db: AsyncSession, email: str) -> User | None:
    """Return user matching ``email``, or ``None``."""
    stmt = select(User).where(User.email == email)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def create_user(db: AsyncSession, email: str) -> User:
    """Insert a new user row and return it."""
    user = User(email=email, phone=None)
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def get_user_by_id(db: AsyncSession, user_id: uuid.UUID) -> User | None:
    """Fetch user by primary key."""
    return await db.get(User, user_id)


# ── OTP queries ──────────────────────────────────────────────────────────────

async def invalidate_old_otps(db: AsyncSession, email: str) -> None:
    """Mark all unused OTPs for this email as used."""
    await db.execute(
        update(OTP)
        .where(
            OTP.identifier == email,
            OTP.is_used.is_(False),
        )
        .values(is_used=True),
    )


async def save_otp_record(
    db: AsyncSession,
    email: str,
    otp_hash: str,
    expires_at: datetime,
) -> OTP:
    """Persist a new hashed OTP record."""
    row = OTP(
        identifier=email,
        otp_hash=otp_hash,
        expires_at=expires_at,
        is_used=False,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


async def find_valid_otp(db: AsyncSession, email: str, now: datetime) -> OTP | None:
    """Return the latest unused, non-expired OTP for ``email``."""
    stmt = (
        select(OTP)
        .where(
            OTP.identifier == email,
            OTP.is_used.is_(False),
            OTP.expires_at > now,
        )
        .order_by(OTP.created_at.desc())
        .limit(1)
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def mark_otp_used(db: AsyncSession, otp_row: OTP) -> None:
    """Mark OTP row as consumed."""
    otp_row.is_used = True
    await db.commit()


# ── Refresh token queries ────────────────────────────────────────────────────

async def save_refresh_token_record(
    db: AsyncSession,
    user_id: uuid.UUID,
    token_hash: str,
    expires_at: datetime,
    device_info: str | None = None,
) -> RefreshToken:
    """Persist a refresh token hash row."""
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
    return row


async def find_active_refresh_token(
    db: AsyncSession,
    token_hash: str,
    now: datetime,
) -> RefreshToken | None:
    """Find non-revoked, non-expired refresh token by hash."""
    stmt = select(RefreshToken).where(
        RefreshToken.token_hash == token_hash,
        RefreshToken.is_revoked.is_(False),
        RefreshToken.expires_at > now,
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def revoke_token_by_hash(db: AsyncSession, token_hash: str) -> int:
    """Revoke refresh token by hash. Returns rowcount."""
    stmt = (
        update(RefreshToken)
        .where(RefreshToken.token_hash == token_hash)
        .values(is_revoked=True)
    )
    res = await db.execute(stmt)
    await db.commit()
    return res.rowcount


async def revoke_all_tokens_for_user(db: AsyncSession, user_id: uuid.UUID) -> int:
    """Revoke all non-revoked refresh tokens for the user. Returns count."""
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
    return res.rowcount

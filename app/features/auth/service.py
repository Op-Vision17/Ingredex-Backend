"""Auth service — business logic for OTP, user management, and refresh tokens."""

from __future__ import annotations

import asyncio
import hashlib
import secrets
import smtplib
import uuid
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from smtplib import SMTPException

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.features.auth.dao import (
    create_user,
    find_active_refresh_token,
    find_user_by_email,
    find_valid_otp,
    get_user_by_id,
    invalidate_old_otps,
    mark_otp_used,
    revoke_all_tokens_for_user,
    revoke_token_by_hash,
    save_otp_record,
    save_refresh_token_record,
)
from app.models.user import User
from app.utils.jwt_handler import verify_token
from app.utils.logger import logger


# ── Helpers ──────────────────────────────────────────────────────────────────

def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _hash_otp(otp: str) -> str:
    return hashlib.sha256(otp.encode()).hexdigest()


def _verify_otp_hash(plain: str, hashed: str) -> bool:
    return hashlib.sha256(plain.encode()).hexdigest() == hashed


# ── OTP logic ────────────────────────────────────────────────────────────────

def generate_otp() -> str:
    """Return a random 6-digit numeric OTP."""
    return f"{secrets.randbelow(1_000_000):06d}"


async def save_otp(db: AsyncSession, email: str, otp: str) -> None:
    """Invalidate prior unused OTPs, then persist a new hashed OTP."""
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(minutes=settings.otp_expire_minutes)

    await invalidate_old_otps(db, email)
    await save_otp_record(db, email, _hash_otp(otp), expires_at)
    logger.info("Saved new OTP for email={} expires_at={}", email, expires_at)


async def validate_otp(db: AsyncSession, email: str, otp: str) -> bool:
    """Validate the latest unused, non-expired OTP and mark it used."""
    now = datetime.now(timezone.utc)
    row = await find_valid_otp(db, email, now)
    if row is None:
        logger.warning("No valid OTP for email={}", email)
        return False
    if not _verify_otp_hash(otp, row.otp_hash):
        logger.warning("OTP hash mismatch for email={}", email)
        return False
    await mark_otp_used(db, row)
    logger.info("OTP consumed for email={} otp_id={}", email, row.id)
    return True


def _send_otp_email_sync(email: str, otp: str) -> bool:
    """Blocking SMTP send with STARTTLS (port 587). Returns True on success."""
    if not settings.smtp_host.strip():
        logger.error("SMTP_HOST is not configured; cannot send email OTP")
        return False
    if not settings.smtp_from_email.strip():
        logger.error("SMTP_FROM_EMAIL is not configured; cannot send email OTP")
        return False

    subject = "Your Ingredex OTP Code"
    plain = (
        f"Your verification code is {otp}. It expires in {settings.otp_expire_minutes} minutes.\n\n"
        "Do not share this code with anyone."
    )
    html = f"""\
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <link href="https://fonts.googleapis.com/css2?family=Megrim&family=Smooch+Sans:wght@100;300;400;600&display=swap" rel="stylesheet">
</head>
<body style="margin:0;padding:0;background:#0d0d0d;font-size:16px;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#0d0d0d;padding:48px 24px;">
    <tr><td align="center">
      <table width="520" cellpadding="0" cellspacing="0" style="background:#111;border-radius:16px;border:1px solid #222;overflow:hidden;">

        <tr><td style="padding:36px 48px 28px;text-align:center;border-bottom:1px solid #1e1e1e;">
          <div style="font-family:'Megrim',cursive;font-size:32px;color:#e8f5e4;letter-spacing:0.18em;">INGREDEX</div>
          <div style="font-family:'Smooch Sans',sans-serif;font-size:11px;font-weight:300;color:#4a7c59;letter-spacing:0.3em;text-transform:uppercase;margin-top:4px;">food intelligence</div>
        </td></tr>

        <tr><td style="padding:44px 48px 36px;text-align:center;">
          <div style="font-family:'Smooch Sans',sans-serif;font-size:13px;font-weight:300;color:#6b6b6b;letter-spacing:0.2em;text-transform:uppercase;margin-bottom:12px;">your verification code</div>
          <div style="font-family:'Megrim',cursive;font-size:56px;letter-spacing:0.35em;color:#a3d9a5;margin:24px 0 8px;line-height:1;">{otp}</div>
          <div style="width:48px;height:1px;background:#2a2a2a;margin:0 auto 28px;"></div>
          <div style="font-family:'Smooch Sans',sans-serif;font-size:15px;font-weight:300;color:#888;line-height:1.8;margin-bottom:32px;">
            Enter this code to verify your identity.<br>
            This code expires in <span style="color:#a3d9a5;font-weight:400;">{settings.otp_expire_minutes} minutes</span>.
          </div>
          <table width="100%" cellpadding="0" cellspacing="0" style="background:#161616;border:1px solid #1e1e1e;border-radius:10px;">
            <tr><td style="padding:16px 20px;">
              <table cellpadding="0" cellspacing="0"><tr>
                <td style="width:6px;height:6px;background:#4a7c59;border-radius:50%;vertical-align:middle;padding-right:10px;">&nbsp;</td>
                <td style="font-family:'Smooch Sans',sans-serif;font-size:13px;font-weight:300;color:#555;">Do not share this code with anyone. Ingredex will never ask for your code.</td>
              </tr></table>
            </td></tr>
          </table>
        </td></tr>

        <tr><td style="padding:20px 48px 32px;text-align:center;border-top:1px solid #1a1a1a;">
          <div style="font-family:'Smooch Sans',sans-serif;font-size:12px;font-weight:300;color:#3a3a3a;line-height:1.9;">
            Didn't request this? You can safely ignore this email.<br>
            ingredex.app &middot; food intelligence platform
          </div>
        </td></tr>

      </table>
    </td></tr>
  </table>
</body>
</html>"""

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = f"{settings.smtp_from_name} <{settings.smtp_from_email}>"
    msg["To"] = email
    msg.set_content(plain)
    msg.add_alternative(html, subtype="html")

    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=30) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            if settings.smtp_username and settings.smtp_password:
                server.login(settings.smtp_username, settings.smtp_password)
            server.send_message(msg)
    except SMTPException as exc:
        logger.exception("SMTP error sending OTP email to {}: {}", email, exc)
        return False
    except OSError as exc:
        logger.exception("Network error sending OTP email to {}: {}", email, exc)
        return False
    else:
        logger.info("OTP email sent successfully to {}", email)
        return True


async def send_otp_email(email: str, otp: str) -> bool:
    """Send OTP via SMTP in a thread pool (``smtplib`` is synchronous)."""
    return await asyncio.to_thread(_send_otp_email_sync, email, otp)


# ── User logic ───────────────────────────────────────────────────────────────

async def get_or_create_user(db: AsyncSession, email: str) -> tuple[User, bool]:
    """Find user by email, or create a new account."""
    user = await find_user_by_email(db, email)
    if user is not None:
        logger.info("Existing user login: user_id={} email={}", user.id, email)
        return user, False

    user = await create_user(db, email)
    logger.info("New user created: user_id={} email={}", user.id, email)
    return user, True


# ── Refresh token logic ─────────────────────────────────────────────────────

async def save_refresh_token(
    db: AsyncSession,
    user_id: uuid.UUID,
    token: str,
    device_info: str | None = None,
) -> None:
    """Persist SHA256 hash of the refresh JWT with expiry aligned to settings."""
    logger.info("save_refresh_token: persisting hash for user_id={}", user_id)
    token_hash = _hash_token(token)
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(days=settings.refresh_token_expire_days)
    row = await save_refresh_token_record(db, user_id, token_hash, expires_at, device_info)
    logger.info(
        "save_refresh_token: stored refresh_token id={} user_id={} expires_at={}",
        row.id,
        user_id,
        expires_at,
    )


async def verify_refresh_token(db: AsyncSession, token: str) -> User:
    """Validate refresh JWT signature and DB row; return user."""
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

    token_hash = _hash_token(token)
    now = datetime.now(timezone.utc)
    row = await find_active_refresh_token(db, token_hash, now)
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
    user = await get_user_by_id(db, row.user_id)
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
    token_hash = _hash_token(token)
    logger.info("revoke_refresh_token: revoking by hash prefix={}...", token_hash[:12])
    count = await revoke_token_by_hash(db, token_hash)
    revoked = count > 0
    logger.info("revoke_refresh_token: rowcount={} revoked={}", count, revoked)
    return revoked


async def revoke_all_user_tokens(db: AsyncSession, user_id: uuid.UUID) -> int:
    """Revoke all non-revoked refresh tokens for the user."""
    logger.info("revoke_all_user_tokens: user_id={}", user_id)
    count = await revoke_all_tokens_for_user(db, user_id)
    logger.info("revoke_all_user_tokens: revoked count={} user_id={}", count, user_id)
    return count

"""OTP generation, storage, verification, and email delivery."""

from __future__ import annotations

import asyncio
import hashlib
import secrets
import smtplib
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from smtplib import SMTPException

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.otp import OTP
from app.utils.logger import logger


def generate_otp() -> str:
    """Return a random 6-digit numeric OTP."""
    return f"{secrets.randbelow(1_000_000):06d}"


def hash_otp(otp: str) -> str:
    return hashlib.sha256(otp.encode()).hexdigest()


def verify_otp_hash(plain: str, hashed: str) -> bool:
    return hashlib.sha256(plain.encode()).hexdigest() == hashed


async def save_otp(db: AsyncSession, email: str, otp: str) -> OTP:
    """
    Invalidate prior unused OTPs for this email, then persist a new hashed OTP.

    The ``otps.identifier`` column stores the normalized email address.
    """
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(minutes=settings.otp_expire_minutes)

    await db.execute(
        update(OTP)
        .where(
            OTP.identifier == email,
            OTP.is_used.is_(False),
        )
        .values(is_used=True),
    )

    row = OTP(
        identifier=email,
        otp_hash=hash_otp(otp),
        expires_at=expires_at,
        is_used=False,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    logger.info("Saved new OTP for email={} expires_at={}", email, expires_at)
    return row


async def validate_otp(db: AsyncSession, email: str, otp: str) -> bool:
    """
    Validate the latest unused, non-expired OTP for ``email`` and mark it used.

    Returns ``True`` on success, ``False`` if wrong OTP, expired, or already used.
    """
    now = datetime.now(timezone.utc)
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
    row = result.scalar_one_or_none()
    if row is None:
        logger.warning("No valid OTP for email={}", email)
        return False
    if not verify_otp_hash(otp, row.otp_hash):
        logger.warning("OTP hash mismatch for email={}", email)
        return False
    row.is_used = True
    await db.commit()
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
<head><meta charset="utf-8"></head>
<body style="font-family: system-ui, sans-serif; line-height: 1.5; color: #1a1a1a;">
  <p>Your verification code is:</p>
  <p style="font-size: 2rem; font-weight: bold; letter-spacing: 0.2em; margin: 1rem 0;">{otp}</p>
  <p>This code expires in <strong>{settings.otp_expire_minutes} minutes</strong>.</p>
  <p style="color: #666;">Do not share this code with anyone. Ingredex will only send codes to this email.</p>
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

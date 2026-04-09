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

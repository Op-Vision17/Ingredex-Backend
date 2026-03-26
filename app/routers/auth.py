"""Authentication routes: OTP, JWT, refresh, logout, current user."""

from typing import Annotated

from fastapi import APIRouter, Body, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.dependencies import get_current_user
from app.models.user import User
from app.schemas.auth import (
    LogoutRequest,
    LogoutResponse,
    RefreshTokenRequest,
    RefreshTokenResponse,
    SendOTPRequest,
    SendOTPResponse,
    UserResponse,
    VerifyOTPRequest,
    VerifyOTPResponse,
)
from app.services.auth_service import (
    get_or_create_user,
    revoke_all_user_tokens,
    revoke_refresh_token,
    save_refresh_token,
    verify_refresh_token,
)
from app.services.otp_service import generate_otp, save_otp, send_otp_email, validate_otp
from app.utils.jwt_handler import create_access_token, create_refresh_token
from app.utils.logger import logger

router = APIRouter()


def _access_expires_seconds() -> int:
    return settings.access_token_expire_minutes * 60


@router.post("/send-otp", response_model=SendOTPResponse)
async def send_otp(
    body: SendOTPRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> SendOTPResponse:
    """Generate an OTP, persist it, and deliver it by email."""
    email = body.email
    logger.info("send-otp: email={}", email)

    otp = generate_otp()
    await save_otp(db, email, otp)

    sent = await send_otp_email(email, otp)
    if not sent:
        logger.error("send-otp: email delivery failed for email={}", email)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Could not deliver OTP email. Please try again later.",
        )

    logger.info("send-otp: OTP email queued successfully email={}", email)
    return SendOTPResponse(
        message="OTP sent to your email.",
        expires_in_minutes=settings.otp_expire_minutes,
    )


@router.post("/verify-otp", response_model=VerifyOTPResponse)
async def verify_otp_endpoint(
    body: VerifyOTPRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> VerifyOTPResponse:
    """Validate OTP, ensure user exists, and return access + refresh tokens."""
    email = body.email
    logger.info("verify-otp: email={}", email)

    valid = await validate_otp(db, email, body.otp)
    if not valid:
        logger.warning("verify-otp failed: invalid or expired OTP for email={}", email)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired OTP",
        )

    user, is_new_user = await get_or_create_user(db, email)

    payload = {"sub": str(user.id), "email": email}
    try:
        access_token = create_access_token(payload)
        refresh_token = create_refresh_token(payload)
    except RuntimeError as exc:
        logger.exception("JWT signing failed: {}", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Authentication service misconfiguration",
        ) from exc

    await save_refresh_token(db, user.id, refresh_token)
    expires_in = _access_expires_seconds()

    logger.info(
        "verify-otp success: user_id={} is_new_user={} access_expires_in_s={}",
        user.id,
        is_new_user,
        expires_in,
    )
    return VerifyOTPResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
        access_token_expires_in=expires_in,
        is_new_user=is_new_user,
    )


@router.post("/refresh", response_model=RefreshTokenResponse)
async def refresh_tokens(
    body: RefreshTokenRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> RefreshTokenResponse:
    """Exchange a valid refresh token for new access + refresh tokens (rotation)."""
    logger.info("refresh: validating refresh token")
    user = await verify_refresh_token(db, body.refresh_token)

    revoked = await revoke_refresh_token(db, body.refresh_token)
    if not revoked:
        logger.warning("refresh: revoke of presented token failed user_id={}", user.id)

    email = user.email or ""
    payload = {"sub": str(user.id), "email": email}
    try:
        access_token = create_access_token(payload)
        new_refresh = create_refresh_token(payload)
    except RuntimeError as exc:
        logger.exception("refresh: JWT signing failed: {}", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Authentication service misconfiguration",
        ) from exc

    await save_refresh_token(db, user.id, new_refresh)
    expires_in = _access_expires_seconds()

    logger.info("Token refreshed for user {}", user.id)
    return RefreshTokenResponse(
        access_token=access_token,
        refresh_token=new_refresh,
        token_type="bearer",
        access_token_expires_in=expires_in,
    )


@router.post("/logout", response_model=LogoutResponse)
async def logout(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    body: LogoutRequest = Body(default_factory=LogoutRequest),
) -> LogoutResponse:
    """Revoke refresh token(s): one session or all sessions for this user."""
    if body.refresh_token:
        logger.info("logout: revoking single refresh token for user_id={}", current_user.id)
        await revoke_refresh_token(db, body.refresh_token)
    else:
        logger.info("logout: revoking all refresh tokens for user_id={}", current_user.id)
        await revoke_all_user_tokens(db, current_user.id)

    logger.info("User {} logged out", current_user.id)
    return LogoutResponse(message="Logged out successfully")


@router.get("/me", response_model=UserResponse)
async def read_me(
    current_user: Annotated[User, Depends(get_current_user)],
) -> UserResponse:
    """Return the authenticated user's profile."""
    logger.debug("GET /me user_id={}", current_user.id)
    return UserResponse.model_validate(current_user)

"""Auth router — endpoint declarations delegating to handler functions."""

from typing import Annotated

from fastapi import APIRouter, Body, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.features.auth.handler import (
    handle_logout,
    handle_read_me,
    handle_refresh,
    handle_send_otp,
    handle_verify_otp,
)
from app.features.auth.schemas import (
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
from app.models.user import User

router = APIRouter()


@router.post("/send-otp", response_model=SendOTPResponse)
async def send_otp(
    body: SendOTPRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> SendOTPResponse:
    """Generate an OTP, persist it, and deliver it by email."""
    return await handle_send_otp(body, db)


@router.post("/verify-otp", response_model=VerifyOTPResponse)
async def verify_otp_endpoint(
    body: VerifyOTPRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> VerifyOTPResponse:
    """Validate OTP, ensure user exists, and return access + refresh tokens."""
    return await handle_verify_otp(body, db)


@router.post("/refresh", response_model=RefreshTokenResponse)
async def refresh_tokens(
    body: RefreshTokenRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> RefreshTokenResponse:
    """Exchange a valid refresh token for new access + refresh tokens (rotation)."""
    return await handle_refresh(body, db)


@router.post("/logout", response_model=LogoutResponse)
async def logout(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    body: LogoutRequest = Body(default_factory=LogoutRequest),
) -> LogoutResponse:
    """Revoke refresh token(s): one session or all sessions for this user."""
    return await handle_logout(current_user, db, body)


@router.get("/me", response_model=UserResponse)
async def read_me(
    current_user: Annotated[User, Depends(get_current_user)],
) -> UserResponse:
    """Return the authenticated user's profile."""
    return await handle_read_me(current_user)

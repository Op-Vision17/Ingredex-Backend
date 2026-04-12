"""Pydantic schemas for authentication (OTP, tokens, user)."""

from __future__ import annotations

import uuid
from datetime import datetime

from email_validator import EmailNotValidError, validate_email
from pydantic import BaseModel, ConfigDict, Field, field_validator


class SendOTPRequest(BaseModel):
    """Request to send an OTP to an email address."""

    email: str = Field(
        ...,
        min_length=3,
        max_length=255,
        description="Email address used to deliver the OTP.",
        examples=["user@example.com"],
    )

    @field_validator("email")
    @classmethod
    def validate_email_normalized(cls, value: str) -> str:
        s = value.strip()
        if not s:
            msg = "email cannot be empty"
            raise ValueError(msg)
        try:
            return validate_email(s, check_deliverability=False).normalized
        except EmailNotValidError as exc:
            msg = "Invalid email address"
            raise ValueError(msg) from exc


class SendOTPResponse(BaseModel):
    """Acknowledgement after an OTP has been queued."""

    message: str = Field(..., description="Human-readable status message.")
    expires_in_minutes: int = Field(
        ...,
        ge=1,
        description="Minutes until the OTP expires.",
    )


class VerifyOTPRequest(BaseModel):
    """Submit email and OTP to obtain tokens."""

    email: str = Field(
        ...,
        min_length=3,
        max_length=255,
        description="Same email address used when requesting the OTP.",
    )
    otp: str = Field(
        ...,
        min_length=4,
        max_length=6,
        description="Numeric one-time password (4–6 digits).",
    )

    @field_validator("email")
    @classmethod
    def validate_email_normalized(cls, value: str) -> str:
        return SendOTPRequest.model_validate({"email": value}).email

    @field_validator("otp")
    @classmethod
    def validate_otp_digits(cls, value: str) -> str:
        s = value.strip()
        if not s.isdigit():
            msg = "OTP must contain only digits"
            raise ValueError(msg)
        if not (4 <= len(s) <= 6):
            msg = "OTP must be between 4 and 6 digits"
            raise ValueError(msg)
        return s


class VerifyOTPResponse(BaseModel):
    """Access and refresh tokens after successful OTP verification."""

    access_token: str = Field(..., description="JWT access token.")
    refresh_token: str = Field(..., description="JWT refresh token.")
    token_type: str = Field(
        default="bearer",
        description="OAuth2 token type (always bearer).",
    )
    access_token_expires_in: int = Field(
        ...,
        ge=1,
        description="Access token lifetime in seconds.",
    )
    is_new_user: bool = Field(
        ...,
        description="True if this verification created a new user record.",
    )
    needs_onboarding: bool = Field(
        default=False,
        description="True if the user has not set up their health profile yet.",
    )


class RefreshTokenRequest(BaseModel):
    """Submit refresh token to obtain a new access token (and rotated refresh token)."""

    refresh_token: str = Field(..., min_length=1, description="Current refresh JWT.")


class RefreshTokenResponse(BaseModel):
    """New access token and rotated refresh token after /auth/refresh."""

    access_token: str = Field(..., description="New JWT access token.")
    refresh_token: str = Field(..., description="New JWT refresh token (rotation).")
    token_type: str = Field(
        default="bearer",
        description="OAuth2 token type (always bearer).",
    )
    access_token_expires_in: int = Field(
        ...,
        ge=1,
        description="Access token lifetime in seconds.",
    )


class LogoutRequest(BaseModel):
    """Optional refresh token to revoke; omit to revoke all sessions for the user."""

    refresh_token: str | None = Field(
        None,
        description="If set, revoke only this refresh token; otherwise revoke all.",
    )


class LogoutResponse(BaseModel):
    """Acknowledgement after logout."""

    message: str = Field(
        default="Logged out successfully",
        description="Status message.",
    )


class UserResponse(BaseModel):
    """Public user profile for API responses."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID = Field(..., description="User primary key.")
    email: str | None = Field(None, description="Registered email, if any.")
    created_at: datetime = Field(..., description="Account creation time (UTC).")
    needs_onboarding: bool = Field(
        default=False,
        description="True if the user has not set up their health profile yet.",
    )

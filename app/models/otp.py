"""OTP ORM model."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Index, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.database import Base


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class OTP(Base):
    """One-time password record for email verification (``identifier`` holds normalized email)."""

    __tablename__ = "otps"

    __table_args__ = (Index("ix_otp_identifier_is_used", "identifier", "is_used"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    identifier: Mapped[str] = mapped_column(String(255), nullable=False)
    otp_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    is_used: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        default=_utc_now,
    )

    def __repr__(self) -> str:
        return (
            f"OTP(id={self.id!s}, identifier={self.identifier!r}, "
            f"is_used={self.is_used}, expires_at={self.expires_at!r})"
        )

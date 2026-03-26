"""Persisted refresh token records (hashed JWTs) for rotation and revocation."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.database import Base

if TYPE_CHECKING:
    from app.models.user import User


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class RefreshToken(Base):
    """Stored hash of a refresh JWT, with expiry and revocation."""

    __tablename__ = "refresh_tokens"

    __table_args__ = (
        Index("ix_refresh_tokens_token_hash", "token_hash", unique=True),
        Index("ix_refresh_tokens_user_id_is_revoked", "user_id", "is_revoked"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    token_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    is_revoked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        default=_utc_now,
    )
    device_info: Mapped[str | None] = mapped_column(String(255), nullable=True)

    user: Mapped["User"] = relationship("User", back_populates="refresh_tokens")

    def __repr__(self) -> str:
        return (
            f"RefreshToken(id={self.id!s}, user_id={self.user_id!s}, "
            f"is_revoked={self.is_revoked}, expires_at={self.expires_at!r})"
        )

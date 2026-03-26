"""User ORM model."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, CheckConstraint, DateTime, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.database import Base


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    """Application user identified by phone and/or email."""

    __tablename__ = "users"

    __table_args__ = (
        CheckConstraint(
            "(phone IS NOT NULL) OR (email IS NOT NULL)",
            name="ck_users_phone_or_email_present",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    phone: Mapped[str | None] = mapped_column(String(20), unique=True, nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        default=_utc_now,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        default=_utc_now,
        onupdate=_utc_now,
    )

    scans: Mapped[list["ProductScan"]] = relationship(
        "ProductScan",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    refresh_tokens: Mapped[list["RefreshToken"]] = relationship(
        "RefreshToken",
        back_populates="user",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return (
            f"User(id={self.id!s}, phone={self.phone!r}, email={self.email!r}, "
            f"is_active={self.is_active})"
        )

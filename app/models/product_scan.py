"""Product scan ORM model."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.database import Base


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ProductScan(Base):
    """A single product ingredient scan for a user."""

    __tablename__ = "product_scans"

    __table_args__ = (
        CheckConstraint(
            "scan_type IN ('barcode', 'ocr', 'analysis')",
            name="ck_product_scans_scan_type",
        ),
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
        index=True,
    )
    product_name: Mapped[str | None] = mapped_column(String(500), nullable=True)
    barcode: Mapped[str | None] = mapped_column(String(100), nullable=True)
    raw_ingredients: Mapped[str | None] = mapped_column(Text, nullable=True)
    analysis_result: Mapped[dict[str, Any] | list[Any] | None] = mapped_column(JSONB, nullable=True)
    scan_type: Mapped[str] = mapped_column(String(20), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        default=_utc_now,
    )

    user: Mapped["User"] = relationship("User", back_populates="scans")

    def __repr__(self) -> str:
        return (
            f"ProductScan(id={self.id!s}, user_id={self.user_id!s}, "
            f"scan_type={self.scan_type!r}, product_name={self.product_name!r})"
        )

"""Schemas for scan history API."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class ScanSummary(BaseModel):
    """Lightweight scan row for list views."""

    model_config = {"from_attributes": True}

    id: uuid.UUID
    product_name: str | None
    barcode: str | None
    scan_type: str
    created_at: datetime


class ScanDetail(BaseModel):
    """Full scan record including analysis payload when present."""

    model_config = {"from_attributes": True}

    id: uuid.UUID
    product_name: str | None
    barcode: str | None
    raw_ingredients: str | None
    analysis_result: dict[str, Any] | list[Any] | None
    scan_type: str
    created_at: datetime


class HistoryStats(BaseModel):
    """Aggregated counts for the current user."""

    total_scans: int = Field(..., ge=0)
    by_scan_type: dict[str, int] = Field(
        default_factory=dict,
        description="Counts keyed by scan_type (barcode, ocr, analysis).",
    )

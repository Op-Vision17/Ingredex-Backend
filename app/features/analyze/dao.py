"""Analyze DAO — database queries for the analyze feature."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.product_scan import ProductScan


async def save_product_scan(
    db: AsyncSession,
    user_id: uuid.UUID,
    product_name: str | None,
    raw_ingredients: str,
    analysis_result: dict[str, Any],
    scan_type: str,
) -> ProductScan:
    """Insert a new ProductScan row and return it."""
    scan = ProductScan(
        user_id=user_id,
        product_name=product_name,
        barcode=None,
        raw_ingredients=raw_ingredients,
        analysis_result=analysis_result,
        scan_type=scan_type,
    )
    db.add(scan)
    await db.commit()
    await db.refresh(scan)
    return scan

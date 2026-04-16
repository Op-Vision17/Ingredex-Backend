"""History DAO — database queries for scan history."""

from __future__ import annotations

import uuid

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.product_scan import ProductScan


async def get_scan_stats(
    db: AsyncSession,
    user_id: uuid.UUID,
) -> tuple[int, dict[str, int]]:
    """Return (total_count, {scan_type: count}) for the user."""
    total_stmt = select(func.count()).select_from(ProductScan).where(
        ProductScan.user_id == user_id,
    )
    total = int((await db.execute(total_stmt)).scalar_one())

    by_type_stmt = (
        select(ProductScan.scan_type, func.count())
        .where(ProductScan.user_id == user_id)
        .group_by(ProductScan.scan_type)
    )
    rows = (await db.execute(by_type_stmt)).all()
    by_scan_type = {row[0]: int(row[1]) for row in rows}

    return total, by_scan_type


async def list_user_scans(
    db: AsyncSession,
    user_id: uuid.UUID,
    limit: int = 50,
    offset: int = 0,
) -> list[ProductScan]:
    """List scans for the user, newest first."""
    stmt = (
        select(ProductScan)
        .where(ProductScan.user_id == user_id)
        .order_by(ProductScan.created_at.desc())
        .limit(min(limit, 200))
        .offset(max(offset, 0))
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_scan_by_id(
    db: AsyncSession,
    scan_id: uuid.UUID,
) -> ProductScan | None:
    """Fetch a single scan by primary key."""
    return await db.get(ProductScan, scan_id)


async def delete_scan(
    db: AsyncSession,
    scan_id: uuid.UUID,
    user_id: uuid.UUID,
) -> int:
    """Delete a scan owned by the user. Returns rowcount."""
    stmt = delete(ProductScan).where(
        ProductScan.id == scan_id,
        ProductScan.user_id == user_id,
    )
    result = await db.execute(stmt)
    await db.commit()
    return getattr(result, "rowcount", 0)

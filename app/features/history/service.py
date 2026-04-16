"""History service — business logic for scan history."""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.features.history.dao import (
    delete_scan as dao_delete_scan,
    get_scan_by_id,
    get_scan_stats,
    list_user_scans,
)
from app.features.history.schemas import HistoryStats, ScanDetail, ScanSummary
from app.models.product_scan import ProductScan
from app.utils.logger import logger


async def get_stats(db: AsyncSession, user_id: uuid.UUID) -> HistoryStats:
    """Aggregate scan counts for the user."""
    total, by_scan_type = await get_scan_stats(db, user_id)
    logger.debug("History stats for user_id={}: total={}", user_id, total)
    return HistoryStats(total_scans=total, by_scan_type=by_scan_type)


async def list_scans(
    db: AsyncSession,
    user_id: uuid.UUID,
    limit: int = 50,
    offset: int = 0,
) -> list[ScanSummary]:
    """List scans for the user, newest first."""
    scans = await list_user_scans(db, user_id, limit, offset)
    logger.info("Listed {} scans for user_id={}", len(scans), user_id)
    return [ScanSummary.model_validate(s) for s in scans]


async def get_scan(
    db: AsyncSession,
    scan_id: uuid.UUID,
    user_id: uuid.UUID,
) -> ProductScan | None:
    """Get a single scan if it belongs to the user."""
    scan = await get_scan_by_id(db, scan_id)
    if scan is None or scan.user_id != user_id:
        return None
    return scan


async def remove_scan(
    db: AsyncSession,
    scan_id: uuid.UUID,
    user_id: uuid.UUID,
) -> bool:
    """Delete a scan. Returns True if a row was deleted."""
    count = await dao_delete_scan(db, scan_id, user_id)
    if count > 0:
        logger.info("Deleted scan_id={} for user_id={}", scan_id, user_id)
        return True
    return False

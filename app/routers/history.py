"""Scan / analysis history (authenticated)."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models.product_scan import ProductScan
from app.models.user import User
from app.schemas.history import HistoryStats, ScanDetail, ScanSummary
from app.utils.logger import logger

router = APIRouter()


@router.get("/stats", response_model=HistoryStats)
async def get_history_stats(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> HistoryStats:
    """Aggregate scan counts for the current user."""
    total_stmt = select(func.count()).select_from(ProductScan).where(
        ProductScan.user_id == current_user.id,
    )
    total = int((await db.execute(total_stmt)).scalar_one())

    by_type_stmt = (
        select(ProductScan.scan_type, func.count())
        .where(ProductScan.user_id == current_user.id)
        .group_by(ProductScan.scan_type)
    )
    rows = (await db.execute(by_type_stmt)).all()
    by_scan_type = {row[0]: int(row[1]) for row in rows}

    logger.debug("History stats for user_id={}: total={}", current_user.id, total)
    return HistoryStats(total_scans=total, by_scan_type=by_scan_type)


@router.get("", response_model=list[ScanSummary])
async def list_scans(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    limit: int = 50,
    offset: int = 0,
) -> list[ScanSummary]:
    """List the current user's scans, newest first."""
    stmt = (
        select(ProductScan)
        .where(ProductScan.user_id == current_user.id)
        .order_by(ProductScan.created_at.desc())
        .limit(min(limit, 200))
        .offset(max(offset, 0))
    )
    result = await db.execute(stmt)
    scans = result.scalars().all()
    logger.info("Listed {} scans for user_id={}", len(scans), current_user.id)
    return [ScanSummary.model_validate(s) for s in scans]


@router.get("/{scan_id}", response_model=ScanDetail)
async def get_scan(
    scan_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ScanDetail:
    """Return a single scan by id (must belong to the current user)."""
    scan = await db.get(ProductScan, scan_id)
    if scan is None or scan.user_id != current_user.id:
        logger.warning("Scan not found or forbidden: scan_id={} user_id={}", scan_id, current_user.id)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Scan not found",
        )
    return ScanDetail.model_validate(scan)


@router.delete("/{scan_id}")
async def delete_scan(
    scan_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Response:
    """Delete a scan owned by the current user."""
    stmt = delete(ProductScan).where(
        ProductScan.id == scan_id,
        ProductScan.user_id == current_user.id,
    )
    result = await db.execute(stmt)
    await db.commit()
    if getattr(result, "rowcount", 0) == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Scan not found",
        )
    logger.info("Deleted scan_id={} for user_id={}", scan_id, current_user.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)

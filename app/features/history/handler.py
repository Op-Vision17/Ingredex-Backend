"""History handler — request handling for scan history endpoints."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import Depends, HTTPException, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.features.history.schemas import HistoryStats, ScanDetail, ScanSummary
from app.features.history.service import get_scan, get_stats, list_scans, remove_scan
from app.models.user import User
from app.utils.logger import logger


async def handle_stats(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> HistoryStats:
    """Aggregate scan counts for the current user."""
    return await get_stats(db, current_user.id)


async def handle_list_scans(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    limit: int = 50,
    offset: int = 0,
) -> list[ScanSummary]:
    """List the current user's scans, newest first."""
    return await list_scans(db, current_user.id, limit, offset)


async def handle_get_scan(
    scan_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ScanDetail:
    """Return a single scan by id (must belong to the current user)."""
    scan = await get_scan(db, scan_id, current_user.id)
    if scan is None:
        logger.warning("Scan not found or forbidden: scan_id={} user_id={}", scan_id, current_user.id)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Scan not found",
        )
    return ScanDetail.model_validate(scan)


async def handle_delete_scan(
    scan_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Response:
    """Delete a scan owned by the current user."""
    deleted = await remove_scan(db, scan_id, current_user.id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Scan not found",
        )
    return Response(status_code=status.HTTP_204_NO_CONTENT)

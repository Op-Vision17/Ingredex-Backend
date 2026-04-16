"""History router — endpoint declarations for scan history."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.features.history.handler import (
    handle_delete_scan,
    handle_get_scan,
    handle_list_scans,
    handle_stats,
)
from app.features.history.schemas import HistoryStats, ScanDetail, ScanSummary
from app.models.user import User

router = APIRouter()


@router.get("/stats", response_model=HistoryStats)
async def get_history_stats(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> HistoryStats:
    """Aggregate scan counts for the current user."""
    return await handle_stats(current_user, db)


@router.get("", response_model=list[ScanSummary])
async def list_scans(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    limit: int = 50,
    offset: int = 0,
) -> list[ScanSummary]:
    """List the current user's scans, newest first."""
    return await handle_list_scans(current_user, db, limit, offset)


@router.get("/{scan_id}", response_model=ScanDetail)
async def get_scan(
    scan_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ScanDetail:
    """Return a single scan by id (must belong to the current user)."""
    return await handle_get_scan(scan_id, current_user, db)


@router.delete("/{scan_id}")
async def delete_scan(
    scan_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Response:
    """Delete a scan owned by the current user."""
    return await handle_delete_scan(scan_id, current_user, db)

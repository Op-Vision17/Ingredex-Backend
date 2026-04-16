"""Analyze router — endpoint declaration for ingredient analysis."""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.features.analyze.handler import handle_analyze
from app.features.analyze.schemas import AnalyzeRequest, AnalyzeResponse
from app.models.user import User

router = APIRouter()


@router.post("", response_model=AnalyzeResponse)
async def analyze_ingredients(
    body: AnalyzeRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AnalyzeResponse:
    """
    Run ingredient analysis (cached when possible), persist a ``ProductScan`` on miss.

    Requires a valid JWT (Bearer).
    """
    return await handle_analyze(body, current_user, db)

"""Profile router — endpoint declarations for health profile."""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.features.profile.handler import handle_get_profile, handle_update_profile
from app.features.profile.schemas import HealthProfileResponse, HealthProfileUpdate
from app.models.user import User

router = APIRouter()


@router.get("", response_model=HealthProfileResponse)
async def get_profile(
    current_user: Annotated[User, Depends(get_current_user)],
) -> HealthProfileResponse:
    """Retrieve the current user's health profile."""
    return await handle_get_profile(current_user)


@router.put("", response_model=HealthProfileResponse)
async def update_profile(
    body: HealthProfileUpdate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> HealthProfileResponse:
    """Update or create the current user's health profile."""
    return await handle_update_profile(body, current_user, db)

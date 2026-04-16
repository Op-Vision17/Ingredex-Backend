"""Profile handler — request handling for health profile endpoints."""

from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.features.profile.schemas import HealthProfileResponse, HealthProfileUpdate
from app.features.profile.service import get_profile, update_profile
from app.models.user import User


async def handle_get_profile(
    current_user: Annotated[User, Depends(get_current_user)],
) -> HealthProfileResponse:
    """Retrieve the current user's health profile."""
    return await get_profile(current_user)


async def handle_update_profile(
    body: HealthProfileUpdate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> HealthProfileResponse:
    """Update or create the current user's health profile."""
    return await update_profile(db, current_user, body)

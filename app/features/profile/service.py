"""Profile service — business logic for health profile management."""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.features.profile.dao import get_user_profile, update_user_profile
from app.features.profile.schemas import HealthProfileResponse, HealthProfileUpdate
from app.models.user import User
from app.utils.logger import logger


async def get_profile(user: User) -> HealthProfileResponse:
    """Retrieve the user's health profile."""
    logger.info("GET /profile for user_id={}", user.id)
    profile_data = await get_user_profile(user)
    return HealthProfileResponse(
        allergies=profile_data.get("allergies", []),
        medical_conditions=profile_data.get("medical_conditions", []),
        diet_recommendations=profile_data.get("diet_recommendations", ""),
    )


async def update_profile(
    db: AsyncSession,
    user: User,
    body: HealthProfileUpdate,
) -> HealthProfileResponse:
    """Update or create the user's health profile."""
    logger.info("PUT /profile for user_id={}", user.id)
    profile_dict = body.model_dump()
    await update_user_profile(db, user, profile_dict)
    return HealthProfileResponse(**profile_dict)

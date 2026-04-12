"""Health profile management routes."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models.user import User
from app.schemas.profile import HealthProfileResponse, HealthProfileUpdate
from app.utils.logger import logger

router = APIRouter()

@router.get("", response_model=HealthProfileResponse)
async def get_profile(
    current_user: Annotated[User, Depends(get_current_user)],
) -> HealthProfileResponse:
    """Retrieve the current user's health profile."""
    logger.info("GET /profile for user_id={}", current_user.id)
    profile_data = current_user.health_profile or {}
    
    return HealthProfileResponse(
        allergies=profile_data.get("allergies", []),
        medical_conditions=profile_data.get("medical_conditions", []),
        diet_recommendations=profile_data.get("diet_recommendations", ""),
    )

@router.put("", response_model=HealthProfileResponse)
async def update_profile(
    body: HealthProfileUpdate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> HealthProfileResponse:
    """Update or create the current user's health profile."""
    logger.info("PUT /profile for user_id={}", current_user.id)
    
    profile_dict = body.model_dump()
    current_user.health_profile = profile_dict
    
    db.add(current_user)
    await db.commit()
    await db.refresh(current_user)
    
    return HealthProfileResponse(**profile_dict)

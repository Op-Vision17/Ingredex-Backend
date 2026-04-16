"""Profile DAO — database queries for user health profiles."""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User


async def get_user_profile(user: User) -> dict[str, Any]:
    """Return the user's health_profile dict (or empty dict if unset)."""
    return user.health_profile or {}


async def update_user_profile(
    db: AsyncSession,
    user: User,
    profile_dict: dict[str, Any],
) -> User:
    """Update user's health_profile column and return refreshed user."""
    user.health_profile = profile_dict
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user

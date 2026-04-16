"""Pydantic schemas for user health profiles."""

from pydantic import BaseModel, Field


class HealthProfileUpdate(BaseModel):
    """Update payload for creating/editing a user's health profile."""
    allergies: list[str] = Field(default_factory=list, description="List of user allergies.")
    medical_conditions: list[str] = Field(default_factory=list, description="Underlying medical conditions.")
    diet_recommendations: str = Field(default="", description="Strict dietary goals or doctor recommendations.")


class HealthProfileResponse(BaseModel):
    """Response payload returning the user's health profile."""
    allergies: list[str] = Field(default_factory=list)
    medical_conditions: list[str] = Field(default_factory=list)
    diet_recommendations: str = Field(default="")

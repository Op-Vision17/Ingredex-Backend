"""Pydantic schemas for ingredient analysis API."""

from __future__ import annotations

import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class AnalyzeRequest(BaseModel):
    """Request body to analyze ingredient text."""

    scan_type: Literal["analysis", "barcode", "ocr"] = Field(
        "analysis",
        description="Origin of the analysis used for history labeling.",
    )
    product_name: str | None = Field(
        None,
        max_length=500,
        description="Optional product name for context.",
    )
    ingredients: str = Field(
        ...,
        min_length=10,
        description="Ingredient list or label text to analyze (minimum 10 characters).",
    )

    @field_validator("product_name")
    @classmethod
    def strip_optional_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        s = value.strip()
        return s or None

    @field_validator("ingredients")
    @classmethod
    def strip_ingredients(cls, value: str) -> str:
        s = value.strip()
        if len(s) < 10:
            msg = "ingredients must be at least 10 characters after trimming whitespace"
            raise ValueError(msg)
        return s


class IngredientIssue(BaseModel):
    """A flagged ingredient and rationale."""

    model_config = ConfigDict(str_strip_whitespace=True)

    ingredient: str = Field(..., min_length=1, description="Ingredient name or label fragment.")
    risk: str = Field(..., min_length=1, description="Risk category or label for this issue.")
    reason: str = Field(..., min_length=1, description="Plain-language explanation.")


class GoodIngredient(BaseModel):
    """A beneficial ingredient note."""

    model_config = ConfigDict(str_strip_whitespace=True)

    ingredient: str = Field(..., min_length=1, description="Ingredient name.")
    benefit: str = Field(..., min_length=1, description="Why this ingredient is considered positive.")


class Alternative(BaseModel):
    """Suggested alternative product or ingredient."""

    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(..., min_length=1, description="Alternative product or substance name.")
    reason: str = Field(..., min_length=1, description="Why this alternative is suggested.")


class AnalysisResult(BaseModel):
    """Structured output from the analysis pipeline."""

    model_config = ConfigDict(str_strip_whitespace=True)

    health_score: int = Field(
        ...,
        ge=1,
        le=10,
        description="Overall health score from 1 (worst) to 10 (best).",
    )
    risk_level: Literal["Low", "Medium", "High"] = Field(
        ...,
        description="Qualitative risk band.",
    )
    issues: list[IngredientIssue] = Field(
        default_factory=list,
        description="Problematic ingredients or concerns.",
    )
    good_ingredients: list[GoodIngredient] = Field(
        default_factory=list,
        description="Ingredients with positive attributes.",
    )
    alternatives: list[Alternative] = Field(
        default_factory=list,
        description="Suggested alternatives.",
    )
    summary: str = Field(..., min_length=1, description="Short narrative summary of the analysis.")


class AnalyzeResponse(BaseModel):
    """API response wrapping analysis output and optional scan linkage."""

    analysis: AnalysisResult = Field(..., description="Full structured analysis.")
    product_name: str | None = Field(None, description="Resolved or user-provided product name.")
    scan_id: uuid.UUID | None = Field(
        None,
        description="Persisted scan row id, if the analysis was stored.",
    )

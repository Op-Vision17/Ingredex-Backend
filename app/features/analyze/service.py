"""Analyze service — orchestrates preprocessing, cache, AI crew, and persistence."""

from __future__ import annotations

import asyncio
import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.preprocessor import compute_ingredients_hash, normalize_ingredients
from app.features.analyze.dao import save_product_scan
from app.features.analyze.schemas import AnalysisResult
from app.shared.services.cache_service import cache
from app.utils.logger import logger


def preprocess_ingredients(raw: str) -> tuple[list[str], str] | None:
    """Normalize ingredients and compute cache hash. Returns None if empty."""
    normalized = normalize_ingredients(raw)
    if not normalized:
        return None
    ingredients_hash = compute_ingredients_hash(normalized)
    return normalized, ingredients_hash


async def get_cached_analysis(ingredients_hash: str) -> dict[str, Any] | None:
    """Try to retrieve analysis from cache."""
    try:
        return await cache.get_cached_analysis_by_hash(ingredients_hash)
    except RuntimeError:
        logger.warning("Redis unavailable; skipping analysis cache read")
        return None


async def run_ai_analysis(
    product_name: str,
    normalized: list[str],
    health_profile: dict | None,
) -> dict[str, Any]:
    """Run the CrewAI pipeline in a thread."""
    from app.ai.crew import run_analysis

    return await asyncio.to_thread(
        run_analysis,
        product_name or "",
        normalized,
        health_profile,
    )


async def persist_scan(
    db: AsyncSession,
    user_id: uuid.UUID,
    product_name: str | None,
    raw_ingredients: str,
    analysis: AnalysisResult,
    scan_type: str,
) -> uuid.UUID:
    """Save ProductScan and return its id."""
    scan = await save_product_scan(
        db,
        user_id=user_id,
        product_name=product_name,
        raw_ingredients=raw_ingredients,
        analysis_result=analysis.model_dump(),
        scan_type=scan_type,
    )
    logger.info("Saved ProductScan id={} for user_id={}", scan.id, user_id)
    return scan.id


async def cache_analysis(ingredients_hash: str, result_dict: dict[str, Any]) -> None:
    """Store analysis result in cache."""
    try:
        await cache.cache_analysis_result(ingredients_hash, result_dict)
    except RuntimeError:
        logger.warning("Could not cache analysis result (Redis unavailable)")

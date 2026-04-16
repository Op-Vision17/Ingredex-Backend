"""Analyze handler — request handling for ingredient analysis."""

from typing import Annotated

from fastapi import Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.features.analyze.schemas import AnalysisResult, AnalyzeRequest, AnalyzeResponse
from app.features.analyze.service import (
    cache_analysis,
    get_cached_analysis,
    persist_scan,
    preprocess_ingredients,
    run_ai_analysis,
)
from app.models.user import User
from app.utils.logger import logger


async def handle_analyze(
    body: AnalyzeRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AnalyzeResponse:
    """Run ingredient analysis (cached when possible), persist a ProductScan on miss."""
    logger.info(
        "POST /analyze user_id={} product_name={!r}",
        current_user.id,
        body.product_name,
    )

    result = preprocess_ingredients(body.ingredients)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No recognizable ingredients after normalization.",
        )
    normalized, ingredients_hash = result
    logger.debug(
        "Normalized {} ingredients, hash={}",
        len(normalized),
        ingredients_hash,
    )

    # Check cache
    cached = await get_cached_analysis(ingredients_hash)
    if cached is not None:
        logger.info("Analysis served from cache for hash={}", ingredients_hash)
        try:
            analysis = AnalysisResult.model_validate(cached)
        except Exception as exc:
            logger.error("Cached analysis failed validation: {}", exc)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Invalid cached analysis payload",
            ) from exc
        return AnalyzeResponse(
            analysis=analysis,
            product_name=body.product_name,
            scan_id=None,
        )

    # Run AI pipeline
    logger.info("Analysis cache miss — running CrewAI pipeline")
    try:
        result_dict = await run_ai_analysis(
            body.product_name or "",
            normalized,
            current_user.health_profile,
        )
    except Exception as exc:
        logger.exception("Crew analysis failed: {}", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Ingredient analysis service temporarily unavailable.",
        ) from exc

    try:
        analysis = AnalysisResult.model_validate(result_dict)
    except Exception as exc:
        logger.error("Could not validate analysis result: {}", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Analysis produced invalid data.",
        ) from exc

    # Persist scan
    scan_id = await persist_scan(
        db,
        user_id=current_user.id,
        product_name=body.product_name,
        raw_ingredients=body.ingredients,
        analysis=analysis,
        scan_type=body.scan_type,
    )

    # Cache result
    await cache_analysis(ingredients_hash, analysis.model_dump())

    return AnalyzeResponse(
        analysis=analysis,
        product_name=body.product_name,
        scan_id=scan_id,
    )

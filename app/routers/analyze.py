"""Ingredient analysis via CrewAI + Groq (authenticated)."""

import asyncio
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.preprocessor import compute_analysis_cache_key, normalize_ingredients
from app.database import get_db
from app.dependencies import get_current_user
from app.models.product_scan import ProductScan
from app.models.user import User
from app.schemas.analysis import AnalysisResult, AnalyzeRequest, AnalyzeResponse
from app.services.cache_service import cache
from app.services.web_search_service import web_search_service
from app.utils.logger import logger

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
    logger.info(
        "POST /analyze user_id={} product_name={!r}",
        current_user.id,
        body.product_name,
    )

    normalized = normalize_ingredients(body.ingredients)
    if not normalized:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No recognizable ingredients after normalization.",
        )

    analysis_cache_key = compute_analysis_cache_key(normalized, current_user.health_profile)
    logger.debug(
        "Normalized {} ingredients, cache_key={}",
        len(normalized),
        analysis_cache_key,
    )

    try:
        cached = await cache.get_cached_analysis_by_hash(analysis_cache_key)
    except RuntimeError:
        logger.warning("Redis unavailable; skipping analysis cache read")
        cached = None

    if cached is not None:
        summary_val = cached.get("summary", "") if isinstance(cached, dict) else ""
        if "Automated analysis could not be completed" in summary_val:
            logger.warning("Ignoring cached fallback error analysis; will re-analyze")
            cached = None
        else:
            logger.info("Analysis served from cache for key={}", analysis_cache_key)
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

    logger.info("Analysis cache miss — fetching web search context & running CrewAI pipeline")
    try:
        web_context, sources = await web_search_service.fetch_context_async(
            normalized,
            cache_service=cache,
        )
    except Exception as exc:
        logger.warning("Failed to fetch web search context asynchronously: {}", exc)
        web_context, sources = "", []

    try:
        from app.ai.crew import run_analysis

        result_dict = await asyncio.to_thread(
            run_analysis,
            body.product_name or "",
            normalized,
            current_user.health_profile,
            web_context,
            sources,
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

    scan = ProductScan(
        user_id=current_user.id,
        product_name=body.product_name,
        barcode=None,
        raw_ingredients=body.ingredients,
        analysis_result=analysis.model_dump(),
        scan_type=body.scan_type,
    )
    db.add(scan)
    await db.commit()
    await db.refresh(scan)
    logger.info("Saved ProductScan id={} for user_id={}", scan.id, current_user.id)

    if "Automated analysis could not be completed" not in analysis.summary:
        try:
            await cache.cache_analysis_result(analysis_cache_key, analysis.model_dump())
        except RuntimeError:
            logger.warning("Could not cache analysis result (Redis unavailable)")

    return AnalyzeResponse(
        analysis=analysis,
        product_name=body.product_name,
        scan_id=scan.id,
    )

"""Ingredient analysis pipeline: High-speed multi-agent synthesis with Gemini + Groq failover."""

from __future__ import annotations

import json
import os
import re
from typing import Any

import litellm

os.environ["CREWAI_DISABLE_TELEMETRY"] = "true"
os.environ["OTEL_SDK_DISABLED"] = "true"

from app.ai.prompts import (
    build_analyze_task_prompt,
    build_format_task_prompt,
    build_health_context_prompt,
)
from app.config import settings
from app.utils.logger import logger


def _fallback_analysis_dict() -> dict[str, Any]:
    return {
        "health_score": 50,
        "risk_level": "Medium",
        "issues": [],
        "good_ingredients": [],
        "alternatives": [],
        "summary": (
            "Automated analysis could not be completed. "
            "Please try scanning again."
        ),
    }


def _extract_json_dict(text: str) -> dict[str, Any] | None:
    cleaned = text.strip()
    if "```" in cleaned:
        match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", cleaned, re.DOTALL)
        if match:
            cleaned = match.group(1)
        else:
            parts = cleaned.split("```")
            for part in parts:
                part = part.strip()
                if part.startswith("json"):
                    part = part[4:].strip()
                if part.startswith("{") and part.endswith("}"):
                    cleaned = part
                    break
    elif "{" in cleaned and "}" in cleaned:
        first_brace = cleaned.find("{")
        last_brace = cleaned.rfind("}")
        cleaned = cleaned[first_brace : last_brace + 1]

    try:
        return json.loads(cleaned)
    except Exception:
        return None


def run_analysis(
    product_name: str,
    ingredients: list[str],
    health_profile: dict | None = None,
    web_context: str = "",
    sources: list[dict] | None = None,
) -> dict[str, Any]:
    from app.services.web_search_service import web_search_service

    if sources is None:
        sources = []

    ingredients_str = ", ".join(ingredients)
    logger.info("Starting analysis for product: {}", product_name or "Scanned Product")

    if not web_context and not sources:
        try:
            web_context, sources = web_search_service.fetch_context(ingredients)
        except Exception as e:
            logger.warning("Sync fallback web search skipped: {}", e)
            web_context, sources = "", []

    health_context = build_health_context_prompt(health_profile)
    analyze_instructions = build_analyze_task_prompt(
        product_name=product_name,
        ingredients_str=ingredients_str,
        health_context=health_context,
        web_context=web_context,
    )
    format_instructions = build_format_task_prompt(sources=sources)

    combined_prompt = f"""You are a senior toxicologist, clinical nutritionist, and food safety specialist.

Analyze the following product ingredients and produce the required JSON assessment.

{analyze_instructions}

{format_instructions}
"""

    gemini_key = settings.gemini_api_key.strip()
    groq_key = settings.groq_api_key.strip()

    models_to_try: list[tuple[str, str]] = []
    if gemini_key:
        models_to_try.append(("gemini/gemini-3.5-flash-lite", gemini_key))
        models_to_try.append(("gemini/gemini-flash-latest", gemini_key))
    if groq_key:
        models_to_try.append(("groq/qwen/qwen3.8-27b", groq_key))

    for model_name, api_key in models_to_try:
        try:
            logger.info("Running toxicological analysis with model: {}", model_name)
            response = litellm.completion(
                model=model_name,
                api_key=api_key,
                messages=[{"role": "user", "content": combined_prompt}],
                temperature=0.1,
                max_tokens=4096,
                timeout=12.0,
            )
            raw_text = response.choices[0].message.content or ""
            parsed = _extract_json_dict(raw_text)
            if parsed and isinstance(parsed.get("health_score"), (int, float)):
                logger.info(
                    "Analysis successfully completed using {} — score={}",
                    model_name,
                    parsed.get("health_score"),
                )
                return parsed
            logger.warning("Failed to parse valid JSON from {}; trying next model...", model_name)
        except Exception as exc:
            logger.warning("Model {} error: {}; trying next available model...", model_name, exc)

    # Fallback to CrewAI sequential process if direct calls failed
    try:
        from app.ai.agents import get_agents
        from app.ai.tasks import get_tasks
        from crewai import Crew, Process

        analyzer, formatter = get_agents(settings)
        analyze_task, format_task = get_tasks(
            analyzer,
            formatter,
            product_name,
            ingredients_str,
            web_context=web_context,
            sources=sources,
            health_profile=health_profile,
        )
        crew = Crew(
            agents=[analyzer, formatter],
            tasks=[analyze_task, format_task],
            process=Process.sequential,
            verbose=False,
            tracing=False,
        )
        raw_out = crew.kickoff()
        parsed = _extract_json_dict(str(raw_out))
        if parsed:
            return parsed
    except Exception as exc:
        logger.error("CrewAI fallback also failed: {}", exc)

    return _fallback_analysis_dict()

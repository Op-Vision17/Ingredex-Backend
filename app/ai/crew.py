"""CrewAI sequential pipeline: 2-agent ingredient analysis."""

from __future__ import annotations

import json
import os
import re
from typing import Any

os.environ["CREWAI_DISABLE_TELEMETRY"] = "true"
os.environ["OTEL_SDK_DISABLED"] = "true"

from app.ai.agents import get_agents
from app.ai.tasks import get_tasks
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
            "Please verify GROQ_API_KEY and try again."
        ),
    }


def run_analysis(
    product_name: str,
    ingredients: list[str],
    health_profile: dict | None = None,
    web_context: str = "",
    sources: list[dict] | None = None,
) -> dict[str, Any]:
    from app.services.web_search_service import web_search_service
    from app.ai.prompts import (
        build_analyze_task_prompt,
        build_format_task_prompt,
        build_health_context_prompt,
    )
    from groq import Groq

    if not settings.groq_api_key.strip():
        logger.error("GROQ_API_KEY is not set; cannot run ingredient analysis")
        return _fallback_analysis_dict()

    if sources is None:
        sources = []

    ingredients_str = ", ".join(ingredients)
    logger.info("Starting ingredient analysis for: {}", product_name or "Unknown")

    if not web_context and not sources:
        try:
            web_context, sources = web_search_service.fetch_context(ingredients)
        except Exception as e:
            logger.warning(f"Sync fallback web search skipped: {e}")
            web_context, sources = "", []

    health_context = build_health_context_prompt(health_profile)
    analyze_prompt = build_analyze_task_prompt(
        product_name,
        ingredients_str,
        health_context,
        web_context=web_context,
    )
    format_prompt = build_format_task_prompt(sources=sources)
    full_prompt = f"{analyze_prompt}\n\n═══════════════════════════════\nOUTPUT FORMAT SPECIFICATION:\n{format_prompt}"

    try:
        client = Groq(api_key=settings.groq_api_key.strip())
        model_name = settings.groq_model.strip()
        if model_name.startswith("groq/"):
            model_name = model_name[5:]

        response = client.chat.completions.create(
            model=model_name or "openai/gpt-oss-20b",
            response_format={"type": "json_object"},
            messages=[
                {
                    "role": "system",
                    "content": "You are a Senior Food Toxicologist and Nutritional Specialist. Output pure valid JSON matching the requested schema.",
                },
                {"role": "user", "content": full_prompt},
            ],
            temperature=0.1,
            max_tokens=2048,
        )
        result_text = response.choices[0].message.content or ""
        cleaned_text = result_text.strip()
        if "```" in cleaned_text:
            match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", cleaned_text, re.DOTALL)
            if match:
                cleaned_text = match.group(1)
            else:
                parts = cleaned_text.split("```")
                for part in parts:
                    part = part.strip()
                    if part.startswith("json"):
                        part = part[4:].strip()
                    if part.startswith("{") and part.endswith("}"):
                        cleaned_text = part
                        break
        elif "{" in cleaned_text and "}" in cleaned_text:
            first_brace = cleaned_text.find("{")
            last_brace = cleaned_text.rfind("}")
            cleaned_text = cleaned_text[first_brace : last_brace + 1]

        parsed: dict[str, Any] = json.loads(cleaned_text)
        logger.info(
            "Analysis complete — score={}",
            parsed.get("health_score"),
        )
        return parsed

    except json.JSONDecodeError as e:
        logger.error(
            "JSON parse failed: {} | raw: {!r}",
            e,
            result_text[:200] if result_text else "",
        )
        return _fallback_analysis_dict()
    except Exception as exc:
        logger.warning("Ingredient analysis failed: {}; returning fallback", exc)
        return _fallback_analysis_dict()

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
    from crewai import Agent, Task, Crew, Process
    from app.services.web_search_service import web_search_service
    if not settings.groq_api_key.strip():
        logger.error("GROQ_API_KEY is not set; cannot run ingredient crew")
        return _fallback_analysis_dict()

    if sources is None:
        sources = []

    ingredients_str = ", ".join(ingredients)

    logger.info("Starting 2-agent CrewAI analysis for: {}", product_name)

    # If web_context wasn't pre-fetched asynchronously, attempt sync fallback
    if not web_context and not sources:
        try:
            web_context, sources = web_search_service.fetch_context(ingredients)
        except Exception as e:
            logger.warning(f"Sync fallback web search skipped: {e}")
            web_context, sources = "", []

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

    result_text = ""
    for attempt in range(2):
        try:
            raw_out = crew.kickoff()
            result_text = str(raw_out).strip()
            # Robust JSON block extraction
            cleaned_text = result_text
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
                "CrewAI analysis complete — score={}",
                parsed.get("health_score"),
            )
            return parsed

        except json.JSONDecodeError as e:
            logger.error(
                "JSON parse failed: {} | raw: {!r}",
                e,
                result_text[:200] if result_text else "",
            )
            if attempt == 0:
                import time
                time.sleep(1)
                continue
            return _fallback_analysis_dict()
        except Exception as exc:
            logger.warning(
                "CrewAI execution attempt {} failed: {}",
                attempt + 1,
                exc,
            )
            if attempt == 0:
                import time
                logger.info("Retrying CrewAI analysis after 3s backoff...")
                time.sleep(3)
                continue
            return _fallback_analysis_dict()

    return _fallback_analysis_dict()

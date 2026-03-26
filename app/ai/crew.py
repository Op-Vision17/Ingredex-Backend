"""CrewAI sequential pipeline: 2-agent ingredient analysis."""

from __future__ import annotations

import json
import os
from typing import Any

os.environ["CREWAI_DISABLE_TELEMETRY"] = "true"
os.environ["OTEL_SDK_DISABLED"] = "true"

from crewai import Crew, Process

from app.ai.agents import get_agents
from app.ai.tasks import get_tasks
from app.config import settings
from app.utils.logger import logger


def _fallback_analysis_dict() -> dict[str, Any]:
    return {
        "health_score": 5,
        "risk_level": "Medium",
        "issues": [],
        "good_ingredients": [],
        "alternatives": [],
        "summary": (
            "Automated analysis could not be completed. "
            "Please verify GROQ_API_KEY and try again."
        ),
    }


def run_analysis(product_name: str, ingredients: list[str]) -> dict[str, Any]:
    if not settings.groq_api_key.strip():
        logger.error("GROQ_API_KEY is not set; cannot run ingredient crew")
        return _fallback_analysis_dict()

    ingredients_str = ", ".join(ingredients)

    logger.info("Starting 2-agent CrewAI analysis for: {}", product_name)

    analyzer, formatter = get_agents(settings)
    analyze_task, format_task = get_tasks(
        analyzer,
        formatter,
        product_name,
        ingredients_str,
    )

    crew = Crew(
        agents=[analyzer, formatter],
        tasks=[analyze_task, format_task],
        process=Process.sequential,
        verbose=False,
        tracing=False,
    )

    result_text = ""
    try:
        raw_out = crew.kickoff()
        result_text = str(raw_out).strip()

        if "```" in result_text:
            parts = result_text.split("```")
            for part in parts:
                part = part.strip()
                if part.startswith("json"):
                    part = part[4:].strip()
                if part.startswith("{"):
                    result_text = part
                    break

        parsed: dict[str, Any] = json.loads(result_text)
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
        return _fallback_analysis_dict()
    except Exception:
        logger.exception("CrewAI crew.kickoff() failed")
        raise

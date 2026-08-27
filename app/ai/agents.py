"""CrewAI agents: analyzer + formatter (Groq via LiteLLM)."""

from __future__ import annotations

import os

from crewai import Agent, LLM

from app.ai.prompts import (
    ANALYZER_BACKSTORY,
    ANALYZER_GOAL,
    ANALYZER_ROLE,
    FORMATTER_BACKSTORY,
    FORMATTER_GOAL,
    FORMATTER_ROLE,
)
from app.config import Settings


def get_agents(settings: Settings) -> tuple[Agent, Agent]:
    if settings.gemini_api_key.strip():
        clean_key = settings.gemini_api_key.strip()
        os.environ["GEMINI_API_KEY"] = clean_key
        model_name = settings.groq_model.strip()
        if not model_name.startswith("gemini/"):
            model_name = "gemini/gemini-3.6-flash"
    else:
        clean_key = settings.groq_api_key.strip()
        os.environ["GROQ_API_KEY"] = clean_key
        model_name = settings.groq_model.strip() or "groq/llama-3.1-8b-instant"
        if not model_name.startswith("groq/"):
            model_name = f"groq/{model_name}"

    analyzer_llm = LLM(
        model=model_name,
        api_key=clean_key,
        temperature=0.1,
        max_tokens=800,
    )

    formatter_llm = LLM(
        model=model_name,
        api_key=clean_key,
        temperature=0.1,
        max_tokens=2048,
    )

    analyzer = Agent(
        role=ANALYZER_ROLE,
        goal=ANALYZER_GOAL,
        backstory=ANALYZER_BACKSTORY,
        llm=analyzer_llm,
        verbose=False,
        allow_delegation=False,
        max_iter=1,
    )

    formatter = Agent(
        role=FORMATTER_ROLE,
        goal=FORMATTER_GOAL,
        backstory=FORMATTER_BACKSTORY,
        llm=formatter_llm,
        verbose=False,
        allow_delegation=False,
        max_iter=1,
    )

    return analyzer, formatter


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
    os.environ["GROQ_API_KEY"] = settings.groq_api_key

    llm = LLM(
        model="groq/llama-3.3-70b-versatile",
        temperature=0.1,
    )

    analyzer = Agent(
        role=ANALYZER_ROLE,
        goal=ANALYZER_GOAL,
        backstory=ANALYZER_BACKSTORY,
        llm=llm,
        verbose=False,
    )

    formatter = Agent(
        role=FORMATTER_ROLE,
        goal=FORMATTER_GOAL,
        backstory=FORMATTER_BACKSTORY,
        llm=llm,
        verbose=False,
    )

    return analyzer, formatter


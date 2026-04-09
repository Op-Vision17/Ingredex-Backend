"""CrewAI agents: analyzer + formatter (Groq via LiteLLM)."""

from __future__ import annotations

import os

from crewai import Agent, LLM

from app.config import Settings


def get_agents(settings: Settings) -> tuple[Agent, Agent]:
    os.environ["GROQ_API_KEY"] = settings.groq_api_key

    llm = LLM(
        model="groq/llama-3.3-70b-versatile",
        temperature=0.1,
    )

    analyzer = Agent(
        role="Food Ingredient Analyst",
        goal="Classify ingredients, identify health risks and benefits",
        backstory="""You are an expert food scientist and toxicologist who evaluates food ingredients. 
        You use an extremely stringent, objective methodology. You deeply understand food additives,
        preservatives, colorants, sweeteners and their health impacts. You strictly flag risky ingredients 
        like TBHQ, BHA, BHT, High-Fructose Corn Syrup (HFCS), artificial dyes (e.g. Red 40), and trans fats.
        You deduct points scientifically and logically based on peer-reviewed health impacts rather than guessing.""",
        llm=llm,
        verbose=False,
    )

    formatter = Agent(
        role="Health Report Formatter",
        goal="Compile ingredient analysis into strict JSON health report",
        backstory="""You are a data specialist who takes ingredient analysis
        and formats it into clean, structured JSON. You always output valid
        JSON with no markdown, no code blocks.""",
        llm=llm,
        verbose=False,
    )

    return analyzer, formatter

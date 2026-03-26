"""CrewAI tasks for 2-step ingredient analysis."""

from __future__ import annotations

from crewai import Task


def get_tasks(
    analyzer: object,
    formatter: object,
    product_name: str,
    ingredients_str: str,
) -> tuple[Task, Task]:
    analyze_task = Task(
        description=f"""Analyze these ingredients from "{product_name}":

{ingredients_str}

For each ingredient identify:
1. Type: natural/artificial/preservative/colorant/sweetener/emulsifier/other
2. Health risk: None/Low/Medium/High
3. Reason for risk (if any)
4. Any health benefits

Also determine:
- Overall health score 1-10 (1=very unhealthy, 10=very healthy)
- Overall risk level: Low/Medium/High
- 2 healthier product alternatives""",
        expected_output="Detailed ingredient analysis with risks and benefits",
        agent=analyzer,
    )

    format_task = Task(
        description="""Using the ingredient analysis provided, output ONLY this 
exact JSON with no markdown, no code fences, no extra text:

{
  "health_score": <integer 1-10>,
  "risk_level": "<Low|Medium|High>",
  "issues": [
    {"ingredient": "<name>", "risk": "<Low|Medium|High>", "reason": "<explanation>"}
  ],
  "good_ingredients": [
    {"ingredient": "<name>", "benefit": "<health benefit>"}
  ],
  "alternatives": [
    {"name": "<product name>", "reason": "<why healthier>"}
  ],
  "summary": "<2-3 sentence overall health assessment>"
}

Include top 3-5 risky ingredients in issues.
Include top 2-3 beneficial ingredients in good_ingredients.
Include exactly 2 alternatives.""",
        expected_output="Raw JSON string only",
        agent=formatter,
        context=[analyze_task],
    )

    return analyze_task, format_task

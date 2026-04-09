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
2. Health risk: None/Low/Medium/High (Be strict. Medium = allergens/debated; High = known carcinogens/banned in some countries/endocrine disruptors)
3. Reason for risk (if any) - Provide scientific reasoning.
4. Any health benefits

Calculate a strict Health Score:
- Start at 100 (perfectly healthy).
- Deduct 15 points for every High risk ingredient.
- Deduct 5 points for every Medium risk ingredient.
- IMPORTANT PROPORTION CHECK: If a large percentage of the total ingredients are High or Medium risk, heavily penalize the score. For example, if a product has only 3 ingredients and they are all bad, the score should be below 20. Adjust the final score to reflect the overall density of bad ingredients.
- Ensure the score is an integer between 1 and 100. 

Also determine:
- Overall health score 1-100 (1=toxic, 100=pristine)
- Overall risk level: Low/Medium/High based on findings.
- 2 healthier product alternatives""",
        expected_output="Detailed ingredient analysis with risks and benefits",
        agent=analyzer,
    )

    format_task = Task(
        description="""Using the ingredient analysis provided, output ONLY this 
exact JSON with no markdown, no code fences, no extra text:

{
  "health_score": <integer 1-100>,
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

STRICT RULES:
- An ingredient goes in "issues" if it has Medium or High risk. Period.
- An ingredient goes in "good_ingredients" ONLY if it has NO risk (None or Low).
- An ingredient CANNOT appear in both lists. If it has any risk, it belongs ONLY in issues.
- Include top 3-5 risky ingredients in issues.
- Include top 2-3 beneficial ingredients in good_ingredients.
- Include exactly 2 alternatives.""",
        expected_output="Raw JSON string only",
        agent=formatter,
        context=[analyze_task],
    )

    return analyze_task, format_task

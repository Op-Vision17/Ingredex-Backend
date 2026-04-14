"""CrewAI tasks for 2-step ingredient analysis."""

from __future__ import annotations

from crewai import Task


def get_tasks(
    analyzer: object,
    formatter: object,
    product_name: str,
    ingredients_str: str,
    web_context: str = "",
    sources: list[dict] = [],
    health_profile: dict | None = None,
) -> tuple[Task, Task]:
    health_context = "No specific user health profile provided."
    if health_profile:
        health_context = f"""
USER HEALTH PROFILE:
- Allergies: {', '.join(health_profile.get('allergies', [])) or 'None'}
- Medical Conditions: {', '.join(health_profile.get('medical_conditions', [])) or 'None'}
- Dietary Recommendations: {health_profile.get('diet_recommendations', 'None')}

STRICT SCORING & INSIGHT RULES:
1. ALLERGY CONFLICT: If an ingredient is a confirmed user allergy, it is a 'Negative' impact.
2. CONDITION CONFLICT: If an ingredient worsens a medical condition (e.g. sugar for diabetes), it is a 'Negative' impact.
3. PROTECTIVE/HELPFUL: If an ingredient is beneficial specifically for their condition or goals (e.g. 'whole wheat' provides complex carbs good for diabetes, 'fiber' for digestion), flag it as a 'Positive' impact.
4. BALANCED VIEW: Always try to find at least one 'Positive' insight if the product contains any healthy/natural ingredients that support general longevity or specifically aid the user's stated health profile."""

    analyze_task = Task(
        description=f"""Analyze these ingredients from "{product_name}":

{ingredients_str}

{health_context}

   ⚠️ STRICT RULES:
   1. Use WEB SEARCH RESULTS below as PRIMARY source
   2. Do NOT use your own training knowledge
   3. Cite source domain for every concern/benefit
   4. If an ingredient is not found in web search results, use your own training knowledge to analyze it and set source_domain as "ingredex" for that ingredient. Never write "No data from trusted sources" — always provide an analysis.
   5. Never guess or hallucinate

   ══════════════════════════════════════
   WEB SEARCH RESULTS (TRUSTED SOURCES):
   ══════════════════════════════════════
   {web_context if web_context else "No web data — use general knowledge cautiously"}
   ══════════════════════════════════════

For each ingredient identify:
1. Type: natural/artificial/preservative/colorant/sweetener/emulsifier/other
2. Health risk: None/Low/Medium/High (Be strict. Medium = allergens/debated; High = known carcinogens/banned in some countries/endocrine disruptors)
3. Reason for risk (if any) - Provide scientific reasoning.
4. Any health benefits

Calculate a strict PERSONALIZED Health Score:
- Start at 100 (perfectly healthy).
- GENERAL PENALTIES:
  - Deduct 15 points for every High risk ingredient.
  - Deduct 5 points for every Medium risk ingredient.
- USER-SPECIFIC IMPACTS (CRITICAL):
  - Deduct 30 points if an ingredient is a confirmed user ALLERGY.
  - Deduct 20 points if an ingredient conflicts with a user's MEDICAL CONDITION.
  - Deduct 15 points if the product violates a specific DIETARY RECOMMENDATION (e.g., 'avoid sugar' but sugar is present).
  - Add 5 points (bonus) if an ingredient specifically supports a personal goal (e.g. 'high fiber').
- PROPORTION CHECK: If most ingredients are bad or conflict with user profile, floor the score at 1-10.
- CONCLUSION: The score MUST reflect how safe the product is for THIS specific user. 
- Ensure the score is an integer between 1 and 100. 

STRICT RULE: The FIRST sentence of your 'summary' must explicitly mention any personalized deductions. E.g., 'This product scores lower due to ingredients that conflict with your allergies.'
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
    {"ingredient": "<name>", "risk": "<Low|Medium|High>", "reason": "<explanation>", "source_domain": "<e.g. ewg.org>"}
  ],
  "good_ingredients": [
    {"ingredient": "<name>", "benefit": "<health benefit>", "source_domain": "<domain>"}
  ],
  "alternatives": [
    {"name": "<product name>", "reason": "<why healthier>"}
  ],
  "user_insights": [
    {"impact": "<Positive|Negative|Neutral>", "title": "<short 3-4 word title>", "description": "<detailed reasoning based specifically on the user's health profile>"}
  ],
  "summary": "<2-3 sentence overall health assessment>",
  "sources_used": ["ewg.org", "fssai.gov.in"]
}

STRICT RULES:
- An ingredient goes in "issues" if it has Medium or High risk. Period.
- An ingredient goes in "good_ingredients" ONLY if it has NO risk (None or Low).
- An ingredient CANNOT appear in both lists. If it has any risk, it belongs ONLY in issues.
- Include top 3-5 risky ingredients in issues.
- Include top 2-3 beneficial ingredients in good_ingredients.
- Include exactly 2 alternatives.
- The health_score is a score for the PRODUCT, not the person. Never say "your score". Instead say things like "this product scores", "this product is", "this product is not recommended for you".
- In summary and user_insights, address the person directly using "you/your" when talking about their health profile, but always refer to the score/risk as belonging to the product.
- Never use the word "user". Use "you" or "your" instead.
- If source_domain is not available from web results, use "ingredex" as the source_domain. Never leave source_domain empty or write "No data".""",
        expected_output="Raw JSON string only",
        agent=formatter,
        context=[analyze_task],
    )

    return analyze_task, format_task

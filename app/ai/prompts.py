"""
Centralized Prompt Repository for Ingredex.

Contains all LLM prompts, agent backstories, task descriptions, scoring rules,
citation requirements, format schemas, OCR prompts, and web search templates.
"""

from __future__ import annotations

# ==============================================================================
# Agent Roles, Goals, & Backstories
# ==============================================================================

# ==============================================================================
# Agent Roles, Goals, & Backstories
# ==============================================================================

ANALYZER_ROLE = "Senior Food Toxicologist"
ANALYZER_GOAL = "Evaluate ingredient health risks and calculate personalized health score."
ANALYZER_BACKSTORY = """You are an expert food toxicologist. You classify ingredients into High, Medium, Low, or None risk based on safety standards (FDA, EFSA, FSSAI), apply user health profile penalties, and calculate health score (1-100)."""

FORMATTER_ROLE = "Health Data Formatter"
FORMATTER_GOAL = "Format toxicologist findings into schema-compliant JSON."
FORMATTER_BACKSTORY = """You format toxicological evaluations into valid JSON with no markdown wrapping or conversational filler."""


# ==============================================================================
# Task Prompt Construction Helpers
# ==============================================================================

def build_health_context_prompt(health_profile: dict | None = None) -> str:
    """Build personalized user context and scoring rules based on user profile."""
    if not health_profile:
        return "USER HEALTH PROFILE: None. Evaluate for general safety."

    allergies = health_profile.get("allergies", [])
    medical_conditions = health_profile.get("medical_conditions", [])
    diet_recommendations = health_profile.get("diet_recommendations", "None")

    return f"""USER PROFILE:
- Allergies: {', '.join(allergies) if allergies else 'None'}
- Conditions: {', '.join(medical_conditions) if medical_conditions else 'None'}
- Goals/Diet: {diet_recommendations}

SCORING RULES:
Allergy match: -30 pts. Condition conflict: -20 pts. Diet violation: -15 pts. Goal support: +5 pts."""


def build_analyze_task_prompt(
    product_name: str,
    ingredients_str: str,
    health_context: str,
    web_context: str = "",
) -> str:
    """Build the analysis task prompt for the Senior Food Toxicologist agent."""
    web_snippet = f"\nSCIENTIFIC EVIDENCE:\n{web_context}" if web_context else ""

    return f"""Analyze food product "{product_name or 'Unknown Product'}":

INGREDIENTS:
{ingredients_str}

{health_context}
{web_snippet}

RULES:
1. Risk Tiers:
   - High (-15 pts): BHA/BHT/TBHQ, artificial dyes (Red 40, Yellow 5/6), trans fats, HFCS, sodium nitrite.
   - Medium (-5 pts): Artificial sweeteners (Aspartame, Sucralose), emulsifiers (Polysorbate 80), added sugar, MSG.
   - Low: Citric acid, lecithin, baking soda.
   - None: Whole foods, water, spices.
2. Score calculation: Start 100, apply risk and profile penalties/bonuses. Clamp score 1-100.
   - 75-100: Low risk | 40-74: Medium risk | 1-39: High risk.
3. Summary: Mention score and profile conflicts using 'you/your'. Suggest 2 healthier alternatives."""


def build_format_task_prompt(sources: list[dict] | None = None) -> str:
    """Build the output formatting task prompt for the JSON report formatter agent."""
    domains = []
    if sources:
        for s in sources:
            d = s.get("domain", "").strip().lower()
            if d:
                if d.startswith("www."):
                    d = d[4:]
                if d not in domains:
                    domains.append(d)

    if not domains:
        domains = ["ingredex"]

    available_sources_str = ", ".join(f'"{d}"' for d in domains)

    return f"""Convert the analysis into pure JSON matching this exact structure:
{{
  "health_score": <int 1-100>,
  "risk_level": "<Low|Medium|High>",
  "issues": [
    {{
      "ingredient": "<name>",
      "risk": "<Medium|High>",
      "reason": "<explanation>",
      "source_domain": "<e.g. ewg.org or ingredex>"
    }}
  ],
  "good_ingredients": [
    {{
      "ingredient": "<name>",
      "benefit": "<benefit>",
      "source_domain": "<e.g. fssai.gov.in or ingredex>"
    }}
  ],
  "alternatives": [
    {{
      "name": "<healthier alternative name>",
      "reason": "<nutritional justification>"
    }}
  ],
  "user_insights": [
    {{
      "impact": "<Positive|Negative|Neutral>",
      "title": "<3-4 word title>",
      "description": "<personalized insight using 'you/your'>"
    }}
  ],
  "summary": "<2-3 sentence overview>",
  "sources_used": [{available_sources_str}]
}}
Do NOT output markdown fences (no ```json). Output raw JSON only."""



# ==============================================================================
# Service Prompts (OCR & Web Search)
# ==============================================================================

OCR_EXTRACTION_PROMPT = """You are an expert OCR food packaging ingredient extraction specialist.

INSTRUCTIONS:
1. Carefully scan the image for the ingredient list panel on the food or beverage packaging.
2. Locate section headers such as 'INGREDIENTS:', 'INGREDIENT LIST:', 'CONTAINS:', or 'COMPOSITION:'.
3. Extract ONLY the exact, complete raw ingredient list text as printed on the packaging.
4. Preserve parenthetical sub-ingredients, E-numbers/INS numbers, percentages, and punctuation (commas, semicolons).
5. Exclude non-ingredient text such as marketing slogans, nutrition facts tables, barcode numbers, net weight, storage instructions, or manufacturer address.
6. If the ingredient list is missing, blurry, unreadable, or not visible in the image, return EXACTLY: 'NO_INGREDIENTS_FOUND'.
7. Do NOT include markdown code fences, headers, explanations, or introductory text. Output raw extracted text only."""

WEB_SEARCH_QUERY_TEMPLATE = "{ingredients} food safety toxicology health effects risks benefits"

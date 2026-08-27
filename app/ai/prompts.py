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
    """Build the analysis task prompt with user-friendly language and deterministic scoring."""
    web_snippet = f"\nSCIENTIFIC EVIDENCE:\n{web_context}" if web_context else ""

    return f"""You are a caring nutritional expert and food safety advisor.

Analyze the food product "{product_name or 'Scanned Product'}" for everyday consumers.

INGREDIENTS LIST:
{ingredients_str}

{health_context}
{web_snippet}

SCIENTIFIC & DETERMINISTIC SCORING ALGORITHM (Score: 1 to 100):
Start with Base Score = 100.
Apply the following strict point deductions and bonuses:
1. HARMFUL CHEMICALS & TOXIC ADDITIVES: Deduct -25 points each (e.g. INS 133 / Brilliant Blue, Tartrazine / Yellow 5, Red 40, TBHQ, BHA, BHT, Potassium Bromate, Trans Fats, Hydrogenated Oils, High Fructose Corn Syrup).
2. MODERATE CONCERNS & REFINED OILS: Deduct -10 points each (e.g. Palm / Palmolein Oil, Refined Bleached Sugar, Artificial Sweeteners, MSG, Sodium Nitrite, High Saturated Fat).
3. MILD PROCESSING AGENTS: Deduct -4 points each (e.g. Preservative INS 211, Emulsifier INS 471, Added Iodised Salt, Acidity Regulators).
4. USER PROFILE PENALTIES:
   - Direct Allergy Conflict: Deduct -35 points (immediately triggers High Risk).
   - Medical Condition Conflict: Deduct -20 points (e.g. High Salt for Hypertension, High Sugar/Refined Flour for Diabetes, High Saturated Fat for High Cholesterol).
   - Diet Violation: Deduct -15 points.
5. BENEFICIAL NUTRIENT BONUSES:
   - Add +5 points each for genuine wholesome whole foods (e.g. Whole Pulses/Lentils, Oats, Nuts, Seeds, Natural Spices like Turmeric/Black Pepper).
6. FINAL SCORE CALCULATION:
   - Calculate Total Score = 100 - (All Deductions) + (Bonuses).
   - Clamp final score between 1 and 100.

RISK TIER & MANDATORY VERDICT MAPPING:
- 🟢 SCORE 75 - 100: "Low" Risk.
  Verdict Title (First User Insight): "🟢 Great for Daily Snacking" (Impact: "Positive").
  Verdict Description: Explain in 1-2 simple sentences why this is wholesome and safe for everyday eating.
- 🟡 SCORE 45 - 74: "Medium" Risk.
  Verdict Title (First User Insight): "🟡 Only Good for Occasional Eating" (Impact: "Neutral").
  Verdict Description: Explain in 1-2 simple sentences why eating this daily should be avoided (e.g. due to sodium/oil/sugar), but is fine as an occasional treat.
- 🔴 SCORE 1 - 44: "High" Risk.
  Verdict Title (First User Insight): "🔴 Daily Eating Can Be Dangerous" (Impact: "Negative").
  Verdict Description: Explain in 1-2 clear sentences why regular consumption is dangerous to their body or specific health conditions.

COMMUNICATION RULES:
1. SIMPLE & JARGON-FREE: Write in plain, everyday conversational English. Avoid technical chemistry or medical jargon.
2. SPEAK DIRECTLY TO USER: Always use "you" and "your".
3. SUGGEST 2 HEALTHIER SNACKS: Recommend 2 clean, wholesome alternatives with a simple 1-sentence explanation."""


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

    return f"""Format the nutritional analysis into pure, valid JSON matching this exact structure:
{{
  "health_score": <integer 1 to 100>,
  "risk_level": "<Low | Medium | High>",
  "issues": [
    {{
      "ingredient": "<exact ingredient name>",
      "risk": "<Medium | High>",
      "reason": "<simple, jargon-free 1-sentence explanation of why it is bad>",
      "source_domain": "<e.g. who.int, fssai.gov.in, or ingredex>"
    }}
  ],
  "good_ingredients": [
    {{
      "ingredient": "<exact ingredient name>",
      "benefit": "<simple 1-sentence explanation of what good nutrient it gives you>",
      "source_domain": "<e.g. fssai.gov.in or ingredex>"
    }}
  ],
  "alternatives": [
    {{
      "name": "<clean healthier snack name>",
      "reason": "<simple 1-sentence reason why it is healthier>"
    }}
  ],
  "user_insights": [
    {{
      "impact": "<Positive | Neutral | Negative>",
      "title": "<e.g. 🟢 Great for Daily Snacking | 🟡 Only Good for Occasional Eating | 🔴 Daily Eating Can Be Dangerous>",
      "description": "<simple 1-2 sentence explanation tailored directly to the user>"
    }},
    {{
      "impact": "<Positive | Neutral | Negative>",
      "title": "<concise title for allergy/condition insight>",
      "description": "<clear advice using you/your>"
    }}
  ],
  "summary": "<2 simple sentences giving the bottom line and practical advice for you.>",
  "sources_used": [{available_sources_str}]
}}
Do NOT wrap with markdown fences. Return pure JSON text only."""



# ==============================================================================
# Service Prompts (OCR & Web Search)
# ==============================================================================

OCR_EXTRACTION_PROMPT = """Extract and output ONLY the verbatim raw ingredients list text from this packaging image.
Do not explain, do not reason, do not add introductory text. If no ingredients list is visible, return exactly 'NO_INGREDIENTS_FOUND'."""

WEB_SEARCH_QUERY_TEMPLATE = "{ingredients} food safety toxicology health effects risks benefits"

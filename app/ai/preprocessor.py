"""Ingredient list normalization and cache-key hashing."""

from __future__ import annotations

import hashlib
import re

# Common label shorthand → canonical name for consistent analysis and caching.
_SYNONYMS: dict[str, str] = {
    "msg": "monosodium glutamate",
    "e621": "monosodium glutamate",
    "e330": "citric acid",
    "hfcs": "high fructose corn syrup",
    "tbhq": "tertiary butylhydroquinone",
}


def _split_ingredients(raw: str) -> list[str]:
    """Split on comma, semicolon, or newline."""
    parts = re.split(r"[,;\n\r]+", raw)
    return [p for p in parts if p.strip()]


def _strip_parenthetical_content(token: str) -> str:
    """
    Remove parenthetical notes unless they contain numbers/codes (e.g. INS/E-numbers).
    'water (filtered)' -> 'water'
    'color (150c)' -> 'color (150c)'
    """
    def repl(match):
        inner = match.group(0)
        if any(char.isdigit() for char in inner):
            return inner
        return ""
        
    s = re.sub(r"\([^)]*\)", repl, token)
    return s.strip()


_CONVERSATIONAL_KEYWORDS = {
    "user", "analyze", "image", "locate", "transcribe", "readable", "label",
    "bottle", "looking", "crop", "zoom", "blurry", "sample", "dense", "actually",
    "wait", "think", "extract", "contains:", "ingredients:", "ingredient list",
}


def _is_invalid_ingredient_token(t: str) -> bool:
    """Check if token is conversational text, markdown noise, or meta commentary."""
    if not t or len(t) < 2 or len(t) > 90:
        return True
    if t.startswith("<") or t.endswith(">"):
        return True
    if re.match(r"^(?:step|\d+\.|\*|\-)\s*", t):
        return True
    # If token contains multiple conversational keywords or looks like a full English sentence
    words = set(re.findall(r"\b[a-z]{3,}\b", t.lower()))
    if len(words.intersection(_CONVERSATIONAL_KEYWORDS)) >= 2:
        return True
    if t.lower().startswith("the user") or t.lower().startswith("i need") or t.lower().startswith("let's"):
        return True
    return False


def normalize_ingredients(raw: str) -> list[str]:
    """
    Split, clean, lowercase, dedupe, and map synonyms to canonical names.
    Safely filters out OCR reasoning debris, sentences, and markdown artifacts.

    Returns a stable ordered list (first-seen order preserved).
    """
    # Remove leading common prefixes if present
    cleaned_raw = re.sub(r"^(?:ingredients?|contains?|composition?)\s*[:\-]\s*", "", raw.strip(), flags=re.IGNORECASE)

    seen: set[str] = set()
    out: list[str] = []
    for part in _split_ingredients(cleaned_raw):
        # Strip markdown bolding / bullets
        t = re.sub(r"^[\*\-\d\.\s]+", "", part).strip()
        t = t.replace("**", "").replace("__", "").strip()
        t = _strip_parenthetical_content(t)
        t = re.sub(r"\s+", " ", t).strip().lower()
        if _is_invalid_ingredient_token(t):
            continue
        t = _SYNONYMS.get(t, t)
        if t not in seen:
            seen.add(t)
            out.append(t)
    return out[:35]



def ingredients_to_string(ingredients: list[str]) -> str:
    """Join normalized ingredients for LLM prompts."""
    return ", ".join(ingredients)


def compute_ingredients_hash(ingredients: list[str]) -> str:
    """
    Deterministic cache key: sort, join, MD5.

    Same logical set of ingredients → same hash regardless of input order.
    """
    canonical = sorted(ingredients)
    joined = ",".join(canonical)
    return hashlib.md5(joined.encode("utf-8")).hexdigest()


def compute_analysis_cache_key(ingredients: list[str], health_profile: dict | None = None) -> str:
    """
    Compute a cache key that combines ingredient hash with health profile hash.

    This prevents cross-user personalization cache poisoning where User A's
    allergy/condition warnings would be served to User B.
    """
    import json
    ing_hash = compute_ingredients_hash(ingredients)
    if not health_profile:
        return f"{ing_hash}:default"
    profile_str = json.dumps(health_profile, sort_keys=True)
    profile_hash = hashlib.md5(profile_str.encode("utf-8")).hexdigest()
    return f"{ing_hash}:{profile_hash}"


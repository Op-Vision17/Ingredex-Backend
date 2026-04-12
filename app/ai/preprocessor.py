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


def normalize_ingredients(raw: str) -> list[str]:
    """
    Split, clean, lowercase, dedupe, and map synonyms to canonical names.

    Returns a stable ordered list (first-seen order preserved).
    """
    seen: set[str] = set()
    out: list[str] = []
    for part in _split_ingredients(raw):
        t = _strip_parenthetical_content(part)
        t = re.sub(r"\s+", " ", t).strip().lower()
        if not t:
            continue
        t = _SYNONYMS.get(t, t)
        if t not in seen:
            seen.add(t)
            out.append(t)
    return out


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

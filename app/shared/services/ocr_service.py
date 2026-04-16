"""Ingredient text extraction from label images using Groq Vision (LangChain)."""

from __future__ import annotations

import base64
import re

from langchain_core.messages import HumanMessage
from langchain_groq import ChatGroq

from app.config import settings
from app.utils.logger import logger

_EXTRACTION_PROMPT = """You are an ingredient extraction specialist. 
Look at this food product image carefully.
Extract ONLY the ingredients list text exactly as written on the packaging.
If you find an ingredients list, return just the raw ingredients text.
If no ingredients list is visible, return 'NO_INGREDIENTS_FOUND'.
Do not add any explanation, just the ingredients text."""


def _guess_image_mime(image_bytes: bytes) -> str:
    """Infer MIME type from magic bytes (no Pillow required)."""
    if image_bytes.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if image_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if len(image_bytes) >= 12 and image_bytes.startswith(b"RIFF") and image_bytes[8:12] == b"WEBP":
        return "image/webp"
    return "image/jpeg"


def _clean_extracted_text(text: str) -> str:
    """Strip ends, collapse excessive newlines, preserve commas and wording."""
    s = text.strip()
    s = re.sub(r"\n{3,}", "\n\n", s)
    s = re.sub(r"[ \t]+", " ", s)
    return s.strip()


def _response_text(content: object) -> str:
    """Normalize LangChain message content to a single string."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and "text" in block:
                parts.append(str(block["text"]))
        return "".join(parts)
    return str(content)


async def extract_text_from_image(image_bytes: bytes) -> dict:
    """
    Call Groq Vision to read the ingredients list from a product photo.

    Returns:
        ``extracted_text`` (``None`` if none found), ``confidence`` (0.0 or 0.95),
        ``found`` (whether a list was detected).
    """
    if not settings.groq_api_key.strip():
        logger.error("GROQ_API_KEY is not set; cannot run Groq Vision OCR")
        return {"extracted_text": None, "confidence": 0.0, "found": False}

    b64 = base64.standard_b64encode(image_bytes).decode("ascii")
    mime = _guess_image_mime(image_bytes)
    data_url = f"data:{mime};base64,{b64}"

    llm = ChatGroq(
        model="meta-llama/llama-4-scout-17b-16e-instruct",
        api_key=settings.groq_api_key,
        temperature=0,
    )

    message = HumanMessage(
        content=[
            {"type": "text", "text": _EXTRACTION_PROMPT},
            {
                "type": "image_url",
                "image_url": {"url": data_url},
            },
        ],
    )

    try:
        response = await llm.ainvoke([message])
    except Exception as exc:
        logger.exception("Groq Vision API error during OCR: {}", exc)
        return {"extracted_text": None, "confidence": 0.0, "found": False}

    raw = _response_text(response.content).strip()
    stripped = raw.strip().strip('"').strip("'")
    compact = re.sub(r"\s+", "", stripped.upper())
    if compact == "NO_INGREDIENTS_FOUND":
        logger.info("Groq Vision OCR: no ingredients list detected (NO_INGREDIENTS_FOUND)")
        return {"extracted_text": None, "confidence": 0.0, "found": False}

    cleaned = _clean_extracted_text(raw)
    if not cleaned:
        logger.info("Groq Vision OCR: empty response after cleaning")
        return {"extracted_text": None, "confidence": 0.0, "found": False}

    logger.info("Groq Vision OCR: extracted ingredients text (len={})", len(cleaned))
    return {
        "extracted_text": cleaned,
        "confidence": 0.95,
        "found": True,
    }

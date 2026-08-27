"""Ingredient text extraction from label images using Gemini Vision (LiteLLM)."""

from __future__ import annotations

import base64
import io
import re

import litellm
from PIL import Image

from app.ai.prompts import OCR_EXTRACTION_PROMPT
from app.config import settings
from app.utils.logger import logger


def _optimize_image_for_vision(image_bytes: bytes, max_dimension: int = 1024) -> tuple[bytes, str]:
    """
    Optimize packaging images for vision OCR.
    """
    try:
        with Image.open(io.BytesIO(image_bytes)) as img:
            if img.mode in ("RGBA", "P", "LA"):
                img = img.convert("RGB")

            width, height = img.size
            if max(width, height) > max_dimension:
                scale = max_dimension / max(width, height)
                new_width = int(width * scale)
                new_height = int(height * scale)
                img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
                logger.info("Scaled image from {}x{} to {}x{} for optimal vision OCR", width, height, new_width, new_height)

            out_buf = io.BytesIO()
            img.save(out_buf, format="JPEG", quality=90, optimize=True)
            return out_buf.getvalue(), "image/jpeg"
    except Exception as exc:
        logger.warning("Image optimization fallback: {}", exc)
        return image_bytes, _guess_image_mime(image_bytes)


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


def _strip_thinking_tags(text: str) -> str:
    """Remove <think>...</think> tags and take pure extracted text."""
    if "</think>" in text:
        text = text.split("</think>")[-1].strip()
    elif "<think>" in text:
        text = re.sub(r"<think>.*$", "", text, flags=re.DOTALL).strip()
    
    if "ingredient" in text.lower() and ("**analyze the image" in text.lower() or "the user wants me" in text.lower()):
        match = re.search(r"(?:ingredients?|contains?|composition?)\s*[:\-]\s*(.+)", text, flags=re.IGNORECASE | re.DOTALL)
        if match:
            text = match.group(0)

    text = re.sub(r"^(?:ingredients?|contains?|composition?)\s*[:\-]\s*", "", text, flags=re.IGNORECASE)
    return text.strip()


async def extract_text_from_image(image_bytes: bytes) -> dict:
    """
    Call Gemini Vision via LiteLLM to extract ingredients from a product photo.

    Returns:
        ``extracted_text`` (``None`` if none found), ``confidence`` (0.0 or 0.95),
        ``found`` (whether a list was detected).
    """
    use_gemini = bool(settings.gemini_api_key.strip())
    use_groq = bool(settings.groq_api_key.strip())

    if not use_gemini and not use_groq:
        logger.error("Neither GEMINI_API_KEY nor GROQ_API_KEY is set; cannot run Vision OCR")
        return {"extracted_text": None, "confidence": 0.0, "found": False}

    opt_bytes, mime = _optimize_image_for_vision(image_bytes, max_dimension=1024)
    b64 = base64.standard_b64encode(opt_bytes).decode("ascii")
    data_url = f"data:{mime};base64,{b64}"

    if use_gemini:
        model_name = "gemini/gemini-3.6-flash"
        api_key = settings.gemini_api_key.strip()
    else:
        model_name = "groq/qwen/qwen3.6-27b"
        api_key = settings.groq_api_key.strip()

    messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": OCR_EXTRACTION_PROMPT},
                {"type": "image_url", "image_url": {"url": data_url}},
            ],
        }
    ]

    try:
        response = await litellm.acompletion(
            model=model_name,
            api_key=api_key,
            messages=messages,
            temperature=0.0,
            max_tokens=800,
        )
        raw = response.choices[0].message.content or ""
    except Exception as exc:
        logger.exception("Vision OCR API error: {}", exc)
        return {"extracted_text": None, "confidence": 0.0, "found": False}

    raw = _strip_thinking_tags(raw)
    stripped = raw.strip().strip('"').strip("'")
    compact = re.sub(r"\s+", "", stripped.upper())
    if not compact or compact == "NO_INGREDIENTS_FOUND" or "NO_INGREDIENTS_FOUND" in compact:
        logger.info("Vision OCR: no ingredients list detected (NO_INGREDIENTS_FOUND)")
        return {"extracted_text": None, "confidence": 0.0, "found": False}

    cleaned = _clean_extracted_text(raw)
    if not cleaned:
        logger.info("Vision OCR: empty response after cleaning")
        return {"extracted_text": None, "confidence": 0.0, "found": False}

    logger.info("Vision OCR: extracted ingredients text (len={})", len(cleaned))
    return {
        "extracted_text": cleaned,
        "confidence": 0.95,
        "found": True,
    }


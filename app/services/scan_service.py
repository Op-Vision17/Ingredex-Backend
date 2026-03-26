"""Barcode lookup via Open Food Facts with Redis caching."""

from __future__ import annotations

import httpx

from app.services.cache_service import cache
from app.utils.logger import logger

_OPEN_FOOD_FACTS_URL = "https://world.openfoodfacts.org/api/v2/product/{barcode}.json"


async def lookup_barcode(barcode: str) -> dict:
    """
    Resolve product name and ingredients for a barcode.

    Returns a dict compatible with :class:`~app.schemas.scan.BarcodeResponse`:
    ``product_name``, ``ingredients``, ``barcode``, ``source``.
    """
    try:
        cached = await cache.get_cached_barcode(barcode)
    except RuntimeError:
        logger.warning("Barcode cache unavailable (Redis not connected); skipping cache read")
        cached = None

    if cached is not None:
        logger.info("Cache hit for barcode {}", barcode)
        return cached

    logger.debug("Cache miss for barcode {} — fetching Open Food Facts", barcode)

    async with httpx.AsyncClient(timeout=httpx.Timeout(10.0)) as client:
        url = _OPEN_FOOD_FACTS_URL.format(barcode=barcode)
        try:
            response = await client.get(url)
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            logger.warning(
                "Open Food Facts HTTP error for barcode {}: {} {}",
                barcode,
                exc.response.status_code,
                exc.response.text[:200],
            )
            return {
                "product_name": None,
                "ingredients": None,
                "barcode": barcode,
                "source": "open_food_facts_error",
            }
        except httpx.TimeoutException as exc:
            logger.warning(
                "Open Food Facts timeout for barcode {}: {}",
                barcode,
                exc,
            )
            return {
                "product_name": None,
                "ingredients": None,
                "barcode": barcode,
                "source": "open_food_facts_error",
            }
        except httpx.RequestError as exc:
            logger.warning(
                "Open Food Facts request failed for barcode {}: {}",
                barcode,
                exc,
            )
            return {
                "product_name": None,
                "ingredients": None,
                "barcode": barcode,
                "source": "open_food_facts_error",
            }

    try:
        payload = response.json()
    except ValueError as exc:
        logger.warning("Open Food Facts returned invalid JSON for barcode {}: {}", barcode, exc)
        return {
            "product_name": None,
            "ingredients": None,
            "barcode": barcode,
            "source": "open_food_facts_error",
        }

    # API uses status==1 when the product exists in the database.
    if payload.get("status") != 1 or not payload.get("product"):
        logger.info("Product not found in Open Food Facts for barcode {}", barcode)
        result = {
            "product_name": None,
            "ingredients": None,
            "barcode": barcode,
            "source": "not_found",
        }
        try:
            await cache.cache_barcode_result(barcode, result)
        except RuntimeError:
            logger.debug("Could not cache not_found result (Redis unavailable)")
        return result

    product = payload["product"]
    product_name = product.get("product_name") or product.get("product_name_en")
    ingredients = product.get("ingredients_text")

    result = {
        "product_name": product_name,
        "ingredients": ingredients,
        "barcode": barcode,
        "source": "open_food_facts",
    }
    logger.info(
        "Open Food Facts hit for barcode {}: product_name={!r}",
        barcode,
        product_name,
    )

    try:
        await cache.cache_barcode_result(barcode, result)
    except RuntimeError:
        logger.debug("Could not cache barcode result (Redis unavailable)")

    return result

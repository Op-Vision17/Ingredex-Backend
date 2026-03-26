"""
Ingredex Redis cache layer (async).

================================================================================
REDIS CONCEPTS
================================================================================

What Redis is
    Redis is an **in-memory data structure store** that behaves like a remote
    dictionary: you associate **keys** (strings) with **values** (strings, or
    richer types depending on commands). Data lives primarily in **RAM**, which
    makes reads and writes extremely fast compared to hitting PostgreSQL on disk.

Why it is faster than a typical database
    PostgreSQL persists rows to disk (with caching layers, but still optimized
    for durability and complex queries). Redis is optimized for **low-latency
    key-value access**: no SQL planner, no heavy disk I/O for simple GET/SET.
    Trade-off: Redis is **not** your source of truth for user accounts or scans;
    it is an **ephemeral acceleration layer** in front of slower or expensive work.

TTL (time to live)
    Many cache entries should not live forever. **TTL** tells Redis to
    **automatically delete** a key after N seconds. That bounds memory use and
    ensures stale product or AI data eventually refreshes from upstream sources.

When to use cache vs database
    **Database (PostgreSQL):** durable records you must not lose — users, OTPs,
    scans, audit history.
    **Redis:** derived or expensive results you can recompute — barcode lookups,
    AI analysis for the same ingredient text. If Redis loses data, the app can
    fall back to recomputing or refetching; if Postgres loses data, you have a
    real incident.

================================================================================
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any

import redis.asyncio as redis

from app.config import settings
from app.utils.logger import logger

# --- Ingredex-specific TTLs (seconds) ------------------------------------------

_BARCODE_TTL_SECONDS = 24 * 60 * 60  # 24 hours
_ANALYSIS_TTL_SECONDS = 12 * 60 * 60  # 12 hours


def _normalize_ingredients_for_hash(text: str) -> str:
    """
    Normalize ingredient text so visually identical lists map to the same hash.

    Lowercase, strip ends, collapse internal whitespace to a single space — so
    "Sugar,  FLOUR" and "sugar flour" differ, but spacing/case variants of the
    same phrase align for caching.
    """
    s = text.strip().lower()
    s = re.sub(r"\s+", " ", s)
    return s


def ingredients_md5_hash(ingredients: str) -> str:
    """Return MD5 hex digest of normalized ingredients (used as cache key suffix)."""
    normalized = _normalize_ingredients_for_hash(ingredients)
    return hashlib.md5(normalized.encode("utf-8")).hexdigest()


class CacheService:
    """
    Async Redis wrapper for Ingredex.

    Uses ``redis.asyncio`` so FastAPI handlers can ``await`` I/O without
    blocking the event loop. One shared client is created in ``connect()`` and
    closed in ``disconnect()``.
    """

    def __init__(self) -> None:
        self._client: redis.Redis | None = None

    async def connect(self) -> None:
        """
        Build the async Redis client from ``REDIS_URL`` and verify connectivity.

        ``redis.from_url`` parses connection options (host, port, db, password)
        from a single URL string — same style as ``DATABASE_URL``.
        ``decode_responses=True`` makes GET return ``str`` instead of ``bytes``,
        which matches JSON text we store in values.
        """
        if self._client is not None:
            logger.debug("Redis cache: connect() called but client already exists")
            return
        client = redis.from_url(
            settings.redis_url,
            decode_responses=True,
        )
        try:
            # PING is the simplest server round-trip: proves TCP + auth + protocol work.
            await client.ping()
        except Exception:
            await client.aclose()
            raise
        self._client = client
        logger.info("Redis cache connected to {}", settings.redis_url.split("@")[-1])

    async def disconnect(self) -> None:
        """
        Close the TCP connection pool and release resources.

        Always call this on application shutdown so sockets are not leaked.
        """
        if self._client is None:
            return
        await self._client.aclose()
        self._client = None
        logger.info("Redis cache disconnected")

    async def health_check(self) -> bool:
        """Return True if Redis responds to PING, else False."""
        if self._client is None:
            return False
        try:
            await self._client.ping()
        except Exception as exc:
            logger.warning("Redis health_check failed: {}", exc)
            return False
        else:
            return True

    def _require_client(self) -> redis.Redis:
        if self._client is None:
            msg = "Redis cache is not connected; call connect() during app startup"
            raise RuntimeError(msg)
        return self._client

    async def get(self, key: str) -> dict[str, Any] | None:
        """
        Fetch a JSON object stored under ``key``.

        Redis concept — **GET**:
            Returns the **string value** stored at ``key``, or ``nil`` (Python
            ``None``) if the key does not exist. This is an O(1) lookup in RAM.

        We stored values as JSON text, so we **deserialize** back to a Python
        ``dict``. Malformed JSON is treated as a cache miss (returns ``None``)
        and logged.
        """
        r = self._require_client()
        raw = await r.get(key)
        if raw is None:
            return None
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            logger.warning("Cache key {} has invalid JSON: {}", key, exc)
            return None
        if not isinstance(data, dict):
            logger.warning("Cache key {} expected JSON object, got {}", key, type(data))
            return None
        return data

    async def set(self, key: str, value: dict[str, Any], ttl_seconds: int = 3600) -> bool:
        """
        Store a JSON-serializable dict under ``key`` with an expiry.

        Redis concepts — **SET** and **EX**:
            **SET** writes ``key -> value`` (both strings at the protocol level).
            The **EX** option sets **TTL in seconds**: after that time Redis
            **automatically deletes** the key — no cron job required. This is how
            we avoid infinite growth of cached barcode or analysis data.

        Returns True if Redis acknowledged the write, False on failure.
        """
        r = self._require_client()
        try:
            payload = json.dumps(value, ensure_ascii=False)
            # SET key value EX ttl — atomic write + expiry in one round-trip.
            await r.set(key, payload, ex=ttl_seconds)
        except Exception as exc:
            logger.warning("Redis SET failed for key {}: {}", key, exc)
            return False
        else:
            return True

    async def delete(self, key: str) -> bool:
        """
        Remove ``key`` immediately (before any TTL would have fired).

        Redis concept — **DEL**:
            Deletes one key synchronously. If the key did not exist, Redis still
            returns 0 deletions — we treat “deleted or absent” as success for
            idempotent cache invalidation.
        """
        r = self._require_client()
        try:
            await r.delete(key)
        except Exception as exc:
            logger.warning("Redis DEL failed for key {}: {}", key, exc)
            return False
        else:
            return True

    async def exists(self, key: str) -> bool:
        """
        Check whether ``key`` exists **without** reading the value.

        Redis concept — **EXISTS**:
            Returns how many of the given keys exist (here: 0 or 1). Cheaper than
            GET when you only need “is something cached?” — no payload transfer.
        """
        r = self._require_client()
        try:
            n = await r.exists(key)
        except Exception as exc:
            logger.warning("Redis EXISTS failed for key {}: {}", key, exc)
            return False
        else:
            return n > 0

    async def get_ttl(self, key: str) -> int:
        """
        Return remaining TTL for ``key`` in seconds.

        Redis concept — **TTL**:
            **Seconds** until expiry. Special values:
            ``-2`` → key does not exist.
            ``-1`` → key exists but has **no** expiry (we always set EX, so this
            is rare unless another client changed the key).
        """
        r = self._require_client()
        try:
            return int(await r.ttl(key))
        except Exception as exc:
            logger.warning("Redis TTL failed for key {}: {}", key, exc)
            return -2

    async def set_many(self, mapping: dict[str, dict[str, Any]], ttl_seconds: int) -> bool:
        """
        Write many key→dict pairs, each with the same TTL, in one **pipeline**.

        Redis concept — **PIPELINE**:
            Normally each command is a network round-trip. A **pipeline** batches
            multiple commands and sends them together, then reads all replies.
            Throughput improves when warming many keys (e.g. bulk preload).

        We use ``SET … EX`` for each entry via the pipeline’s ``setex`` helper
        (SET with expiry in one command).
        """
        if not mapping:
            return True
        r = self._require_client()
        try:
            # Pipeline batches SETEX commands; one execute() flushes the batch.
            pipe = r.pipeline(transaction=True)
            for key, value in mapping.items():
                payload = json.dumps(value, ensure_ascii=False)
                pipe.setex(key, ttl_seconds, payload)
            await pipe.execute()
        except Exception as exc:
            logger.warning("Redis pipeline set_many failed: {}", exc)
            return False
        else:
            return True

    async def flush_pattern(self, pattern: str) -> int:
        """
        Delete all keys matching ``pattern`` (glob-style).

        Redis concepts — **SCAN** + **DEL**:
            **KEYS pattern** is O(N) and blocks the server on large databases.
            **SCAN** iterates with a cursor, yielding keys in chunks — safe for
            production. We then **DEL** each key (could batch DEL per chunk for
            fewer round-trips; this loop is clear for learning).

        Example pattern: ``"barcode:*"`` removes every barcode cache entry.

        Returns the number of keys deleted.
        """
        r = self._require_client()
        deleted = 0
        try:
            async for key in r.scan_iter(match=pattern, count=100):
                await r.delete(key)
                deleted += 1
        except Exception as exc:
            logger.warning("Redis flush_pattern failed for {}: {}", pattern, exc)
            return deleted
        else:
            return deleted

    # --- Ingredex-specific helpers -------------------------------------------

    async def cache_barcode_result(self, barcode: str, result: dict[str, Any]) -> bool:
        """
        Cache a barcode lookup response for 24 hours.

        Why cache barcodes?
            The same product is scanned repeatedly (retail, testing). Caching the
            resolved name/ingredients avoids repeated upstream API or DB work when
            nothing has changed.
        """
        key = f"barcode:{barcode}"
        return await self.set(key, result, ttl_seconds=_BARCODE_TTL_SECONDS)

    async def get_cached_barcode(self, barcode: str) -> dict[str, Any] | None:
        """
        Retrieve a cached barcode result, if any.

        Cache HIT vs MISS:
            **HIT** — Redis returned a value; we skip external work (fast path).
            **MISS** — ``None``; caller should fetch fresh data and optionally
            call ``cache_barcode_result`` to populate the cache for next time.
        """
        key = f"barcode:{barcode}"
        return await self.get(key)

    async def cache_analysis_result(self, ingredients_hash: str, result: dict[str, Any]) -> bool:
        """
        Cache AI analysis for a given **ingredients hash** (12-hour TTL).

        Same normalized ingredients → same hash → same cached analysis, so we
        do not re-run expensive LLM calls for identical text.
        """
        key = f"analysis:{ingredients_hash}"
        return await self.set(key, result, ttl_seconds=_ANALYSIS_TTL_SECONDS)

    async def get_cached_analysis_by_hash(self, ingredients_hash: str) -> dict[str, Any] | None:
        """Lookup cached analysis by precomputed hash (see ``compute_ingredients_hash``)."""
        key = f"analysis:{ingredients_hash}"
        return await self.get(key)

    async def get_cached_analysis(self, ingredients: str) -> dict[str, Any] | None:
        """
        Look up analysis by raw ingredients string.

        We **normalize + MD5-hash** the text so minor spacing/case differences
        still map to one stable key — otherwise "Sugar, Flour" and "sugar  flour"
        would fragment the cache.
        """
        h = ingredients_md5_hash(ingredients)
        key = f"analysis:{h}"
        return await self.get(key)


# Singleton used across the app (connect in lifespan, disconnect on shutdown).
cache = CacheService()

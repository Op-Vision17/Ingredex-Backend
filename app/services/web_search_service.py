import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from tavily import TavilyClient

from app.ai.prompts import WEB_SEARCH_QUERY_TEMPLATE
from app.config import settings
from app.utils.logger import logger


TRUSTED_DOMAINS = [
    # International
    "ewg.org",
    "healthline.com",
    "webmd.com",
    "pubmed.ncbi.nlm.nih.gov",
    "who.int",
    "fda.gov",
    "efsa.europa.eu",
    "mayoclinic.org",
    # Indian
    "fssai.gov.in",
    "icmr.gov.in",
    "nhp.gov.in",
    "apollohospitals.com",
    "1mg.com",
]

# These are universally known safe ingredients
# No need to waste Tavily calls on these
SKIP_SEARCH = {
    "water", "salt", "sugar", "wheat flour",
    "rice flour", "corn starch", "vinegar",
    "milk", "eggs", "butter", "vegetable oil",
    "soybean oil", "sunflower oil",
    "natural flavors",
    "yeast", "baking soda", "baking powder",
    "black pepper", "turmeric", "cumin",
    "coriander", "ginger", "garlic", "onion",
    "tomato", "potato starch", "tapioca starch",
}

# Redis TTL for ingredient cache — 7 days
INGREDIENT_CACHE_TTL = 60 * 60 * 24 * 7


class WebSearchService:

    def __init__(self):
        self._client = None

    @property
    def client(self) -> TavilyClient:
        if not self._client:
            if not settings.tavily_api_key:
                raise ValueError("TAVILY_API_KEY not set in .env")
            self._client = TavilyClient(
                api_key=settings.tavily_api_key
            )
        return self._client

    # ─── Redis helpers ────────────────────────────────────

    def _cache_key(self, ingredient: str) -> str:
        """Consistent cache key per ingredient."""
        return f"web:ingredient:{ingredient.lower().strip()}"

    def _get_cached(
        self,
        ingredient: str,
        redis_client,
    ) -> dict | None:
        """
        Try to get ingredient data from Redis.
        Returns parsed dict or None on miss/error.
        
        REDIS CONCEPT:
        Each ingredient gets its own key with 7-day TTL.
        Once cached, same ingredient never hits Tavily again
        for 7 days — saves API quota massively.
        """
        try:
            raw = redis_client.get(self._cache_key(ingredient))
            if raw:
                logger.info(
                    f"Redis HIT for ingredient: '{ingredient}'"
                )
                return json.loads(raw)
            logger.info(
                f"Redis MISS for ingredient: '{ingredient}'"
            )
            return None
        except Exception as e:
            logger.warning(f"Redis get failed: {e}")
            return None

    def _set_cached(
        self,
        ingredient: str,
        data: dict,
        redis_client,
    ) -> None:
        """
        Save ingredient data to Redis with 7-day TTL.
        
        REDIS CONCEPT:
        EX = expire in seconds. After 7 days Redis
        auto-deletes the key — fresh data next time.
        """
        try:
            redis_client.set(
                self._cache_key(ingredient),
                json.dumps(data),
                ex=INGREDIENT_CACHE_TTL,
            )
            logger.info(
                f"Redis SET for ingredient: '{ingredient}' "
                f"(TTL: 7 days)"
            )
        except Exception as e:
            logger.warning(f"Redis set failed: {e}")

    # ─── Batch search ─────────────────────────────────────

    def _search_single_batch(self, batch: list[str]) -> dict[str, dict]:
        batch_query = WEB_SEARCH_QUERY_TEMPLATE.format(ingredients=" ".join(batch))
        logger.info(
            f"Tavily batch search: {batch} "
            f"(1 call for {len(batch)} ingredients)"
        )
        batch_results: dict[str, dict] = {}
        try:
            response = self.client.search(
                query=batch_query,
                search_depth="basic",
                include_domains=TRUSTED_DOMAINS,
                max_results=5,
                include_answer=False,
            )

            for ingredient in batch:
                ing_lower = ingredient.lower()
                matched_content = []
                matched_sources = []

                for r in response.get("results", []):
                    content = r.get("content", "").lower()
                    url = r.get("url", "")
                    if ing_lower in content or any(
                        word in content
                        for word in ing_lower.split()
                        if len(word) > 3
                    ):
                        raw_snippet = r.get("content", "").strip()
                        snippet = raw_snippet[:350] + ("..." if len(raw_snippet) > 350 else "")
                        matched_content.append(
                            f"[Source: {url}]\n"
                            f"{snippet}"
                        )
                        raw_domain = url.split("/")[2] if (url and len(url.split("/")) > 2) else ""
                        domain = raw_domain.lower().replace("www.", "")
                        matched_sources.append({
                            "title": r.get("title", ""),
                            "url": url,
                            "domain": domain,
                        })

                batch_results[ingredient] = {
                    "ingredient": ingredient,
                    "content": "\n\n".join(matched_content),
                    "sources": matched_sources,
                    "found": bool(matched_sources),
                }

        except Exception as e:
            logger.warning(
                f"Tavily batch failed for {batch}: {e}"
            )
            for ingredient in batch:
                batch_results[ingredient] = {
                    "ingredient": ingredient,
                    "content": "",
                    "sources": [],
                    "found": False,
                }
        return batch_results

    def _batch_search(self, ingredients: list[str]) -> dict[str, dict]:
        """
        Parallelized batch search up to 5 ingredients per Tavily call across worker threads.
        """
        if not self.client:
            logger.warning("Tavily API key not set — skipping web search")
            return {}

        batch_size = 5
        batches = [
            ingredients[i : i + batch_size]
            for i in range(0, len(ingredients), batch_size)
        ]

        results: dict[str, dict] = {}
        with ThreadPoolExecutor(max_workers=min(len(batches), 5)) as executor:
            future_to_batch = {
                executor.submit(self._search_single_batch, batch): batch
                for batch in batches
            }
            for future in as_completed(future_to_batch):
                batch_res = future.result()
                results.update(batch_res)

        return results

    # ─── Redis helpers (Async) ────────────────────────────

    async def _get_cached_async(
        self,
        ingredient: str,
        cache_service,
    ) -> dict | None:
        try:
            val = await cache_service.get(self._cache_key(ingredient))
            if val and isinstance(val, dict):
                logger.info(f"Redis HIT for ingredient: '{ingredient}'")
                return val
            logger.info(f"Redis MISS for ingredient: '{ingredient}'")
            return None
        except Exception as e:
            logger.warning(f"Redis async get failed: {e}")
            return None

    async def _set_cached_async(
        self,
        ingredient: str,
        data: dict,
        cache_service,
    ) -> None:
        try:
            await cache_service.set(
                self._cache_key(ingredient),
                data,
                ttl_seconds=INGREDIENT_CACHE_TTL,
            )
            logger.info(f"Redis SET for ingredient: '{ingredient}' (TTL: 7 days)")
        except Exception as e:
            logger.warning(f"Redis async set failed: {e}")

    # ─── Main async method ───────────────────────────────

    async def fetch_context_async(
        self,
        ingredients: list[str],
        cache_service=None,
    ) -> tuple[str, list[dict]]:
        """
        Asynchronous flow called before offloading CrewAI to thread worker.
        
        1. Skip common safe ingredients
        2. Check Redis cache asynchronously per ingredient
        3. Batch search remaining on Tavily (in worker thread)
        4. Save new results to Redis asynchronously
        5. Return formatted context + sources
        """
        import asyncio

        searchable = [
            i for i in ingredients
            if i.lower().strip() not in SKIP_SEARCH
        ]
        skipped = len(ingredients) - len(searchable)
        if skipped:
            logger.info(f"Skipped {skipped} common ingredients (water, salt, etc.)")

        if not searchable:
            logger.info("All ingredients are common — no search needed")
            return "", []

        cached_results: dict[str, dict] = {}
        need_search: list[str] = []

        if cache_service and getattr(cache_service, "_client", None) is not None:
            for ing in searchable:
                cached = await self._get_cached_async(ing, cache_service)
                if cached:
                    cached_results[ing] = cached
                else:
                    need_search.append(ing)
        else:
            need_search = searchable

        logger.info(
            f"Cache: {len(cached_results)} hits, "
            f"{len(need_search)} need Tavily search"
        )

        fresh_results: dict[str, dict] = {}
        if need_search:
            try:
                fresh_results = await asyncio.to_thread(self._batch_search, need_search)
            except Exception as e:
                logger.warning(f"Tavily search execution error: {e}")
                fresh_results = {}

            if cache_service and getattr(cache_service, "_client", None) is not None:
                for ing, data in fresh_results.items():
                    if data.get("found"):
                        await self._set_cached_async(ing, data, cache_service)

        all_results = {**cached_results, **fresh_results}

        context_parts: list[str] = []
        all_sources: list[dict] = []

        for ing in searchable:
            result = all_results.get(ing)
            if not result or not result.get("found"):
                continue
            context_parts.append(f"=== {ing.upper()} ===\n{result['content']}")
            all_sources.extend(result.get("sources", []))

        seen: set[str] = set()
        unique_sources: list[dict] = []
        for s in all_sources:
            url = s.get("url", "")
            if url and url not in seen:
                seen.add(url)
                unique_sources.append(s)

        context = "\n\n".join(context_parts)
        if len(context) > 3000:
            context = context[:3000] + "\n[Context capped for token limits]"
        logger.info(
            f"Final context: {len(context)} chars, "
            f"{len(unique_sources)} unique sources"
        )
        return context, unique_sources

    # ─── Main public method (Sync fallback) ───────────────

    def fetch_context(
        self,
        ingredients: list[str],
        redis_client=None,
    ) -> tuple[str, list[dict]]:
        """
        Synchronous fallback method called from crew.py if pre-fetched context was not provided.
        """
        searchable = [
            i for i in ingredients
            if i.lower().strip() not in SKIP_SEARCH
        ]
        if not searchable:
            return "", []

        fresh_results = self._batch_search(searchable)
        context_parts: list[str] = []
        all_sources: list[dict] = []

        for ing in searchable:
            result = fresh_results.get(ing)
            if not result or not result.get("found"):
                continue
            context_parts.append(f"=== {ing.upper()} ===\n{result['content']}")
            all_sources.extend(result.get("sources", []))

        seen: set[str] = set()
        unique_sources: list[dict] = []
        for s in all_sources:
            url = s.get("url", "")
            if url and url not in seen:
                seen.add(url)
                unique_sources.append(s)

        context = "\n\n".join(context_parts)
        if len(context) > 3000:
            context = context[:3000] + "\n[Context capped for token limits]"
        return context, unique_sources

web_search_service = WebSearchService()


from tavily import TavilyClient
from app.config import settings
from app.utils.logger import logger
import json

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

    def _batch_search(
        self,
        ingredients: list[str],
    ) -> dict[str, dict]:
        """
        OPTIMIZATION: Search multiple ingredients in ONE
        Tavily call instead of one call per ingredient.

        Strategy:
        - Group ingredients into batches of 5
        - Single query: "TBHQ BHA Red40 safety risks"
        - Parse results and map back to ingredients
        - 15 ingredients = 3 calls instead of 15 ✅
        """
        results: dict[str, dict] = {}
        batch_size = 5

        # Split into batches of 5
        batches = [
            ingredients[i: i + batch_size]
            for i in range(0, len(ingredients), batch_size)
        ]

        for batch in batches:
            batch_query = (
                " ".join(batch)
                + " food safety health effects risks benefits"
            )
            logger.info(
                f"Tavily batch search: {batch} "
                f"(1 call for {len(batch)} ingredients)"
            )
            try:
                response = self.client.search(
                    query=batch_query,
                    search_depth="basic",
                    include_domains=TRUSTED_DOMAINS,
                    max_results=5,
                    include_answer=False,
                )

                # Map search results back to each ingredient
                for ingredient in batch:
                    ing_lower = ingredient.lower()
                    matched_content = []
                    matched_sources = []

                    for r in response.get("results", []):
                        content = r.get("content", "").lower()
                        url = r.get("url", "")
                        # Include result if it mentions ingredient
                        if ing_lower in content or any(
                            word in content
                            for word in ing_lower.split()
                            if len(word) > 3
                        ):
                            matched_content.append(
                                f"[Source: {url}]\n"
                                f"{r.get('content', '')}"
                            )
                            domain = (
                                url.split("/")[2] if url else ""
                            )
                            matched_sources.append({
                                "title": r.get("title", ""),
                                "url": url,
                                "domain": domain,
                            })

                    results[ingredient] = {
                        "ingredient": ingredient,
                        "content": "\n\n".join(matched_content),
                        "sources": matched_sources,
                        "found": bool(matched_sources),
                    }

            except Exception as e:
                logger.warning(
                    f"Tavily batch failed for {batch}: {e}"
                )
                # Return empty for this batch
                for ingredient in batch:
                    results[ingredient] = {
                        "ingredient": ingredient,
                        "content": "",
                        "sources": [],
                        "found": False,
                    }

        return results

    # ─── Main public method ───────────────────────────────

    def fetch_context(
        self,
        ingredients: list[str],
        redis_client=None,
    ) -> tuple[str, list[dict]]:
        """
        Main method called from crew.py.
        
        Full optimized flow:
        1. Skip common safe ingredients
        2. Check Redis cache per ingredient
        3. Batch search remaining on Tavily
        4. Save new results to Redis
        5. Return formatted context + sources
        
        Called synchronously from crew thread.
        """
        # Step 1 — Filter common/safe ingredients
        searchable = [
            i for i in ingredients
            if i.lower().strip() not in SKIP_SEARCH
        ]
        skipped = len(ingredients) - len(searchable)
        if skipped:
            logger.info(
                f"Skipped {skipped} common ingredients "
                f"(water, salt, etc.)"
            )

        if not searchable:
            logger.info("All ingredients are common — no search needed")
            return "", []

        # Step 2 — Check Redis cache for each ingredient
        cached_results: dict[str, dict] = {}
        need_search: list[str] = []

        if redis_client:
            for ing in searchable:
                cached = self._get_cached(ing, redis_client)
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

        # Step 3 — Batch search only uncached ingredients
        fresh_results: dict[str, dict] = {}
        if need_search:
            fresh_results = self._batch_search(need_search)

            # Step 4 — Save fresh results to Redis
            if redis_client:
                for ing, data in fresh_results.items():
                    if data["found"]:
                        self._set_cached(ing, data, redis_client)

        # Step 5 — Merge cached + fresh results
        all_results = {**cached_results, **fresh_results}

        # Build context string and sources list
        context_parts: list[str] = []
        all_sources: list[dict] = []

        for ing in searchable:
            result = all_results.get(ing)
            if not result or not result["found"]:
                continue
            context_parts.append(
                f"=== {ing.upper()} ===\n{result['content']}"
            )
            all_sources.extend(result["sources"])

        # Deduplicate sources by URL
        seen: set[str] = set()
        unique_sources: list[dict] = []
        for s in all_sources:
            if s["url"] not in seen:
                seen.add(s["url"])
                unique_sources.append(s)

        context = "\n\n".join(context_parts)
        logger.info(
            f"Final context: {len(context)} chars, "
            f"{len(unique_sources)} unique sources, "
            f"Tavily calls used: "
            f"{len(need_search) // 5 + (1 if need_search else 0)}"
        )
        return context, unique_sources

web_search_service = WebSearchService()

"""Web search service for verifying uncertain knowledge during scoring/reporting.

Uses Serper.dev (Google Search API) or Tavily as the search backend.
Results are annotated with source URLs for transparency.
"""

import logging
from typing import Any

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


class WebSearchService:
    """Asynchronous web search service used by scoring and report agents.

    Searches are triggered only when scoring encounters uncertain knowledge.
    Results include source URLs and are meant as supplementary reference,
    not to directly modify scores.
    """

    def __init__(self):
        self.api_key = settings.SEARCH_API_KEY
        self.provider = settings.SEARCH_PROVIDER
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=15.0)
        return self._client

    async def search(self, query: str, num_results: int = 5) -> list[dict[str, Any]]:
        """Search the web for relevant information.

        Returns a list of results with title, snippet, and link.
        """
        if not self.api_key:
            logger.warning("SEARCH_API_KEY not configured, skipping web search")
            return []

        try:
            if self.provider == "tavily":
                return await self._search_tavily(query, num_results)
            else:
                return await self._search_serper(query, num_results)
        except Exception as e:
            logger.error(f"Web search failed: {e}")
            return []

    async def _search_serper(self, query: str, num: int) -> list[dict[str, Any]]:
        client = await self._get_client()
        resp = await client.post(
            "https://google.serper.dev/search",
            json={"q": query, "num": num},
            headers={"X-API-KEY": self.api_key},
        )
        resp.raise_for_status()
        data = resp.json()
        results = []
        for item in data.get("organic", [])[:num]:
            results.append({
                "title": item.get("title", ""),
                "snippet": item.get("snippet", ""),
                "link": item.get("link", ""),
            })
        logger.info(f"Serper搜索完成: query={query}, results={len(results)}")
        return results

    async def _search_tavily(self, query: str, num: int) -> list[dict[str, Any]]:
        client = await self._get_client()
        resp = await client.post(
            "https://api.tavily.com/search",
            json={
                "api_key": self.api_key,
                "query": query,
                "max_results": num,
                "search_depth": "basic",
            },
        )
        resp.raise_for_status()
        data = resp.json()
        results = []
        for item in data.get("results", [])[:num]:
            results.append({
                "title": item.get("title", ""),
                "snippet": item.get("content", ""),
                "link": item.get("url", ""),
            })
        logger.info(f"Tavily搜索完成: query={query}, results={len(results)}")
        return results

    async def verify_knowledge(self, claim: str, context: str = "") -> dict[str, Any]:
        """Verify a claim by searching and comparing results.

        Used by scoring when a candidate's answer contains uncertain claims.
        Returns verification result with source references.
        """
        search_query = claim
        if context:
            search_query = f"{claim} {context}"
        results = await self.search(search_query, num_results=3)

        if not results:
            return {"verified": None, "note": "无法联网验证", "sources": []}

        return {
            "verified": None,  # Not auto-verified; human or LLM should interpret
            "sources": results,
            "search_query": search_query,
            "note": "以下搜索结果供参考，不直接修改评分",
        }

    async def close(self):
        if self._client:
            await self._client.aclose()
            self._client = None

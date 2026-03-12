"""
Web Search Tool — Agentium

Provides web search capability to agents via the tool registry.
Follows the same class/singleton/return-shape pattern as all other tools
(http_api_tool, embedding_tool, git_tool, etc.).

Provider priority (auto mode):
  1. Tavily   — purpose-built for AI agents      (TAVILY_API_KEY)
  2. Brave    — privacy-respecting, fast          (BRAVE_SEARCH_API_KEY)
  3. SerpAPI  — Google results                   (SERPAPI_KEY)
  4. DuckDuckGo — zero-config scraping fallback  (always available)

Each provider is tried in order; the first successful response is returned.
If all API providers fail, DuckDuckGo scraping via httpx is used as the
final fallback — no Playwright / BrowserService dependency required.

Redis caching (TTL: 5 min) is applied when Redis is reachable. Cache misses
are silent so the tool always falls through to a live search.

Return shape (success):
    {
        "status":        "success",
        "query":         str,
        "provider":      str,          # which provider responded
        "cached":        bool,
        "result_count":  int,
        "results": [
            {
                "index":   int,        # 0-based, used for citations
                "title":   str,
                "url":     str,
                "snippet": str,
            },
            ...
        ]
    }

Return shape (error):
    {
        "status": "error",
        "error":  str,
    }

Place this file at: backend/tools/web_search_tool.py
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import time
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────

_CACHE_TTL_SECONDS = 300          # 5 minutes
_DEFAULT_MAX_RESULTS = 5
_MAX_RESULTS_LIMIT   = 10
_REQUEST_TIMEOUT     = 12.0       # seconds — keeps agents responsive

_PROVIDER_PRIORITY = ["tavily", "brave", "serpapi", "duckduckgo"]

_DDG_HTML_URL = "https://html.duckduckgo.com/html/"
_DDG_HEADERS  = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}


# ─────────────────────────────────────────────────────────────────────────────
# Redis cache helpers  (fail-silent — no hard dependency)
# ─────────────────────────────────────────────────────────────────────────────

def _cache_key(query: str, max_results: int) -> str:
    digest = hashlib.sha256(f"{query.strip().lower()}:{max_results}".encode()).hexdigest()[:16]
    return f"agentium:web_search:{digest}"


def _cache_get(key: str) -> Optional[Dict]:
    try:
        import redis as _redis
        url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
        r = _redis.from_url(url, decode_responses=True, socket_timeout=1)
        raw = r.get(key)
        return json.loads(raw) if raw else None
    except Exception:
        return None


def _cache_set(key: str, data: Dict) -> None:
    try:
        import redis as _redis
        url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
        r = _redis.from_url(url, decode_responses=True, socket_timeout=1)
        r.setex(key, _CACHE_TTL_SECONDS, json.dumps(data))
    except Exception:
        pass  # Cache is best-effort; never block a search result


# ─────────────────────────────────────────────────────────────────────────────
# Provider implementations  (pure async functions, no state)
# ─────────────────────────────────────────────────────────────────────────────

async def _tavily(query: str, max_results: int, api_key: str) -> List[Dict]:
    async with httpx.AsyncClient(timeout=_REQUEST_TIMEOUT) as client:
        resp = await client.post(
            "https://api.tavily.com/search",
            json={
                "api_key":      api_key,
                "query":        query,
                "max_results":  max_results,
                "search_depth": "basic",
                "include_answer":      False,
                "include_raw_content": False,
            },
        )
        resp.raise_for_status()
        data = resp.json()

    return [
        {
            "index":   i,
            "title":   r.get("title", ""),
            "url":     r.get("url",   ""),
            "snippet": r.get("content", r.get("snippet", "")),
        }
        for i, r in enumerate(data.get("results", [])[:max_results])
    ]


async def _brave(query: str, max_results: int, api_key: str) -> List[Dict]:
    async with httpx.AsyncClient(timeout=_REQUEST_TIMEOUT) as client:
        resp = await client.get(
            "https://api.search.brave.com/res/v1/web/search",
            headers={
                "Accept":                "application/json",
                "Accept-Encoding":       "gzip",
                "X-Subscription-Token":  api_key,
            },
            params={"q": query, "count": max_results, "safesearch": "moderate"},
        )
        resp.raise_for_status()
        data = resp.json()

    return [
        {
            "index":   i,
            "title":   r.get("title",       ""),
            "url":     r.get("url",         ""),
            "snippet": r.get("description", ""),
        }
        for i, r in enumerate(
            data.get("web", {}).get("results", [])[:max_results]
        )
    ]


async def _serpapi(query: str, max_results: int, api_key: str) -> List[Dict]:
    async with httpx.AsyncClient(timeout=_REQUEST_TIMEOUT) as client:
        resp = await client.get(
            "https://serpapi.com/search",
            params={
                "engine":  "google",
                "q":       query,
                "api_key": api_key,
                "num":     max_results,
            },
        )
        resp.raise_for_status()
        data = resp.json()

    return [
        {
            "index":   i,
            "title":   r.get("title",   ""),
            "url":     r.get("link",    ""),
            "snippet": r.get("snippet", ""),
        }
        for i, r in enumerate(data.get("organic_results", [])[:max_results])
    ]


async def _duckduckgo(query: str, max_results: int) -> List[Dict]:
    """
    Lightweight DuckDuckGo HTML scraper — no Playwright required.

    Tries BrowserService first (already initialised in the app) so the
    existing Playwright instance is reused when available. Falls back
    to a plain httpx POST to the DDG HTML endpoint.
    """
    # ── Attempt 1: reuse existing BrowserService (no extra overhead) ──────────
    try:
        from backend.services.browser_service import get_browser_service
        svc = get_browser_service()
        if svc._initialized:
            result = await svc.search(
                query, agent_id="web_search_tool", max_results=max_results
            )
            if result.success and result.results:
                return [
                    {
                        "index":   i,
                        "title":   r.title,
                        "url":     r.url,
                        "snippet": r.snippet,
                    }
                    for i, r in enumerate(result.results)
                ]
    except Exception as exc:
        logger.debug("web_search: BrowserService path failed (%s), using httpx", exc)

    # ── Attempt 2: httpx POST (no browser dependency) ─────────────────────────
    async with httpx.AsyncClient(
        timeout=_REQUEST_TIMEOUT,
        follow_redirects=True,
        headers=_DDG_HEADERS,
    ) as client:
        resp = await client.post(
            _DDG_HTML_URL,
            data={"q": query, "b": "", "kl": "us-en"},
        )
        resp.raise_for_status()
        html = resp.text

    # Simple regex extraction — avoids an extra BeautifulSoup dependency
    # DDG HTML structure: <a class="result__a" href="...">title</a>
    #                     <a class="result__snippet">snippet</a>
    title_pattern   = re.compile(r'class="result__a"[^>]*href="([^"]*)"[^>]*>(.*?)</a>', re.S)
    snippet_pattern = re.compile(r'class="result__snippet"[^>]*>(.*?)</a>', re.S)

    titles   = title_pattern.findall(html)
    snippets = snippet_pattern.findall(html)

    results = []
    for i, (url, title) in enumerate(titles[:max_results]):
        snippet = snippets[i] if i < len(snippets) else ""
        results.append({
            "index":   i,
            "title":   re.sub(r"<[^>]+>", "", title).strip(),
            "url":     url.strip(),
            "snippet": re.sub(r"<[^>]+>", "", snippet).strip(),
        })

    return results


# ─────────────────────────────────────────────────────────────────────────────
# Main Tool Class
# ─────────────────────────────────────────────────────────────────────────────

class WebSearchTool:
    """
    Web search tool for Agentium agents.

    Registered in ToolRegistry as "web_search".
    All agent tiers (0xxxx – 6xxxx) are authorised.

    The tool reads API keys from environment variables at call-time so keys
    added after startup are picked up without a restart.
    """

    TOOL_NAME         = "web_search"
    TOOL_DESCRIPTION  = (
        "Search the web for current information. "
        "Use when you need up-to-date news, documentation, facts, or any "
        "information that may be beyond your training knowledge. "
        "Returns ranked results with title, URL, and a text snippet for each. "
        "Results are indexed (0, 1, 2 …) for easy citation."
    )
    AUTHORIZED_TIERS  = [
        "0xxxx", "1xxxx", "2xxxx", "3xxxx", "4xxxx", "5xxxx", "6xxxx",
    ]

    # ── Public entry point ────────────────────────────────────────────────────

    async def execute(
        self,
        query:       str,
        max_results: int = _DEFAULT_MAX_RESULTS,
        provider:    str = "auto",
        **_kwargs: Any,
    ) -> Dict[str, Any]:
        """
        Execute a web search.

        Args:
            query:       Natural language search query.
            max_results: How many results to return (1–10, default 5).
            provider:    "auto" | "tavily" | "brave" | "serpapi" | "duckduckgo".
                         "auto" tries providers in priority order.

        Returns:
            {"status": "success", "results": [...], "provider": str, ...}
            {"status": "error",   "error": str}
        """
        query = (query or "").strip()
        if not query:
            return {"status": "error", "error": "query must not be empty"}

        max_results = max(1, min(_MAX_RESULTS_LIMIT, int(max_results)))

        # ── Cache check ───────────────────────────────────────────────────────
        ckey   = _cache_key(query, max_results)
        cached = _cache_get(ckey)
        if cached:
            cached["cached"] = True
            logger.debug("web_search: cache hit for %r", query)
            return cached

        # ── Provider order ────────────────────────────────────────────────────
        if provider == "auto":
            order = _PROVIDER_PRIORITY
        elif provider in _PROVIDER_PRIORITY:
            order = [provider, "duckduckgo"]  # always keep DDG as final fallback
        else:
            logger.warning("web_search: unknown provider %r — using auto", provider)
            order = _PROVIDER_PRIORITY

        # ── Try providers in order ────────────────────────────────────────────
        start          = time.monotonic()
        last_error     = "no providers attempted"
        results        = []
        provider_used  = "none"

        for pname in order:
            try:
                results = await self._call_provider(pname, query, max_results)
                provider_used = pname
                break
            except Exception as exc:
                last_error = f"{pname}: {exc}"
                logger.warning("web_search: provider %s failed — %s", pname, exc)

        latency_ms = int((time.monotonic() - start) * 1000)

        if not results:
            return {
                "status": "error",
                "error":  f"All providers failed. Last error: {last_error}",
            }

        output = {
            "status":       "success",
            "query":        query,
            "provider":     provider_used,
            "cached":       False,
            "latency_ms":   latency_ms,
            "result_count": len(results),
            "results":      results,
        }

        _cache_set(ckey, output)
        logger.info(
            "web_search: query=%r provider=%s results=%d latency=%dms",
            query, provider_used, len(results), latency_ms,
        )
        return output

    # ── Internal dispatch ─────────────────────────────────────────────────────

    async def _call_provider(
        self, provider: str, query: str, max_results: int
    ) -> List[Dict]:
        """Dispatch to the correct provider function."""
        if provider == "tavily":
            key = os.environ.get("TAVILY_API_KEY", "")
            if not key:
                raise ValueError("TAVILY_API_KEY not set")
            return await _tavily(query, max_results, key)

        if provider == "brave":
            key = os.environ.get("BRAVE_SEARCH_API_KEY", "")
            if not key:
                raise ValueError("BRAVE_SEARCH_API_KEY not set")
            return await _brave(query, max_results, key)

        if provider == "serpapi":
            key = os.environ.get("SERPAPI_KEY", "")
            if not key:
                raise ValueError("SERPAPI_KEY not set")
            return await _serpapi(query, max_results, key)

        if provider == "duckduckgo":
            return await _duckduckgo(query, max_results)

        raise ValueError(f"Unknown provider: {provider!r}")


# ─────────────────────────────────────────────────────────────────────────────
# Singletons
# ─────────────────────────────────────────────────────────────────────────────

web_search_tool = WebSearchTool()

# Required by ToolFactory.load_tool() dynamic loader (same as other tools)
tool_instance = web_search_tool
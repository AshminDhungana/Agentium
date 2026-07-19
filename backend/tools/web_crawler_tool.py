"""Web Crawler Tool — depth-limited, polite multi-page web crawling.

Extends the single-shot `web_fetch` tool with link traversal: it fetches a
start URL, extracts same-domain (or allow-listed) links, and follows them up to
a depth and page budget. Crawling is *polite* by default: it honors robots.txt
(`Disallow`/`Allow`), rate-limits requests, and never touches private/loopback
hosts (SSRF guard reused from `web_fetch_tool`).

Reuses the markdown extraction and SSRF helpers from `backend.tools.web_fetch_tool`
so crawling and fetching share one code path. Read-mostly and safe, so it is
registered for every agent tier (0xxxx–9xxxx).

A companion skill at backend/.agentium/skills/web_crawling/SKILL.md documents
this tool and is indexed into ChromaDB by `make seed-skills`; the `help` action
and the tool description both point agents at that skill file.
"""
from __future__ import annotations

import asyncio
import logging
import re
import time
from collections import deque
from html.parser import HTMLParser
from typing import Any, Deque, Dict, List, Optional, Set
from urllib.parse import urljoin, urlparse

import httpx

from backend.tools.web_fetch_tool import (
    _extract_markdown,
    _extract_pdf,
    _is_blocked_host,
)

logger = logging.getLogger(__name__)

SKILL_PATH = "backend/.agentium/skills/web_crawling/SKILL.md"

_DEFAULT_MAX_TOKENS = 2000
_DEFAULT_MAX_DEPTH = 1
_DEFAULT_MAX_PAGES = 20
_DEFAULT_RATE_LIMIT_MS = 200
_REQUEST_TIMEOUT = 15.0
_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 "
    "(AgentiumBot/1.0; +https://example.com/bot)"
)
_MAX_REDIRECT_HOPS = 6


def _estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


class _LinkExtractor(HTMLParser):
    """Collect absolute http(s) hrefs from an HTML document."""

    def __init__(self, base_url: str) -> None:
        super().__init__()
        self.base_url = base_url
        self.links: List[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag.lower() != "a":
            return
        for name, value in attrs:
            if name.lower() == "href" and value:
                self.links.append(value)
                break

    def normalized(self) -> List[str]:
        out: List[str] = []
        for raw in self.links:
            low = raw.lower().strip()
            if low.startswith(("mailto:", "tel:", "javascript:", "#", "data:")):
                continue
            abs_url = urljoin(self.base_url, raw).split("#")[0]
            p = urlparse(abs_url)
            if p.scheme in ("http", "https") and p.netloc:
                out.append(abs_url)
        return out


class WebCrawlerTool:
    """Agent-facing depth-limited, robots-respecting web crawler."""

    TOOL_NAME = "web_crawler"

    def __init__(self) -> None:
        self._client = None
        self._robots_cache: Dict[str, Optional["_RobotsRules"]] = {}

    @property
    def client(self):
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=_REQUEST_TIMEOUT, headers={"User-Agent": _USER_AGENT}
            )
        return self._client

    # ── Public entry point ────────────────────────────────────────────────────

    async def execute(self, action: str, **kwargs) -> Dict[str, Any]:
        if action == "help":
            return self._help()
        if action != "crawl":
            return {"status": "error", "error": f"Unknown action: {action}"}

        url = (kwargs.get("url") or "").strip()
        if not url:
            return {"status": "error", "error": "url is required"}
        if not url.startswith(("http://", "https://")):
            return {"status": "error", "error": "url must start with http:// or https://"}

        try:
            max_depth = int(kwargs.get("max_depth", _DEFAULT_MAX_DEPTH))
            max_pages = int(kwargs.get("max_pages", _DEFAULT_MAX_PAGES))
            max_tokens = int(kwargs.get("max_tokens", _DEFAULT_MAX_TOKENS))
            rate_limit_ms = int(kwargs.get("rate_limit_ms", _DEFAULT_RATE_LIMIT_MS))
        except (ValueError, TypeError):
            return {"status": "error", "error": "max_depth/max_pages/max_tokens/rate_limit_ms must be ints"}
        if max_depth < 0:
            max_depth = _DEFAULT_MAX_DEPTH
        if max_pages < 1:
            max_pages = _DEFAULT_MAX_PAGES

        stay_on_domain = bool(kwargs.get("stay_on_domain", True))
        respect_robots = bool(kwargs.get("respect_robots", True))
        use_cache = bool(kwargs.get("use_cache", True))
        allowed_domains: List[str] = kwargs.get("allowed_domains") or []

        start_host = urlparse(url).hostname or ""
        if _is_blocked_host(start_host):
            return {"status": "error", "error": "host not allowed (SSRF guard)"}

        return await self._crawl(
            start_url=url,
            start_host=start_host.lower(),
            max_depth=max_depth,
            max_pages=max_pages,
            max_tokens=max_tokens,
            rate_limit_ms=rate_limit_ms,
            stay_on_domain=stay_on_domain,
            respect_robots=respect_robots,
            use_cache=use_cache,
            allowed_domains=[d.lower() for d in allowed_domains],
        )

    # ── Crawl engine (breadth-first, depth-limited) ───────────────────────────

    async def _crawl(
        self,
        start_url: str,
        start_host: str,
        max_depth: int,
        max_pages: int,
        max_tokens: int,
        rate_limit_ms: int,
        stay_on_domain: bool,
        respect_robots: bool,
        use_cache: bool,
        allowed_domains: List[str],
    ) -> Dict[str, Any]:
        visited: Set[str] = set()
        queued: Deque[tuple] = deque()
        queued.append((start_url, 0))
        pages: List[Dict[str, Any]] = []
        failed: List[Dict[str, str]] = []
        depth_reached = 0
        started = time.monotonic()

        while queued and len(pages) + len(failed) < max_pages:
            current_url, depth = queued.popleft()
            if current_url in visited:
                continue
            visited.add(current_url)
            if respect_robots and not await self._robots_allows(current_url, use_cache):
                failed.append({"url": current_url, "error": "robots.txt disallow"})
                continue

            host = (urlparse(current_url).hostname or "").lower()
            if not self._host_allowed(host, start_host, stay_on_domain, allowed_domains):
                failed.append({"url": current_url, "error": "domain not allowed"})
                continue

            page = await self._fetch_page(current_url, max_tokens, use_cache)
            if page["status"] == "error":
                failed.append({"url": current_url, "error": page["error"]})
            else:
                pages.append(page)
                depth_reached = max(depth_reached, depth)
                if depth < max_depth:
                    for link in page.get("_links", []):
                        if link not in visited:
                            queued.append((link, depth + 1))

            # Politeness: rate-limit between requests.
            if rate_limit_ms > 0 and queued:
                await asyncio.sleep(rate_limit_ms / 1000.0)

        duration_ms = int((time.monotonic() - started) * 1000)
        return {
            "status": "success",
            "start_url": start_url,
            "pages_fetched": len(pages),
            "pages_failed": len(failed),
            "max_depth": max_depth,
            "depth_reached": depth_reached,
            "duration_ms": duration_ms,
            "pages": pages,
            "failed": failed,
        }

    # ── Per-page fetch (reuses web_fetch extraction + SSRF guard) ──────────────

    async def _fetch_page(self, url: str, max_tokens: int, use_cache: bool) -> Dict[str, Any]:
        parsed = urlparse(url)
        if _is_blocked_host(parsed.hostname):
            return {"status": "error", "error": "host not allowed (SSRF guard)"}

        current_url = url
        resp = None
        for _hop in range(_MAX_REDIRECT_HOPS):
            try:
                resp = await self.client.get(current_url, follow_redirects=False)
            except Exception as exc:  # noqa: BLE001
                return {"status": "error", "error": f"fetch failed: {exc}"}
            if resp.status_code >= 400:
                return {"status": "error", "error": f"HTTP {resp.status_code}"}
            loc = resp.headers.get("location")
            if 300 <= resp.status_code < 400 and loc:
                next_url = urljoin(current_url, loc)
                nxt = urlparse(next_url)
                if _is_blocked_host(nxt.hostname):
                    return {"status": "error", "error": "host not allowed (SSRF guard)"}
                current_url = next_url
                continue
            break
        if resp is None or 300 <= resp.status_code < 400:
            return {"status": "error", "error": "too many redirects or blocked redirect"}

        ctype = resp.headers.get("content-type", "").lower()
        if "pdf" in ctype or url.lower().endswith(".pdf"):
            markdown = _extract_pdf(resp.content)
            if not markdown:
                return {"status": "error", "error": "PDF extraction unavailable"}
        else:
            markdown = _extract_markdown(resp.text, current_url)

        title = ""
        m = re.search(r"<title[^>]*>(.*?)</title>", resp.text, re.IGNORECASE | re.DOTALL)
        if m:
            title = m.group(1).strip()

        token_count = _estimate_tokens(markdown)
        truncated = False
        if token_count > max_tokens:
            markdown = markdown[: max_tokens * 4]
            token_count = _estimate_tokens(markdown)
            truncated = True

        links = _LinkExtractor(current_url)
        try:
            links.feed(resp.text)
        except Exception:  # noqa: BLE001
            pass

        return {
            "status": "success",
            "url": current_url,
            "title": title,
            "markdown": markdown,
            "token_count": token_count,
            "truncated": truncated,
            "_links": links.normalized(),
        }

    # ── Domain gating ─────────────────────────────────────────────────────────

    @staticmethod
    def _host_allowed(host: str, start_host: str, stay_on_domain: bool, allowed: List[str]) -> bool:
        if not host:
            return False
        # The crawl origin is always permitted, even when an allow-list narrows
        # the set of *followed* links.
        if host == start_host or host.endswith("." + start_host):
            return True
        if allowed:
            return any(host == d or host.endswith("." + d) for d in allowed)
        if stay_on_domain:
            return host == start_host or host.endswith("." + start_host)
        return True

    # ── robots.txt handling ───────────────────────────────────────────────────

    async def _robots_allows(self, url: str, use_cache: bool) -> bool:
        parsed = urlparse(url)
        origin = f"{parsed.scheme}://{parsed.netloc}"
        if origin not in self._robots_cache:
            self._robots_cache[origin] = await self._load_robots(origin, use_cache)
        rules = self._robots_cache[origin]
        if rules is None:
            return True  # no robots.txt → allow
        return rules.is_allowed(parsed.path or "/")

    async def _load_robots(self, origin: str, use_cache: bool) -> Optional["_RobotsRules"]:
        robots_url = f"{origin}/robots.txt"
        try:
            resp = await self.client.get(robots_url, follow_redirects=True, timeout=_REQUEST_TIMEOUT)
            if resp.status_code != 200:
                return None
            return _RobotsRules(resp.text)
        except Exception:  # noqa: BLE001
            return None

    # ── Help ──────────────────────────────────────────────────────────────────

    def _help(self):
        return {
            "status": "success",
            "tool": self.TOOL_NAME,
            "skill_file": SKILL_PATH,
            "actions": {
                "crawl": (
                    "Depth-limited crawl. Params: url (str, required), max_depth (int=1), "
                    "max_pages (int=20), max_tokens (int=2000, per-page budget), "
                    "stay_on_domain (bool=true), allowed_domains (list|optional), "
                    "respect_robots (bool=true), rate_limit_ms (int=200, delay between "
                    "requests), use_cache (bool=true)."
                ),
                "help": "Show this message.",
            },
            "help": (
                "The 'web_crawler' tool fetches a page and follows its links up to a depth "
                "and page budget, returning each page as clean Markdown. It honors "
                "robots.txt, rate-limits requests, and blocks private hosts (SSRF guard). "
                "Full usage, best practices, and a reference list of ~100 major websites "
                "by category are in the skill file at backend/.agentium/skills/web_crawling/"
                "SKILL.md (and its datasets/major_sites.md). That skill is indexed into "
                "ChromaDB via `make seed-skills`, so you can also retrieve it semantically "
                "by asking 'what site should I use to look up X'."
            ),
        }


class _RobotsRules:
    """Minimal robots.txt parser — supports Disallow/Allow for our bot."""

    def __init__(self, text: str) -> None:
        self.allows: List[str] = []
        self.disallows: List[str] = []
        self._parse(text)

    def _parse(self, text: str) -> None:
        in_scope = False
        for line in text.splitlines():
            line = line.split("#", 1)[0].strip()
            if not line:
                continue
            if ":" not in line:
                continue
            key, _, val = line.partition(":")
            key = key.strip().lower()
            val = val.strip()
            if key == "user-agent":
                # Apply rules under any wildcard or our explicit bot token.
                in_scope = val == "*" or "agentium" in val.lower() or "bot" in val.lower()
            elif in_scope and key == "disallow":
                if val:
                    self.disallows.append(val)
            elif in_scope and key == "allow":
                if val:
                    self.allows.append(val)

    def is_allowed(self, path: str) -> bool:
        for allow in self.allows:
            if path.startswith(allow):
                return True
        for disallow in self.disallows:
            if disallow == "/" or path.startswith(disallow):
                return False
        return True


web_crawler_tool = WebCrawlerTool()


async def execute(action: str, **kwargs) -> Dict[str, Any]:
    """Module-level entry point — delegates to the singleton instance.

    Unit tests monkeypatch the singleton's `_client` (via
    `backend.tools.web_crawler_tool`), which the instance reads, so this shim
    keeps a flat `execute` while preserving that wiring.
    """
    return await web_crawler_tool.execute(action, **kwargs)


# Required by ToolFactory.load_tool() dynamic loader (same as other tools)
tool_instance = web_crawler_tool

"""Web Fetch Tool — retrieve a URL's content as clean Markdown.

Distinct from web_search (which returns result lists). Returns truncated
Markdown + metadata + token count. Lazy httpx client; optional extraction
libs (trafilatura / markdownify / pypdf) import-guarded; Redis cache is
fail-silent. All failures return {"status":"error"} — never raise into the
agent context. Registered in ToolRegistry as "web_fetch".
"""
from __future__ import annotations

import hashlib
import logging
import re
from typing import Any, Dict, Optional

import httpx

logger = logging.getLogger(__name__)

_CACHE_TTL_SECONDS = 300
_DEFAULT_MAX_TOKENS = 4000
_REQUEST_TIMEOUT = 12.0
_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


def _estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


_extract = None  # set to _extract_markdown below; monkeypatchable at module level

_client = None   # module-level httpx client (lazy); monkeypatchable at module level


def _extract_markdown(html: str, url: str) -> str:
    try:
        import trafilatura  # type: ignore
        extracted = trafilatura.extract(html, url=url)
        if extracted:
            return extracted
    except Exception:
        pass
    try:
        import markdownify  # type: ignore
        return markdownify.markdownify(html)
    except Exception:
        pass
    # last-resort: strip tags
    return re.sub(r"<[^>]+>", "", html)


_extract = _extract_markdown  # module-level extractor; monkeypatchable in tests


def _extract_pdf(payload: bytes) -> str:
    try:
        from pypdf import PdfReader  # type: ignore
        reader = PdfReader(__import__("io").BytesIO(payload))
        return "\n".join((p.extract_text() or "") for p in reader.pages)
    except Exception:
        return ""


class WebFetchTool:
    TOOL_NAME = "web_fetch"
    AUTHORIZED_TIERS = [f"{i}xxxx" for i in range(10)]

    def __init__(self) -> None:
        self._redis = None

    @property
    def client(self):
        global _client
        if _client is None:
            _client = httpx.AsyncClient(
                timeout=_REQUEST_TIMEOUT, headers={"User-Agent": _USER_AGENT}
            )
        return _client

    def _cache_key(self, url: str, max_tokens: int) -> str:
        digest = hashlib.sha256(f"{url.strip().lower()}:{max_tokens}".encode()).hexdigest()[:16]
        return f"agentium:web_fetch:{digest}"

    def _get_cache(self, key: str) -> Optional[str]:
        try:
            import redis  # type: ignore
            if self._redis is None:
                from backend.core.config import settings
                self._redis = redis.from_url(settings.REDIS_URL)
            val = self._redis.get(key)
            return val.decode() if val else None
        except Exception:
            return None

    def _set_cache(self, key: str, value: str) -> None:
        try:
            if self._redis is None:
                from backend.core.config import settings
                import redis  # type: ignore
                self._redis = redis.from_url(settings.REDIS_URL)
            self._redis.set(key, value, ex=_CACHE_TTL_SECONDS)
        except Exception:
            pass

    async def execute(self, action: str, **kwargs) -> Dict[str, Any]:
        if action == "help":
            return {
                "status": "success",
                "description": (
                    "Fetch a URL and return its content as clean Markdown with a token "
                    "budget. Full reference in backend/.agentium/skills/web_fetch/SKILL.md."
                ),
            }
        if action != "fetch":
            return {"status": "error", "error": f"Unknown action: {action}"}

        url = (kwargs.get("url") or "").strip()
        if not url:
            return {"status": "error", "error": "url is required"}
        try:
            max_tokens = int(kwargs.get("max_tokens", _DEFAULT_MAX_TOKENS))
        except (ValueError, TypeError):
            max_tokens = _DEFAULT_MAX_TOKENS
        allowed = kwargs.get("allowed_domains") or []
        use_cache = bool(kwargs.get("use_cache", True))

        if allowed:
            host = re.sub(r"^https?://", "", url).split("/")[0].lower()
            if not any(host == d.lower() or host.endswith("." + d.lower()) for d in allowed):
                return {"status": "error", "error": f"domain not allowed: {host}"}

        cache_key = self._cache_key(url, max_tokens)
        if use_cache:
            cached = self._get_cache(cache_key)
            if cached is not None:
                return {
                    "status": "success", "url": url, "title": "",
                    "markdown": cached, "token_count": _estimate_tokens(cached),
                    "cached": True, "truncated": False,
                }

        try:
            resp = await self.client.get(url, follow_redirects=True)
        except Exception as exc:
            return {"status": "error", "error": f"fetch failed: {exc}"}
        if resp.status_code >= 400:
            return {"status": "error", "error": f"HTTP {resp.status_code}"}

        ctype = resp.headers.get("content-type", "").lower()
        if "pdf" in ctype or url.lower().endswith(".pdf"):
            markdown = _extract_pdf(resp.content)
            if not markdown:
                return {"status": "error", "error": "PDF extraction unavailable"}
        else:
            markdown = (_extract or _extract_markdown)(resp.text, url)

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

        if use_cache:
            self._set_cache(cache_key, markdown)
        return {
            "status": "success", "url": url, "title": title,
            "markdown": markdown, "token_count": token_count,
            "cached": False, "truncated": truncated,
        }


web_fetch_tool = WebFetchTool()


async def execute(action: str, **kwargs) -> Dict[str, Any]:
    """Module-level entry point — delegates to the singleton.

    The unit tests monkeypatch the module-level `_client` and `_extract`
    attributes, which the singleton reads, so this shim keeps that wiring
    intact while exposing a flat `execute`.
    """
    return await web_fetch_tool.execute(action, **kwargs)


# Required by ToolFactory.load_tool() dynamic loader (same as other tools)
tool_instance = web_fetch_tool

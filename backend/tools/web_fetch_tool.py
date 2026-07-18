"""Web Fetch Tool — retrieve a URL's content as clean Markdown.

Distinct from web_search (which returns result lists). Returns truncated
Markdown + metadata + token count. Lazy httpx client; optional extraction
libs (trafilatura / markdownify / pypdf) import-guarded; Redis cache is
fail-silent. All failures return {"status":"error"} — never raise into the
agent context. Registered in ToolRegistry as "web_fetch".
"""
from __future__ import annotations

import hashlib
import ipaddress
import logging
import re
import socket
from typing import Any, Dict, Optional
from urllib.parse import urljoin, urlparse

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


def _is_blocked_host(host: str) -> bool:
    """SSRF guard: reject private/loopback/link-local/reserved/metadata hosts.

    Checks both the literal host (if an IP) and any resolved IP via DNS.
    Also blocks localhost / *.local / *.internal style names.
    """
    if not host:
        return True
    # urlparse().hostname already strips IPv6 brackets and any :port. We only
    # defensively strip stray brackets here — splitting on ":" would corrupt
    # IPv6 addresses (e.g. fd00::1 -> fd00) and let private ranges bypass.
    host = host.strip().strip("[]")
    if not host:
        return True
    low = host.lower()
    if low == "localhost" or low.endswith(".local") or low.endswith(".internal"):
        return True
    try:
        ip = ipaddress.ip_address(host)
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or str(ip) == "169.254.169.254"
        ):
            return True
    except ValueError:
        pass
    # DNS resolution check (best-effort)
    try:
        resolved = socket.gethostbyname(host)
        ip = ipaddress.ip_address(resolved)
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or str(ip) == "169.254.169.254"
        ):
            return True
    except Exception:
        pass
    return False


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
        self._client = None
        self._extract = _extract_markdown

    @property
    def client(self):
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=_REQUEST_TIMEOUT, headers={"User-Agent": _USER_AGENT}
            )
        return self._client

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
            host = re.sub(r"^https?://", "", url).split("/")[0].split(":")[0].lower()
            if not any(host == d.lower() or host.endswith("." + d.lower()) for d in allowed):
                return {"status": "error", "error": f"domain not allowed: {host}"}

        # SSRF guard: reject internal/metadata hosts before any network call
        parsed = urlparse(url)
        if _is_blocked_host(parsed.hostname):
            return {"status": "error", "error": "host not allowed (SSRF guard)"}

        cache_key = self._cache_key(url, max_tokens)
        if use_cache:
            cached = self._get_cache(cache_key)
            if cached is not None:
                return {
                    "status": "success", "url": url, "title": "",
                    "markdown": cached, "token_count": _estimate_tokens(cached),
                    "cached": True, "truncated": False,
                }

        # Fetch with bounded manual redirect following (no automatic redirects)
        current_url = url
        resp = None
        for _hop in range(6):
            try:
                resp = await self.client.get(current_url, follow_redirects=False)
            except Exception as exc:
                return {"status": "error", "error": f"fetch failed: {exc}"}
            if resp.status_code >= 400:
                return {"status": "error", "error": f"HTTP {resp.status_code}"}
            loc = resp.headers.get("location")
            if resp.status_code < 400 and resp.status_code >= 300 and loc:
                next_url = urljoin(current_url, loc)
                nxt = urlparse(next_url)
                if _is_blocked_host(nxt.hostname):
                    return {"status": "error", "error": "host not allowed (SSRF guard)"}
                current_url = next_url
                continue
            break
        if resp is None:
            return {"status": "error", "error": "fetch failed: no response"}
        # If the redirect loop exhausted its hops (or a 3xx had no location),
        # we never actually fetched content — don't fall through to success.
        if 300 <= resp.status_code < 400:
            return {"status": "error", "error": "too many redirects or blocked redirect"}

        ctype = resp.headers.get("content-type", "").lower()
        if "pdf" in ctype or url.lower().endswith(".pdf"):
            markdown = _extract_pdf(resp.content)
            if not markdown:
                return {"status": "error", "error": "PDF extraction unavailable"}
        else:
            markdown = self._extract(resp.text, url)

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
    """Module-level entry point — delegates to the singleton instance.

    The unit tests monkeypatch the singleton's `_client` and `_extract`
    instance attributes (via `backend.tools.web_fetch_tool`), which the
    instance reads, so this shim keeps a flat `execute` while preserving that
    wiring.
    """
    return await web_fetch_tool.execute(action, **kwargs)


# Required by ToolFactory.load_tool() dynamic loader (same as other tools)
tool_instance = web_fetch_tool

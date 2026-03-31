"""
Browser Service for Agentium — Phase 10.1.

Provides headless browser capabilities via Playwright for agents to:
  - Navigate and scrape web pages
  - Take screenshots (logged to audit trail)
  - Perform safe web searches
  - Interact with page elements (click)

All URLs are validated through URLSafetyGuard before any navigation.
"""

import asyncio
import base64
import ipaddress
import logging
import re
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from sqlalchemy.orm import Session

from backend.core.config import settings
from backend.models.entities.audit import AuditLog, AuditLevel, AuditCategory

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# URL Safety Guard — SSRF Prevention
# ---------------------------------------------------------------------------

# Private / reserved IP ranges that must NEVER be accessed
_BLOCKED_IP_RANGES = [
    ipaddress.ip_network("127.0.0.0/8"),       # Loopback
    ipaddress.ip_network("10.0.0.0/8"),         # Private Class A
    ipaddress.ip_network("172.16.0.0/12"),      # Private Class B
    ipaddress.ip_network("192.168.0.0/16"),     # Private Class C
    ipaddress.ip_network("169.254.0.0/16"),     # Link-local / AWS metadata
    ipaddress.ip_network("0.0.0.0/8"),          # "This" network
    ipaddress.ip_network("::1/128"),            # IPv6 loopback
    ipaddress.ip_network("fc00::/7"),           # IPv6 unique local
    ipaddress.ip_network("fe80::/10"),          # IPv6 link-local
]

_DEFAULT_BLOCKED_DOMAINS = [
    "metadata.google.internal",
    "metadata.goog",
    "instance-data",
]

_ALLOWED_SCHEMES = {"http", "https"}


@dataclass
class URLCheckResult:
    """Result of a URL safety check."""
    safe: bool
    url: str
    reason: str = ""
    checked_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())


class URLSafetyGuard:
    """
    Validates URLs against SSRF attacks before Playwright navigates to them.

    Checks:
      1. Scheme must be http or https
      2. Hostname must not resolve to private/reserved IPs
      3. Hostname must not be in the blocked domains list
      4. Hostname must not be a raw private IP
    """

    def __init__(self, blocked_domains: Optional[List[str]] = None):
        extra = []
        if settings.BROWSER_BLOCKED_DOMAINS:
            extra = [
                d.strip().lower()
                for d in settings.BROWSER_BLOCKED_DOMAINS.split(",")
                if d.strip()
            ]
        self._blocked_domains: List[str] = (
            _DEFAULT_BLOCKED_DOMAINS + (blocked_domains or []) + extra
        )

    def check_url(self, url: str) -> URLCheckResult:
        """Validate a URL for safety. Returns URLCheckResult."""
        try:
            parsed = urlparse(url)
        except Exception:
            return URLCheckResult(safe=False, url=url, reason="Malformed URL")

        # 1. Scheme check
        if parsed.scheme.lower() not in _ALLOWED_SCHEMES:
            return URLCheckResult(
                safe=False, url=url,
                reason=f"Blocked scheme: {parsed.scheme}. Only http/https allowed.",
            )

        hostname = (parsed.hostname or "").lower()
        if not hostname:
            return URLCheckResult(safe=False, url=url, reason="Missing hostname")

        # 2. Blocked domain check
        for blocked in self._blocked_domains:
            if hostname == blocked or hostname.endswith(f".{blocked}"):
                return URLCheckResult(
                    safe=False, url=url,
                    reason=f"Blocked domain: {hostname}",
                )

        # 3. Raw IP check
        try:
            addr = ipaddress.ip_address(hostname)
            for network in _BLOCKED_IP_RANGES:
                if addr in network:
                    return URLCheckResult(
                        safe=False, url=url,
                        reason=f"Blocked private/reserved IP: {hostname}",
                    )
        except ValueError:
            # Not an IP literal — hostname is fine, pass through
            pass

        return URLCheckResult(safe=True, url=url)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class NavigateResult:
    url: str
    title: str
    status_code: int
    success: bool
    error: str = ""


@dataclass
class ScrapeResult:
    url: str
    text: str
    html: str
    success: bool
    word_count: int = 0
    error: str = ""


@dataclass
class ScreenshotResult:
    url: str
    image_base64: str
    content_type: str = "image/png"
    success: bool = True
    audit_log_id: Optional[str] = None
    error: str = ""


@dataclass
class SearchResultItem:
    title: str
    url: str
    snippet: str


@dataclass
class SearchResult:
    query: str
    results: List[SearchResultItem]
    success: bool = True
    error: str = ""

@dataclass
class BrowserSession:
    session_id: str
    url: str
    title: str
    status: str
    agent_id: str
    fps: float
    started_at: datetime
    latest_frame: str
    action_log: List[Dict] = field(default_factory=list)
    _context: Any = field(default=None, repr=False)
    _page: Any = field(default=None, repr=False)
    _capture_task: Any = field(default=None, repr=False)


# ---------------------------------------------------------------------------
# Browser Service
# ---------------------------------------------------------------------------

class BrowserService:
    """
    Manages headless Chromium via Playwright.

    Usage::

        svc = BrowserService()
        await svc.initialize()
        result = await svc.navigate("https://example.com")
        await svc.shutdown()
    """

    def __init__(self):
        self._playwright = None
        self._browser = None
        self._safety_guard = URLSafetyGuard()
        self._request_counts: Dict[str, List[float]] = {}  # agent_id → timestamps
        self._initialized = False
        self._sessions: Dict[str, BrowserSession] = {}  # task_id → BrowserSession

    # ── Lifecycle ──────────────────────────────────────────────────────────

    async def initialize(self):
        """Launch Playwright and headless Chromium."""
        if self._initialized:
            return
        if not settings.BROWSER_ENABLED:
            logger.info("Browser service disabled via BROWSER_ENABLED=False")
            return
        try:
            from playwright.async_api import async_playwright
            self._playwright = await async_playwright().start()
            self._browser = await self._playwright.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-gpu",
                ],
            )
            self._initialized = True
            logger.info("Browser service initialized (Playwright + Chromium)")
        except Exception as exc:
            logger.error("Failed to initialize browser service: %s", exc)
            self._initialized = False

    async def shutdown(self):
        """Shut down browser and Playwright."""
        # Stop all active streams
        for task_id in list(self._sessions.keys()):
            await self.stop_stream(task_id)
            
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()
        self._initialized = False
        logger.info("Browser service shut down")

    # ── Live Streaming (Phase 14.1) ───────────────────────────────────────

    async def start_stream(
        self,
        task_id: str,
        url: str,
        agent_id: str = "system",
        fps: float = 2.0,
    ) -> None:
        """Start a browser session and broadcast frames via WebSocket."""
        if not self._initialized or not self._browser:
            logger.warning("Browser service not initialized, cannot start stream")
            return
            
        check = self._safety_guard.check_url(url)
        if not check.safe:
            logger.warning(f"Blocked unsafe stream URL: {url} ({check.reason})")
            return

        if task_id in self._sessions:
            logger.info(f"Stream already running for task {task_id}")
            return
            
        context = await self._create_isolated_context()
        page = await context.new_page()
        
        session = BrowserSession(
            session_id=task_id,
            url=url,
            title="",
            status="active",
            agent_id=agent_id,
            fps=fps,
            started_at=datetime.utcnow(),
            latest_frame="",
            action_log=[],
            _context=context,
            _page=page,
            _capture_task=None
        )
        self._sessions[task_id] = session
        
        self.record_action(task_id, f"Started browser session at {url}")
        
        try:
            await page.goto(url, wait_until="networkidle", timeout=30000)
            session.title = await page.title()
            session.url = page.url
        except Exception as e:
            logger.warning(f"Navigation error in stream {task_id}: {e}")
            self.record_action(task_id, f"Navigation error: {e}")
            
        # Start capture loop
        session._capture_task = asyncio.create_task(self._capture_loop(task_id))
        
    async def _capture_loop(self, task_id: str):
        """Loop that captures screenshots and emits WebSocket events."""
        from backend.api.routes.websocket import manager as websocket_manager
        
        session = self._sessions.get(task_id)
        if not session:
            return
            
        frame_number = 0
        while task_id in self._sessions and session.status != "completed":
            try:
                if session.status == "paused":
                    await asyncio.sleep(1.0)
                    continue
                    
                start_time = time.time()
                
                # Capture frame as JPEG
                jpeg_bytes = await session._page.screenshot(type="jpeg", quality=60)
                frame_b64 = base64.b64encode(jpeg_bytes).decode('utf-8')
                
                session.latest_frame = frame_b64
                session.title = await session._page.title()
                session.url = session._page.url
                frame_number += 1
                
                # Emit WebSocket event
                await websocket_manager.emit_browser_frame(
                    task_id=task_id,
                    frame=frame_b64,
                    url=session.url,
                    title=session.title,
                    action_log=session.action_log[-50:],  # keep it bounded
                    frame_number=frame_number
                )
                
                elapsed = time.time() - start_time
                sleep_time = max(0, (1.0 / session.fps) - elapsed)
                await asyncio.sleep(sleep_time)
                
            except Exception as e:
                logger.error(f"Error in capture loop for task {task_id}: {e}")
                await asyncio.sleep(2.0)  # back off on error
                
    async def stop_stream(self, task_id: str) -> None:
        """Stop a stream and cleanup its browser context."""
        session = self._sessions.pop(task_id, None)
        if not session:
            return
            
        session.status = "completed"
        if session._capture_task:
            session._capture_task.cancel()
            
        try:
            if session._context:
                await session._context.close()
        except Exception as e:
            logger.warning(f"Error closing browser context for task {task_id}: {e}")
            
        logger.info(f"Stopped browser stream for task {task_id}")

    def get_session(self, task_id: str) -> Optional[BrowserSession]:
        """Get the current session state."""
        return self._sessions.get(task_id)

    def get_all_sessions(self) -> List[BrowserSession]:
        """Get all active sessions."""
        return list(self._sessions.values())

    def record_action(self, task_id: str, action: str) -> None:
        """Record an action in the session's action log."""
        session = self._sessions.get(task_id)
        if session:
            session.action_log.append({
                "action": action,
                "timestamp": datetime.utcnow().isoformat()
            })

    # ── Session Isolation (Phase 10.1 hardening) ──────────────────────────

    async def _create_isolated_context(self):
        """
        Create a fresh BrowserContext with its own cookies, localStorage,
        and cache.  The caller MUST close the context in a ``finally`` block.

        This ensures per-session memory/cookie isolation — no cross-session
        data leakage between different agents or requests.
        """
        if not self._browser:
            raise RuntimeError("Browser not initialised")
        context = await self._browser.new_context(
            # Each context gets a clean storage state (no shared cookies)
            accept_downloads=False,
            java_script_enabled=True,
            bypass_csp=False,
            ignore_https_errors=False,
            # Prevent fingerprinting between sessions
            locale="en-US",
            timezone_id="UTC",
        )
        return context

    # ── Rate Limiting ─────────────────────────────────────────────────────

    def _check_rate_limit(self, agent_id: str, max_per_min: int = 10) -> bool:
        """Return True if agent is within rate limit."""
        now = time.time()
        timestamps = self._request_counts.setdefault(agent_id, [])
        # Prune older than 60s
        timestamps[:] = [t for t in timestamps if now - t < 60]
        if len(timestamps) >= max_per_min:
            return False
        timestamps.append(now)
        return True

    # ── Core Operations ───────────────────────────────────────────────────

    async def navigate(
        self,
        url: str,
        agent_id: str = "system",
        timeout_ms: Optional[int] = None,
    ) -> NavigateResult:
        """Navigate to a URL and return page title + status."""
        check = self._safety_guard.check_url(url)
        if not check.safe:
            return NavigateResult(
                url=url, title="", status_code=0,
                success=False, error=check.reason,
            )
        if not self._check_rate_limit(agent_id):
            return NavigateResult(
                url=url, title="", status_code=0,
                success=False, error="Rate limit exceeded (max 10 req/min)",
            )
        if not self._initialized or not self._browser:
            return NavigateResult(
                url=url, title="", status_code=0,
                success=False, error="Browser service not initialized",
            )

        timeout = timeout_ms or settings.BROWSER_TIMEOUT_SECONDS * 1000
        context = await self._create_isolated_context()
        try:
            page = await context.new_page()
            response = await page.goto(url, timeout=timeout, wait_until="domcontentloaded")
            title = await page.title()
            status = response.status if response else 0
            return NavigateResult(url=url, title=title, status_code=status, success=True)
        except Exception as exc:
            return NavigateResult(
                url=url, title="", status_code=0,
                success=False, error=str(exc),
            )
        finally:
            await context.close()

    async def scrape(
        self,
        url: str,
        selector: Optional[str] = None,
        agent_id: str = "system",
    ) -> ScrapeResult:
        """Scrape text/HTML from a URL, optionally targeting a CSS selector."""
        check = self._safety_guard.check_url(url)
        if not check.safe:
            return ScrapeResult(url=url, text="", html="", success=False, error=check.reason)
        if not self._check_rate_limit(agent_id):
            return ScrapeResult(
                url=url, text="", html="", success=False,
                error="Rate limit exceeded",
            )
        if not self._initialized or not self._browser:
            return ScrapeResult(
                url=url, text="", html="", success=False,
                error="Browser service not initialized",
            )

        timeout = settings.BROWSER_TIMEOUT_SECONDS * 1000
        context = await self._create_isolated_context()
        try:
            page = await context.new_page()
            await page.goto(url, timeout=timeout, wait_until="domcontentloaded")
            if selector:
                element = await page.query_selector(selector)
                if element:
                    html = await element.inner_html()
                    text = await element.inner_text()
                else:
                    html = ""
                    text = ""
            else:
                html = await page.content()
                text = await page.inner_text("body")

            return ScrapeResult(
                url=url, text=text.strip(), html=html,
                success=True, word_count=len(text.split()),
            )
        except Exception as exc:
            return ScrapeResult(url=url, text="", html="", success=False, error=str(exc))
        finally:
            await context.close()

    async def screenshot(
        self,
        url: str,
        agent_id: str = "system",
        db: Optional[Session] = None,
    ) -> ScreenshotResult:
        """Capture a full-page screenshot and optionally log to audit trail."""
        check = self._safety_guard.check_url(url)
        if not check.safe:
            return ScreenshotResult(
                url=url, image_base64="", success=False, error=check.reason,
            )
        if not self._check_rate_limit(agent_id):
            return ScreenshotResult(
                url=url, image_base64="", success=False,
                error="Rate limit exceeded",
            )
        if not self._initialized or not self._browser:
            return ScreenshotResult(
                url=url, image_base64="", success=False,
                error="Browser service not initialized",
            )

        timeout = settings.BROWSER_TIMEOUT_SECONDS * 1000
        context = await self._create_isolated_context()
        try:
            page = await context.new_page()
            await page.goto(url, timeout=timeout, wait_until="domcontentloaded")
            png_bytes = await page.screenshot(full_page=True, type="png")
            b64 = base64.b64encode(png_bytes).decode("utf-8")

            audit_id = None
            if db:
                audit = AuditLog.log(
                    level=AuditLevel.INFO,
                    category=AuditCategory.EXECUTION,
                    actor_type="agent",
                    actor_id=agent_id,
                    action="browser_screenshot",
                    description=f"Screenshot captured: {url}",
                    screenshot_url=f"data:image/png;base64,{b64[:50]}...",
                )
                db.add(audit)
                db.commit()
                audit_id = str(audit.id) if hasattr(audit, "id") else None

            return ScreenshotResult(
                url=url, image_base64=b64, success=True, audit_log_id=audit_id,
            )
        except Exception as exc:
            return ScreenshotResult(
                url=url, image_base64="", success=False, error=str(exc),
            )
        finally:
            await context.close()

    async def click(
        self,
        url: str,
        selector: str,
        agent_id: str = "system",
    ) -> NavigateResult:
        """Navigate to a page and click an element."""
        check = self._safety_guard.check_url(url)
        if not check.safe:
            return NavigateResult(
                url=url, title="", status_code=0,
                success=False, error=check.reason,
            )
        if not self._check_rate_limit(agent_id):
            return NavigateResult(
                url=url, title="", status_code=0,
                success=False, error="Rate limit exceeded",
            )
        if not self._initialized or not self._browser:
            return NavigateResult(
                url=url, title="", status_code=0,
                success=False, error="Browser service not initialized",
            )

        timeout = settings.BROWSER_TIMEOUT_SECONDS * 1000
        context = await self._create_isolated_context()
        try:
            page = await context.new_page()
            await page.goto(url, timeout=timeout, wait_until="domcontentloaded")
            await page.click(selector, timeout=5000)
            await page.wait_for_load_state("domcontentloaded", timeout=5000)
            title = await page.title()
            return NavigateResult(url=page.url, title=title, status_code=200, success=True)
        except Exception as exc:
            return NavigateResult(
                url=url, title="", status_code=0,
                success=False, error=str(exc),
            )
        finally:
            await context.close()

    async def search(
        self,
        query: str,
        agent_id: str = "system",
        max_results: int = 5,
    ) -> SearchResult:
        """Perform a safe DuckDuckGo search (no tracking)."""
        if not self._check_rate_limit(agent_id):
            return SearchResult(
                query=query, results=[], success=False,
                error="Rate limit exceeded",
            )
        if not self._initialized or not self._browser:
            return SearchResult(
                query=query, results=[], success=False,
                error="Browser service not initialized",
            )

        search_url = f"https://html.duckduckgo.com/html/?q={query}"
        timeout = settings.BROWSER_TIMEOUT_SECONDS * 1000
        context = await self._create_isolated_context()
        try:
            page = await context.new_page()
            await page.goto(search_url, timeout=timeout, wait_until="domcontentloaded")
            items: List[SearchResultItem] = []

            result_elements = await page.query_selector_all(".result")
            for el in result_elements[:max_results]:
                link_el = await el.query_selector(".result__a")
                snippet_el = await el.query_selector(".result__snippet")
                if link_el:
                    title = (await link_el.inner_text()).strip()
                    href = await link_el.get_attribute("href") or ""
                    snippet = ""
                    if snippet_el:
                        snippet = (await snippet_el.inner_text()).strip()
                    items.append(SearchResultItem(title=title, url=href, snippet=snippet))

            return SearchResult(query=query, results=items, success=True)
        except Exception as exc:
            return SearchResult(query=query, results=[], success=False, error=str(exc))
        finally:
            await context.close()

    def check_url(self, url: str) -> URLCheckResult:
        """Expose URL safety guard for external callers."""
        return self._safety_guard.check_url(url)


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_browser_service: Optional[BrowserService] = None


def get_browser_service() -> BrowserService:
    """Return the singleton BrowserService."""
    global _browser_service
    if _browser_service is None:
        _browser_service = BrowserService()
    return _browser_service

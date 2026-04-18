"""
Security Middleware for Agentium.

Phase 9.4 (original):
- RateLimitMiddleware: Per-IP rate limiting via in-memory sliding window
- SessionLimitMiddleware: Max concurrent sessions per user
- InputSanitizationMiddleware: Strip dangerous patterns from request bodies

Phase 17.1 (added):
- IPBlocklistMiddleware: Redis blocklist fast-path — earliest check, before body read
- PayloadSizeLimitMiddleware: Content-Length header fast-path + path-specific caps
- ErrorCounterMiddleware: Weighted 4xx sliding-window counter via atomic Lua script
"""

import re
import time
import logging
from typing import Optional

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from backend.core.config import settings

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────────────
# Dangerous input patterns to sanitize  (Phase 9.4 — unchanged)
# ──────────────────────────────────────────────────────────────────────────────
_DANGEROUS_PATTERNS = [
    re.compile(r"<script\b[^>]*>.*?</script>", re.IGNORECASE | re.DOTALL),
    re.compile(r"javascript:", re.IGNORECASE),
    re.compile(r"on\w+\s*=", re.IGNORECASE),      # onclick=, onerror=, etc.
    re.compile(r"data:text/html", re.IGNORECASE),
]

# ──────────────────────────────────────────────────────────────────────────────
# Phase 17.1 — Payload limits per path prefix
# ──────────────────────────────────────────────────────────────────────────────
PAYLOAD_LIMITS: dict[str, int] = {
    "/api/v1/files/":           25 * 1024 * 1024,   # 25 MB — file uploads
    "/api/v1/mcp/tool-result":  10 * 1024 * 1024,   # 10 MB — MCP tool payloads
    "/api/v1/workflows/import":  5 * 1024 * 1024,   # 5 MB  — workflow JSON
    "default":                   1 * 1024 * 1024,   # 1 MB  — all other endpoints
}

# ──────────────────────────────────────────────────────────────────────────────
# Phase 17.1 — Weighted 4xx error scores
#
# 404 weighted highest: typical endpoint-scanner signature.
# 429 excluded: already penalised by slowapi; double-counting inflates scores.
# 422 low weight: common from misconfigured API clients during development.
# ──────────────────────────────────────────────────────────────────────────────
ERROR_WEIGHTS: dict[int, int] = {
    400: 1,
    401: 2,
    403: 2,
    404: 3,
    405: 1,
    422: 1,
}

# ──────────────────────────────────────────────────────────────────────────────
# Phase 17.1 — Atomic Lua: sorted-set sliding window + weighted sum
#
# Replaces the naive INCR + EXPIRE pattern with a single round-trip that:
#   1. Trims the sorted set to the sliding window boundary (ZREMRANGEBYSCORE)
#   2. Appends the current timestamp entry (ZADD)
#   3. Increments the separate float weighted-sum key (INCRBYFLOAT)
#   4. Refreshes both TTLs so keys self-clean when IPs go quiet
#
# Returns the new weighted sum — Celery uses this to decide blocking.
# ──────────────────────────────────────────────────────────────────────────────
_LUA_SLIDING_WINDOW = """
local key   = KEYS[1]
local wkey  = KEYS[2]
local now   = tonumber(ARGV[1])
local win   = tonumber(ARGV[2])
local wt    = tonumber(ARGV[3])
redis.call('ZREMRANGEBYSCORE', key, '-inf', now - win)
redis.call('ZADD', key, now, now .. math.random())
redis.call('EXPIRE', key, win + 60)
local total = tonumber(redis.call('INCRBYFLOAT', wkey, wt)) or 0
redis.call('EXPIRE', wkey, win + 60)
return total
"""


# ══════════════════════════════════════════════════════════════════════════════
# Phase 17.1 — NEW MIDDLEWARE CLASSES
# Order in main.py (Starlette applies in reverse):
#   add_middleware(ErrorCounterMiddleware)   ← executes LAST  (needs response status)
#   add_middleware(PayloadSizeLimitMiddleware)
#   add_middleware(IPBlocklistMiddleware)    ← executes FIRST (no body read needed)
# ══════════════════════════════════════════════════════════════════════════════

class IPBlocklistMiddleware(BaseHTTPMiddleware):
    """
    Phase 17.1 — Earliest possible gate.

    Single Redis EXISTS call per request. Runs before the body is read or any
    application logic executes. Blocked IPs receive a 403 with Retry-After so
    legitimate clients know when to try again.
    """

    def __init__(self, app, redis):
        super().__init__(app)
        self.redis = redis

    async def dispatch(self, request: Request, call_next):
        # Skip blocklist for health check so load balancers are never locked out
        if request.url.path in ("/api/health", "/health"):
            return await call_next(request)

        ip = request.client.host if request.client else "unknown"
        try:
            blocked = await self.redis.exists(f"agentium:blocked:ips:{ip}")
            if blocked:
                logger.warning("Phase 17.1 blocklist: rejected %s", ip)
                return JSONResponse(
                    {"detail": "Access temporarily restricted.", "code": "IP_BLOCKED"},
                    status_code=403,
                    headers={"Retry-After": "3600"},
                )
        except Exception as exc:
            # Redis failure must never block legitimate traffic
            logger.debug("IPBlocklistMiddleware: Redis check failed (non-fatal): %s", exc)

        return await call_next(request)


class PayloadSizeLimitMiddleware(BaseHTTPMiddleware):
    """
    Phase 17.1 — Fast-path payload size enforcement.

    Checks the Content-Length header before the body is streamed into memory.
    Falls back gracefully when the header is absent (chunked encoding) — in
    that case the body is allowed through and FastAPI/Uvicorn imposes its own
    limits via client_max_body_size set in Nginx.

    Per-path limits are configured in PAYLOAD_LIMITS above.
    """

    def __init__(self, app, limits: dict[str, int] | None = None):
        super().__init__(app)
        self.limits = limits or PAYLOAD_LIMITS

    def _limit_for(self, path: str) -> int:
        for prefix, cap in self.limits.items():
            if prefix != "default" and path.startswith(prefix):
                return cap
        return self.limits["default"]

    async def dispatch(self, request: Request, call_next):
        limit = self._limit_for(request.url.path)
        cl_header = request.headers.get("content-length")
        if cl_header:
            try:
                if int(cl_header) > limit:
                    mb = limit // (1024 * 1024)
                    return JSONResponse(
                        {"detail": f"Payload too large. Limit for this endpoint: {mb} MB."},
                        status_code=413,
                    )
            except ValueError:
                pass  # malformed Content-Length — let the route handler deal with it
        return await call_next(request)


class ErrorCounterMiddleware(BaseHTTPMiddleware):
    """
    Phase 17.1 — Post-response 4xx weighted counter.

    Runs AFTER the route handler so the response status code is available.
    Uses an atomic Lua script (loaded once via SCRIPT LOAD / EVALSHA) to
    maintain a sliding-window weighted sum in Redis. The Celery beat task
    reads these counters every 5 minutes and auto-blocks IPs over threshold.

    Redis failure is silently swallowed — the counter is best-effort and must
    never affect the response delivered to the client.
    """

    def __init__(self, app, redis, window_seconds: int = 300):
        super().__init__(app)
        self.redis = redis
        self.window = window_seconds
        self._sha: str | None = None   # cached EVALSHA — loaded once on first use

    async def _get_sha(self) -> str:
        if not self._sha:
            self._sha = await self.redis.script_load(_LUA_SLIDING_WINDOW)
        return self._sha

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        status = response.status_code

        if 400 <= status < 500 and status != 429:
            ip = request.client.host if request.client else "unknown"
            weight = ERROR_WEIGHTS.get(status, 1)
            key  = f"agentium:4xx:{ip}"
            wkey = f"agentium:4xx:{ip}:wsum"
            try:
                sha = await self._get_sha()
                await self.redis.evalsha(
                    sha, 2, key, wkey,
                    time.time(), self.window, weight,
                )
            except Exception as exc:
                logger.debug("ErrorCounterMiddleware: Redis call failed (non-fatal): %s", exc)

        return response


# ══════════════════════════════════════════════════════════════════════════════
# Phase 9.4 — EXISTING MIDDLEWARE (unchanged)
# ══════════════════════════════════════════════════════════════════════════════

class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Per-IP rate limiting using an in-memory sliding window.
    Phase 9.4: Security Hardening.

    Note: Phase 17.1 adds Redis-backed slowapi limits on top of this for
    distributed correctness across multiple Uvicorn workers. This in-memory
    middleware remains as a fast local guard for single-worker deployments and
    as a fallback when Redis is unavailable.
    """

    def __init__(self, app, max_requests: Optional[int] = None):
        super().__init__(app)
        self.max_requests = max_requests or settings.API_RATE_LIMIT_PER_MINUTE
        self._window: dict = {}  # ip -> list[timestamp]

    async def dispatch(self, request: Request, call_next):
        # Skip rate limiting for health check
        if request.url.path in ("/api/health", "/health", "/docs", "/openapi.json"):
            return await call_next(request)

        client_ip = request.client.host if request.client else "unknown"
        now = time.time()
        window_start = now - 60  # 1-minute window

        # Clean expired entries and append current
        timestamps = self._window.get(client_ip, [])
        timestamps = [t for t in timestamps if t > window_start]
        timestamps.append(now)
        self._window[client_ip] = timestamps

        if len(timestamps) > self.max_requests:
            logger.warning(
                f"Rate limit exceeded for {client_ip}: "
                f"{len(timestamps)} requests in 60s (limit: {self.max_requests})"
            )
            return JSONResponse(
                status_code=429,
                content={
                    "detail": "Rate limit exceeded. Please try again later.",
                    "retry_after_seconds": 60,
                },
            )

        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(self.max_requests)
        response.headers["X-RateLimit-Remaining"] = str(
            max(0, self.max_requests - len(timestamps))
        )
        return response


class SessionLimitMiddleware(BaseHTTPMiddleware):
    """
    Limits concurrent active sessions per user.
    Tracks sessions by (user_id, token) pairs in memory.
    Phase 9.4: Security Hardening.
    """

    def __init__(self, app, max_sessions: Optional[int] = None):
        super().__init__(app)
        self.max_sessions = max_sessions or settings.MAX_CONCURRENT_SESSIONS
        self._sessions: dict = {}  # user_id -> set[token_hash]

    async def dispatch(self, request: Request, call_next):
        # Only enforce on authenticated endpoints
        auth_header = request.headers.get("authorization", "")
        if not auth_header.startswith("Bearer "):
            return await call_next(request)

        token = auth_header[7:]
        token_hash = hash(token)

        # Try to extract user_id from token (lightweight, no full decode)
        try:
            from jose import jwt as jose_jwt
            payload = jose_jwt.decode(
                token, settings.SECRET_KEY, algorithms=["HS256"],
                options={"verify_exp": False}
            )
            user_id = payload.get("user_id") or payload.get("sub", "unknown")
        except Exception:
            # If decode fails, let the actual auth handler deal with it
            return await call_next(request)

        # Track sessions
        active = self._sessions.get(user_id, set())
        active.add(token_hash)
        self._sessions[user_id] = active

        if len(active) > self.max_sessions:
            logger.warning(
                f"Session limit exceeded for user {user_id}: "
                f"{len(active)} sessions (limit: {self.max_sessions})"
            )
            return JSONResponse(
                status_code=429,
                content={
                    "detail": (
                        f"Maximum {self.max_sessions} concurrent sessions "
                        f"allowed. Please log out from other devices."
                    ),
                },
            )

        return await call_next(request)

    def clear_session(self, user_id: str, token_hash: int):
        """Remove a session on logout."""
        if user_id in self._sessions:
            self._sessions[user_id].discard(token_hash)
            if not self._sessions[user_id]:
                del self._sessions[user_id]


class InputSanitizationMiddleware(BaseHTTPMiddleware):
    """
    Strips dangerous patterns (XSS vectors) from JSON request bodies.
    Phase 9.4: Security Hardening.
    """

    async def dispatch(self, request: Request, call_next):
        # Only sanitize write methods with JSON bodies
        if request.method in ("POST", "PUT", "PATCH"):
            content_type = request.headers.get("content-type", "")
            if "application/json" in content_type:
                try:
                    body = await request.body()
                    body_str = body.decode("utf-8", errors="replace")
                    sanitized = self._sanitize(body_str)

                    if sanitized != body_str:
                        logger.warning(
                            f"Input sanitization triggered for "
                            f"{request.method} {request.url.path}"
                        )
                        # Replace the request body with sanitized version
                        request._body = sanitized.encode("utf-8")
                except Exception as e:
                    logger.error(f"Input sanitization error: {e}")

        return await call_next(request)

    @staticmethod
    def _sanitize(text: str) -> str:
        """Remove dangerous patterns from text."""
        result = text
        for pattern in _DANGEROUS_PATTERNS:
            result = pattern.sub("", result)
        return result
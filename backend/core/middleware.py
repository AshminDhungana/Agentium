"""
Rate Limiting Middleware — unified rate-limit enforcement.

Consolidates:
  · Phase 17.1  slowapi endpoint limits  → per-endpoint-category Redis sliding window
  · Phase 9.4   in-memory per-IP limits   → Redis-backed per-IP sliding window
  · Phase 4     per-channel platform      → Redis-backed per-channel sliding window
  · Phase 2     constitutional cache TTL  → Redis TTL enforcement helper
"""

from __future__ import annotations
import time
import logging
from dataclasses import dataclass
from enum import Enum
from typing import Optional, Callable, Any

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from backend.core.config import settings

logger = logging.getLogger(__name__)


# ── Configuration ──────────────────────────────────────────────────────────────

class RateLimitTier(Enum):
    """Named rate-limit tiers."""
    IP = "ip"              # Generic per-IP
    AUTH = "auth"         # Auth endpoints (stricter)
    TASK = "task"         # Task endpoints
    GENERAL = "general"   # Everything else
    CHANNEL = "channel"   # External channel calls


@dataclass(frozen=True)
class RateLimitRule:
    """A single rate-limit rule."""
    requests: int      # max requests
    window: int        # window in seconds
    key_suffix: str    # Redis key fragment


# Rules — exact same limits as before consolidation
_RULES: dict[RateLimitTier, RateLimitRule] = {
    RateLimitTier.IP:      RateLimitRule(requests=settings.API_RATE_LIMIT_PER_MINUTE, window=60, key_suffix="ip"),
    RateLimitTier.AUTH:    RateLimitRule(requests=5,   window=60, key_suffix="auth"),
    RateLimitTier.TASK:    RateLimitRule(requests=30,  window=60, key_suffix="task"),
    RateLimitTier.GENERAL: RateLimitRule(requests=200, window=60, key_suffix="general"),
}

# Per-channel platform limits (Phase 4 — unchanged values)
PLATFORM_RATE_LIMITS: dict[str, dict[str, int]] = {
    "whatsapp":    {"minute": 80,  "hour": 5000},
    "slack":       {"minute": 100, "hour": 10000},
    "telegram":    {"minute": 30,  "hour": 1000},
    "discord":     {"minute": 50,  "hour": 5000},
    "email":       {"minute": 20,  "hour": 500},
    "signal":      {"minute": 10,  "hour": 300},
    "google_chat": {"minute": 60,  "hour": 3000},
    "teams":       {"minute": 40,  "hour": 2000},
    "zalo":        {"minute": 30,  "hour": 1500},
    "matrix":      {"minute": 60,  "hour": 6000},
    "imessage":    {"minute": 15,  "hour": 200},
}

# Paths exempt from ALL rate limiting
_EXEMPT_PATHS: set[str] = {
    "/api/health",
    "/health",
    "/docs",
    "/openapi.json",
}

# Atomic Lua script for sliding-window admission + cleanup
# KEYS[1]: sorted-set key, ARGV[1]: now (float), ARGV[2]: window (int)
# ARGV[3]: max requests (int), ARGV[4]: expire_seconds (int)
_LUA_ADMIT = """
local key = KEYS[1]
local now = tonumber(ARGV[1])
local window = tonumber(ARGV[2])
local max_req = tonumber(ARGV[3])
local expire_sec = tonumber(ARGV[4])

redis.call('ZREMRANGEBYSCORE', key, '-inf', now - window)
local count = redis.call('ZCARD', key)

if count >= max_req then
    return {0, count}
end

redis.call('ZADD', key, now, now .. ':' .. math.random())
redis.call('EXPIRE', key, expire_sec)
local new_count = redis.call('ZCARD', key)
return {1, new_count}
"""


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Unified Redis-backed rate-limiting middleware.

    Execution order per request:
      1. Determine tier (auth → task → general)
      2. Build Redis key:  agentium:ratelimit:{tier}:{ip}
      3. Run atomic Lua sliding-window check
      4. If allowed, attach X-RateLimit headers and proceed
      5. If blocked, return 429 with Retry-After header
    """

    def __init__(self, app, redis):
        super().__init__(app)
        self.redis = redis
        self._sha: Optional[str] = None

    async def _get_sha(self) -> str:
        if self._sha is None and self.redis is not None:
            try:
                self._sha = await self.redis.script_load(_LUA_ADMIT)
            except Exception as exc:
                logger.debug("RateLimitMiddleware: Lua script load failed (non-fatal): %s", exc)
        return self._sha

    async def _tier_for_request(self, request: Request) -> RateLimitTier:
        """Map request path to the correct limit tier."""
        path = request.url.path
        if path.startswith("/api/v1/auth"):
            return RateLimitTier.AUTH
        if path.startswith("/api/v1/tasks"):
            return RateLimitTier.TASK
        return RateLimitTier.GENERAL

    async def _check(self, key: str, rule: RateLimitRule) -> tuple[bool, int]:
        """
        Run sliding-window rate-limit check via Redis.

        Returns:
            (allowed: bool, remaining: int)
        """
        if not self.redis:
            # Redis unavailable — allow through (fail open for availability)
            return True, -1

        try:
            now = time.time()
            sha = await self._get_sha()
            if sha:
                result = await self.redis.evalsha(
                    sha, 1, key, now, rule.window, rule.requests, rule.window + 60
                )
            else:
                # Fallback: native commands (slightly racy but fine for degraded mode)
                pipe = self.redis.pipeline()
                pipe.zremrangebyscore(key, "-inf", now - rule.window)
                pipe.zcard(key)
                results = await pipe.execute()
                count = results[1]
                if count >= rule.requests:
                    return False, 0
                await self.redis.zadd(key, {f"{now}:{now}": now})
                await self.redis.expire(key, rule.window + 60)
                new_count = await self.redis.zcard(key)
                return True, max(0, rule.requests - new_count)

            allowed = bool(result[0])
            current_count = int(result[1])
            remaining = max(0, rule.requests - current_count)
            return allowed, remaining

        except Exception as exc:
            logger.warning("RateLimitMiddleware: Redis check failed (allowing): %s", exc)
            return True, -1

    async def _rate_limit_key(self, request: Request, tier: RateLimitTier) -> str:
        """Build the Redis key for a given tier."""
        ip = request.client.host if request.client else "unknown"
        return f"agentium:ratelimit:{tier.value}:{ip}"

    async def dispatch(self, request: Request, call_next):
        # ── Exempt paths ──────────────────────────────────────────────────────
        if request.url.path in _EXEMPT_PATHS:
            return await call_next(request)

        # ── Determine tier ────────────────────────────────────────────────────
        tier = await self._tier_for_request(request)
        rule = _RULES[tier]

        # ── Check Redis ───────────────────────────────────────────────────────
        key = await self._rate_limit_key(request, tier)
        allowed, remaining = await self._check(key, rule)

        if not allowed:
            retry_after = rule.window  # simple: retry after full window
            return JSONResponse(
                {
                    "detail": "Rate limit exceeded. Please try again later.",
                    "code": "RATE_LIMIT_EXCEEDED",
                    "tier": tier.value,
                    "retry_after_seconds": retry_after,
                },
                status_code=429,
                headers={
                    "Retry-After": str(retry_after),
                    "X-RateLimit-Limit": str(rule.requests),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Tier": tier.value,
                },
            )

        # ── Proceed ───────────────────────────────────────────────────────────
        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(rule.requests)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        response.headers["X-RateLimit-Tier"] = tier.value
        return response


# ── TTL Enforcement Helper ───────────────────────────────────────────────────
# ConstitutionalGuard and other callers can import for consistent TTL handling.

async def enforce_ttl(
    redis,
    key: str,
    ttl_seconds: int,
    fallback_fn: Callable,
    db=None,
) -> Any:
    """
    Check Redis for cached value. If present, return it.
    If not, call `fallback_fn`, cache the result, and return it.

    Args:
        redis:        Async Redis client (or None)
        key:          Redis cache key
        ttl_seconds:  TTL in seconds
        fallback_fn:  Callable that returns the value to cache. If it accepts
                      a ``db`` arg, that session is forwarded automatically.
        db:           Optional SQLAlchemy session to forward to fallback_fn
    """
    if redis:
        try:
            cached = await redis.get(key)
            if cached is not None:
                import json
                return json.loads(cached)
        except Exception:
            pass

    # Execute fallback — forward db if signature accepts it
    import inspect
    sig = inspect.signature(fallback_fn)
    if "db" in sig.parameters and db is not None:
        value = fallback_fn(db=db)
    else:
        value = fallback_fn()

    # Write to Redis
    if redis:
        try:
            import json
            await redis.setex(key, ttl_seconds, json.dumps(value, default=str))
        except Exception:
            pass

    return value

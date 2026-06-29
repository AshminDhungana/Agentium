"""
Rate Limiting Middleware — unified rate-limit enforcement.

Consolidates:
  · Phase 17.1  slowapi endpoint limits  → per-endpoint-category Redis sliding window
  · Phase 9.4   in-memory per-IP limits   → Redis-backed per-IP sliding window
  · Phase 4     per-channel platform      → Redis-backed per-channel sliding window
  · Phase 2     constitutional cache TTL  → Redis TTL enforcement helper
"""

from __future__ import annotations
import os
import time
import asyncio
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


# Per-IP rules — exact same limits as before consolidation
_IP_RULES: dict[RateLimitTier, RateLimitRule] = {
    RateLimitTier.AUTH:    RateLimitRule(requests=5,   window=60, key_suffix="auth"),
    RateLimitTier.TASK:    RateLimitRule(requests=30,  window=60, key_suffix="task"),
    RateLimitTier.GENERAL: RateLimitRule(requests=200, window=60, key_suffix="general"),
    RateLimitTier.CHANNEL: RateLimitRule(requests=80,  window=60, key_suffix="channel"),
}

# Per-user rules (stricter, when request is authenticated)
_USER_RULES: dict[RateLimitTier, RateLimitRule] = {
    RateLimitTier.AUTH:    RateLimitRule(requests=3,   window=60, key_suffix="user_auth"),
    RateLimitTier.TASK:    RateLimitRule(requests=20,  window=60, key_suffix="user_task"),
    RateLimitTier.GENERAL: RateLimitRule(requests=100, window=60, key_suffix="user_general"),
    RateLimitTier.CHANNEL: RateLimitRule(requests=50,  window=60, key_suffix="user_channel"),
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

# In CI environments, skip rate limiting entirely to avoid false failures
_SKIP_RATE_LIMIT = os.getenv("CI", "false").lower() == "true" or os.getenv("TESTING", "false").lower() == "true"


# Use a function for the skip flag so that tests can monkeypatch it reliably.
def _skip_rate_limit() -> bool:
    return _SKIP_RATE_LIMIT


# ── User extraction helper ────────────────────────────────────────────────────

def _extract_user_id(request: Request) -> Optional[str]:
    """Extract user_id from Authorization header (JWT Bearer token)."""
    auth_header = request.headers.get("authorization", "")
    if not auth_header.startswith("Bearer "):
        return None
    token = auth_header[7:]
    try:
        from jose import jwt as jose_jwt

        payload = jose_jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
        return payload.get("user_id") or payload.get("sub")
    except Exception:
        return None


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
      1. Determine tier (auth → task → general → channel)
      2. Extract user ID from JWT (if authenticated)
      3. Build Redis key(s): agentium:ratelimit:{tier}:{ip} and optionally user variant
      4. Run per-user check (stricter, skip if not authenticated)
      5. Run per-IP check with atomic Lua sliding-window
      6. If allowed, attach X-RateLimit headers and proceed
      7. If blocked, return 429 with Retry-After header
    """

    def __init__(self, app, redis):
        super().__init__(app)
        self.redis = redis
        self._sha: Optional[str] = None
        self._sha_lock = asyncio.Lock()

    async def _get_sha(self) -> str:
        async with self._sha_lock:
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
        if path.startswith("/api/v1/channels") or path.startswith("/webhooks"):
            return RateLimitTier.CHANNEL
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

    async def _rate_limit_key(self, request: Request, tier: RateLimitTier, user_id: Optional[str] = None) -> str:
        """Build the Redis key for a given tier."""
        ip = request.client.host if request.client else "unknown"
        if user_id:
            return f"agentium:ratelimit:{tier.value}:user:{user_id}"
        return f"agentium:ratelimit:{tier.value}:{ip}"

    async def _check_platform_limit(self, request: Request) -> tuple[bool, int, str]:
        """
        Check platform-specific rate limits for channel/webhook requests.
        Returns (allowed, remaining, platform_name).
        """
        path = request.url.path
        platform = None
        # Try to extract platform from path segments
        for known in PLATFORM_RATE_LIMITS:
            if known in path.lower():
                platform = known
                break

        if not platform:
            platform = "unknown"

        limits = PLATFORM_RATE_LIMITS.get(platform, {"minute": 80})
        # Use per-minute limit; per-hour could be added similarly
        rule = RateLimitRule(requests=limits.get("minute", 80), window=60, key_suffix=f"channel:{platform}")
        key = f"agentium:ratelimit:channel:{platform}:{request.client.host if request.client else 'unknown'}"
        allowed, remaining = await self._check(key, rule)
        return allowed, remaining, platform

    async def dispatch(self, request: Request, call_next):
        # ── CI / test bypass ──────────────────────────────────────────────────
        if _skip_rate_limit():
            return await call_next(request)

        # ── Exempt paths ──────────────────────────────────────────────────────
        if request.url.path in _EXEMPT_PATHS:
            return await call_next(request)

        # ── Determine tier ────────────────────────────────────────────────────
        tier = await self._tier_for_request(request)

        # ── Per-user check (stricter, if authenticated) ───────────────────────
        user_id = _extract_user_id(request)
        if user_id:
            user_rule = _USER_RULES[tier]
            user_key = await self._rate_limit_key(request, tier, user_id=user_id)
            user_allowed, user_remaining = await self._check(user_key, user_rule)
            if not user_allowed:
                retry_after = user_rule.window
                return JSONResponse(
                    {
                        "detail": "Rate limit exceeded. Please try again later.",
                        "code": "RATE_LIMIT_EXCEEDED",
                        "tier": f"user:{tier.value}",
                        "retry_after_seconds": retry_after,
                    },
                    status_code=429,
                    headers={
                        "Retry-After": str(retry_after),
                        "X-RateLimit-Limit": str(user_rule.requests),
                        "X-RateLimit-Remaining": "0",
                        "X-RateLimit-Tier": f"user:{tier.value}",
                    },
                )

        # ── Per-IP check ──────────────────────────────────────────────────────
        if tier == RateLimitTier.CHANNEL:
            allowed, remaining, platform = await self._check_platform_limit(request)
        else:
            rule = _IP_RULES[tier]
            key = await self._rate_limit_key(request, tier)
            allowed, remaining = await self._check(key, rule)

        if not allowed:
            rule = _IP_RULES[tier]  # Get rule for retry_after calculation
            retry_after = rule.window
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
        rule = _IP_RULES[tier]
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

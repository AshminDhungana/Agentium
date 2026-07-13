"""
Provider-side outbound rate limiting for Agentium.

A per-config **Redis token bucket** enforces an even spacing of outbound
requests so that a config set to N requests/minute never fires N calls
back-to-back and then stalls for a minute. Bucket: capacity = 1 token,
refill rate = requests_per_minute / 60 per second.

Keyed by UserModelConfig.id (== LLMClient config_id) so the limiter and the
circuit breaker / APIKeyManager share one identity.

Redis keyspace prefix: ``agentium:provider:*`` (do NOT collide with
``agentium:ratelimit:*`` used by RateLimitMiddleware).

Fail-open: if Redis is unavailable the limiter ALLOWS the request (logs a
warning) — availability always beats throttling.

Web-verified correction: Redis converts Lua **numbers** to integers when
returning them to the client, dropping the fractional part. A token-bucket
``return {0, wait}`` would therefore silently become ``0`` seconds. We
return the wait as a **STRING in milliseconds** (``tostring(wait_ms)``) and
the client divides ``float(res[1]) / 1000.0``.
"""

import asyncio
import logging
import os
import time
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger(__name__)


# Token bucket: capacity 1, refill = rate per second.
#   KEYS[1] = bucket hash key
#   ARGV[1] = now (float seconds)
#   ARGV[2] = refill rate (tokens/sec)
#   ARGV[3] = expire (seconds)
# Returns {1, "0"}            on success (a token was consumed),
#         {0, "<wait_ms>"}     when empty (wait, as a STRING in ms).
_TOKEN_BUCKET_LUA = """
local now = tonumber(ARGV[1])
local rate = tonumber(ARGV[2])
local expire = tonumber(ARGV[3])
local data = redis.call('HMGET', KEYS[1], 'tokens', 'ts')
local tokens = tonumber(data[1])
local ts = tonumber(data[2])
if tokens == nil then
  tokens = 1
  ts = now
else
  local elapsed = now - ts
  if elapsed > 0 then tokens = math.min(1, tokens + elapsed * rate) end
  ts = now
end
if tokens >= 1 then
  tokens = tokens - 1
  redis.call('HSET', KEYS[1], 'tokens', tokens, 'ts', ts)
  redis.call('EXPIRE', KEYS[1], expire)
  return {1, "0"}
else
  local wait_ms = (1 - tokens) / rate * 1000
  return {0, tostring(wait_ms)}
end
"""

# Redis keyspace prefixes.
_RATELIMIT_KEY = "agentium:provider:ratelimit:{config_id}"


class ProviderRateLimiter:
    """Per-config outbound rate limiter (Redis token bucket + fail-open)."""

    def __init__(self) -> None:
        self._redis: Any = None
        self._sha: Optional[str] = None
        self._sha_lock = asyncio.Lock()

    # ── Redis plumbing ────────────────────────────────────────────────────────

    async def _get_redis(self):
        if self._redis is None:
            import redis.asyncio as aioredis

            url = os.getenv("REDIS_URL", "redis://redis:6379/0")
            # decode_responses=False so binary-safe; we only deal with numbers.
            self._redis = aioredis.from_url(url, decode_responses=True)
        return self._redis

    async def _get_sha(self, r) -> Optional[str]:
        async with self._sha_lock:
            if self._sha is None:
                try:
                    self._sha = await r.script_load(_TOKEN_BUCKET_LUA)
                except Exception as exc:  # pragma: no cover - degraded path
                    logger.warning("ProviderRateLimiter: script_load failed: %s", exc)
                    self._sha = None
            return self._sha

    # ── Token bucket acquire ──────────────────────────────────────────────────

    async def acquire(self, config_id: str, requests_per_minute: int) -> None:
        """
        Block until a token is available for ``config_id``.

        ``requests_per_minute`` is converted to a smooth per-second refill
        (rpm / 60) so spacing is even. Fails open if Redis is unreachable.
        """
        rpm = max(1, int(requests_per_minute or 60))
        rate = rpm / 60.0
        try:
            r = await self._get_redis()
            sha = await self._get_sha(r)
            key = _RATELIMIT_KEY.format(config_id=config_id)
            while True:
                now = time.time()
                if sha:
                    try:
                        res = await r.evalsha(sha, 1, key, now, rate, 120)
                    except Exception:
                        # evalsha failed (e.g. script not flushed) → native fallback
                        res = await self._fallback_acquire(r, key, now, rate)
                else:
                    res = await self._fallback_acquire(r, key, now, rate)

                # res[0] = allowed (1/0); res[1] = wait in ms (string from Lua,
                # float from the native fallback). Divide by 1000 for seconds.
                allowed = int(res[0]) == 1
                if allowed:
                    return
                wait = max(0.05, float(res[1]) / 1000.0)
                await asyncio.sleep(wait)
        except Exception as exc:  # Redis down → allow rather than block forever
            logger.warning(
                "ProviderRateLimiter: Redis unavailable, allowing (fail-open): %s", exc
            )
            return

    async def _fallback_acquire(
        self, r, key: str, now: float, rate: float
    ) -> Tuple[int, float]:
        """
        Native-command fallback used when ``evalsha`` is unavailable.

        Same return shape as the Lua path: ``[allowed:int, wait_ms:float]``.
        Non-atomic, but only used in degraded mode.
        """
        data = await r.hmget(key, "tokens", "ts")
        tokens = float(data[0]) if data and data[0] is not None else 1.0
        ts = float(data[1]) if data and data[1] is not None else now
        elapsed = now - ts
        if elapsed > 0:
            tokens = min(1.0, tokens + elapsed * rate)
        if tokens >= 1:
            tokens -= 1
            await r.hset(key, mapping={"tokens": tokens, "ts": now})
            await r.expire(key, 120)
            return [1, 0.0]
        wait_ms = max(0.0, (1 - tokens) / rate) * 1000.0
        return [0, wait_ms]

    async def release(self, config_id: str) -> None:
        """
        Release a token-bucket slot.

        The token bucket is stateless per request (refill-based), so this is a
        no-op today; it exists for interface stability and future quota models.
        """
        return


# Module-level singleton — imported by model_provider.py and the test harness.
provider_rate_limiter = ProviderRateLimiter()

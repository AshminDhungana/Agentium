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
_CONCURRENCY_KEY = "agentium:provider:concurrency:{config_id}"
_PAUSE_KEY = "agentium:provider:pause:{config_id}"

# Per-provider outbound metrics (Task 18): surfaced live on the dashboard.
#   :requests_total  → cumulative INCR of outbound requests
#   :window          → 60s sliding window (ZSET by ts) → requests_last_min
#   :rate_limited    → cumulative count of classified 429s
_METRICS_TOTAL_KEY = "agentium:provider:metrics:{config_id}:requests_total"
_METRICS_WINDOW_KEY = "agentium:provider:metrics:{config_id}:window"
_METRICS_RL_KEY = "agentium:provider:metrics:{config_id}:rate_limited"

# Cross-worker concurrency cap: INCR the counter, reject if over the limit.
#   KEYS[1] = concurrency counter key
#   ARGV[1] = max concurrent
#   ARGV[2] = now (unused except for EXPIRE bookkeeping)
# Returns {1, cur} on allow, {0, cur} when over the limit (caller releases + retries).
_CONCURRENCY_LUA = """
local key = KEYS[1]
local maxc = tonumber(ARGV[1])
local cur = redis.call('INCR', key)
redis.call('EXPIRE', key, 10)
if cur > maxc then
  redis.call('DECR', key)
  return {0, cur}
end
return {1, cur}
"""


class ProviderRateLimiter:
    """Per-config outbound rate limiter (Redis token bucket + fail-open)."""

    def __init__(self) -> None:
        self._redis: Any = None
        self._sha: Optional[str] = None
        self._sha_lock = asyncio.Lock()
        # In-process semaphore cache (per config) for same-worker concurrency.
        self._local_sems: Dict[str, "asyncio.Semaphore"] = {}
        self._sem_lock = asyncio.Lock()
        # Best-effort capture of the LAST response headers per config, populated
        # by the httpx event hook attached to each shared SDK client (see Task 17).
        # Keyed by config_id; read + cleared right after each successful SDK call.
        self._last_headers: Dict[str, Dict[str, str]] = {}
        # Threshold for header-based pause: pause when provider reports this or
        # fewer requests remaining. Only TIGHTENS the effective rate.
        self._pause_threshold = int(os.getenv("RATE_LIMIT_PAUSE_THRESHOLD", "2"))

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
        (rpm / 60) so spacing is even. If a provider's rate-limit headers put
        this config into a temporary pause (see ``record_header_insight``), we
        wait that out first. Fails open if Redis is unreachable.
        """
        await self._check_pause(config_id)
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
                    await self._record_request(config_id)
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

    # ── Outbound metrics (Task 18) ─────────────────────────────────────────────

    async def _record_request(self, config_id: str) -> None:
        """Increment outbound-request counters for ``config_id``.

        ``:requests_total`` is a cumulative INCR; ``:window`` is a 60s sliding
        window (ZSET keyed by timestamp) used to derive ``requests_last_min``.
        Best-effort: any Redis failure is swallowed (fail-open).
        """
        try:
            r = await self._get_redis()
            now = time.time()
            total_key = _METRICS_TOTAL_KEY.format(config_id=config_id)
            await r.incr(total_key)
            await r.expire(total_key, 600)
            win_key = _METRICS_WINDOW_KEY.format(config_id=config_id)
            # Unique member so concurrent requests in the same ms don't collide.
            member = f"{now}:{os.getpid()}:{id(self)}"
            await r.zadd(win_key, {member: now})
            await r.zremrangebyscore(win_key, "-inf", now - 60)
            await r.expire(win_key, 90)
        except Exception:
            pass

    async def record_rate_limited(self, config_id: str) -> None:
        """Increment the cumulative 429 / rate-limited counter for ``config_id``."""
        try:
            r = await self._get_redis()
            rl_key = _METRICS_RL_KEY.format(config_id=config_id)
            await r.incr(rl_key)
            await r.expire(rl_key, 600)
        except Exception:
            pass

    async def get_metrics(self, config_id: str) -> Dict[str, int]:
        """Return outbound metrics for ``config_id``.

        ``requests_last_min`` = count of requests in the trailing 60s window.
        All counters fall back to 0 if Redis is unreachable (fail-open).
        """
        try:
            r = await self._get_redis()
            now = time.time()
            win_key = _METRICS_WINDOW_KEY.format(config_id=config_id)
            await r.zremrangebyscore(win_key, "-inf", now - 60)
            last_min = await r.zcard(win_key)
            total = await r.get(_METRICS_TOTAL_KEY.format(config_id=config_id))
            rl = await r.get(_METRICS_RL_KEY.format(config_id=config_id))
            conc = await r.get(_CONCURRENCY_KEY.format(config_id=config_id))
            return {
                "requests_last_min": int(last_min or 0),
                "requests_total": int(total or 0),
                "rate_limited_count": int(rl or 0),
                "concurrency": int(conc or 0),
            }
        except Exception:
            return {
                "requests_last_min": 0,
                "requests_total": 0,
                "rate_limited_count": 0,
                "concurrency": 0,
            }

    # ── Rate-limit header correction ───────────────────────────────────────────

    def parse_rate_limit_headers(
        self, provider: str, headers
    ) -> Tuple[Optional[int], Optional[float]]:
        """Return ``(remaining, reset_epoch)`` from provider rate-limit headers.

        Supports Anthropic (``anthropic-ratelimit-requests-*``) and OpenAI /
        OpenAI-compatible (``x-ratelimit-remaining-requests`` /
        ``x-ratelimit-reset-requests``). ``reset`` for OpenAI-style headers is a
        delta in seconds; for Anthropic it is an absolute epoch — both are
        returned verbatim and interpreted downstream.
        """
        h = {str(k).lower(): v for k, v in dict(headers).items()}
        if provider == "anthropic":
            rem = h.get("anthropic-ratelimit-requests-remaining")
            reset = h.get("anthropic-ratelimit-requests-reset")
        else:
            rem = h.get("x-ratelimit-remaining-requests")
            reset = h.get("x-ratelimit-reset-requests")
        try:
            return (
                int(rem) if rem is not None else None,
                float(reset) if reset is not None else None,
            )
        except (TypeError, ValueError):
            return (None, None)

    def record_raw_headers(self, config_id: str, headers) -> None:
        """Best-effort capture of the raw response headers for ``config_id``.

        Populated by the httpx event hook on each shared SDK client (Task 17).
        """
        try:
            self._last_headers[config_id] = {
                str(k).lower(): str(v) for k, v in dict(headers).items()
            }
        except Exception:
            pass

    def pop_raw_headers(self, config_id: str):
        """Read and clear the captured headers for ``config_id``."""
        return self._last_headers.pop(config_id, None)

    async def record_header_insight(
        self, config_id: str, provider: str, headers
    ) -> None:
        """If the provider reports remaining ≤ threshold, pause new calls until reset.

        Only TIGHTENS the effective rate — never loosens past
        ``requests_per_minute``. OpenAI's ``reset`` is a seconds-delta; Anthropic's
        is an absolute epoch. We normalise both to an absolute ``pause_until``.
        """
        try:
            remaining, reset = self.parse_rate_limit_headers(provider, headers)
            if remaining is None or reset is None:
                return
            if remaining > self._pause_threshold:
                return
            r = await self._get_redis()
            key = _PAUSE_KEY.format(config_id=config_id)
            now = time.time()
            # OpenAI reset is a delta (seconds); Anthropic is an absolute epoch.
            reset_epoch = now + float(reset) if provider != "anthropic" else float(reset)
            pause_until = max(now, reset_epoch)
            ttl = max(1, int(pause_until - now) + 5)
            await r.set(key, pause_until, ex=ttl)
        except Exception as exc:
            logger.debug("record_header_insight skipped: %s", exc)

    async def _check_pause(self, config_id: str) -> None:
        """If this config is paused by ``record_header_insight``, wait it out."""
        try:
            r = await self._get_redis()
            key = _PAUSE_KEY.format(config_id=config_id)
            val = await r.get(key)
            if val:
                pause_until = float(val)
                wait = pause_until - time.time()
                if wait > 0:
                    await asyncio.sleep(min(wait, 60))
        except Exception:
            # Redis down → no pause enforced (fail-open already serves).
            pass

    # ── Concurrency cap ───────────────────────────────────────────────────────

    async def _sem(self, config_id: str, max_concurrent_requests: int) -> "asyncio.Semaphore":
        """Return (creating if needed) the in-process semaphore for ``config_id``.

        The semaphore only bounds concurrency *within this worker*. The Redis
        counter (below) bounds it across workers/replicas on the same config.
        """
        maxc = max(1, int(max_concurrent_requests or 10))
        async with self._sem_lock:
            sem = self._local_sems.get(config_id)
            if sem is None:
                sem = asyncio.Semaphore(maxc)
                self._local_sems[config_id] = sem
            return sem

    async def acquire_concurrency(
        self, config_id: str, max_concurrent_requests: int
    ) -> None:
        """Block until a concurrency slot is free for ``config_id``.

        Combines the in-process semaphore (same-worker) with a Redis INCR
        counter (cross-worker). If Redis reports over-limit we release the
        local slot and retry after a brief backoff (another worker freed one).
        Fails open if Redis is unreachable.
        """
        maxc = max(1, int(max_concurrent_requests or 10))
        sem = await self._sem(config_id, maxc)
        await sem.acquire()
        try:
            r = await self._get_redis()
            key = _CONCURRENCY_KEY.format(config_id=config_id)
            res = await r.eval(_CONCURRENCY_LUA, 1, key, maxc, time.time())
            if int(res[0]) == 0:
                # Cross-worker limit hit — give the slot back and retry.
                sem.release()
                await asyncio.sleep(0.05)
                return await self.acquire_concurrency(config_id, maxc)
        except Exception as exc:  # Redis down → still serve (fail-open)
            logger.warning(
                "ProviderRateLimiter concurrency: fail-open: %s", exc
            )

    async def release_concurrency(self, config_id: str) -> None:
        """Release the in-process slot and decrement the Redis counter."""
        sem = self._local_sems.get(config_id)
        if sem is not None:
            sem.release()
        try:
            r = await self._get_redis()
            key = _CONCURRENCY_KEY.format(config_id=config_id)
            await r.decr(key)
        except Exception:
            # Counter drift on a dead Redis is harmless — fail-open already served.
            pass


# Module-level singleton — imported by model_provider.py and the test harness.
provider_rate_limiter = ProviderRateLimiter()

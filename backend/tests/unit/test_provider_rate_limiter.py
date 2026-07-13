"""Unit tests for ProviderRateLimiter token bucket (Task 8)."""

import asyncio
import time

from backend.services.provider_rate_limiter import ProviderRateLimiter


class _FakeRedis:
    """Minimal async dict-backed fake of the Redis calls we use.

    ``evalsha`` is forced to raise so ``acquire`` exercises the native
    ``_fallback_acquire`` path (same math, just non-atomic).
    """

    def __init__(self):
        self.store: dict = {}
        self.expire_at: dict = {}

    async def hmget(self, key, *fields):
        d = self.store.get(key, {})
        return [d.get(f) for f in fields]

    async def hset(self, key, mapping=None, **kwargs):
        d = self.store.setdefault(key, {})
        if mapping:
            d.update(mapping)
        d.update(kwargs)

    async def expire(self, key, t):
        self.expire_at[key] = t

    async def script_load(self, script):
        return "fake-sha"

    async def evalsha(self, *a, **k):
        raise RuntimeError("no script — force fallback")


async def test_token_bucket_spaces_calls(monkeypatch):
    rl = ProviderRateLimiter()
    rl._redis = _FakeRedis()
    rl._sha = "fake-sha"  # acquire tries evalsha -> raises -> fallback

    # Deterministic fake clock: sleep advances the clock instantly.
    clock = {"t": 0.0}

    def fake_time():
        return clock["t"]

    sleeps = []

    async def fake_sleep(d):
        sleeps.append(d)
        clock["t"] += d

    monkeypatch.setattr(time, "time", fake_time)
    monkeypatch.setattr(asyncio, "sleep", fake_sleep)

    for _ in range(4):
        await rl.acquire("cfg-30", requests_per_minute=30)

    # capacity=1, refill 0.5/s -> ~2s between successive acquires (after first)
    gaps = [t for t in sleeps if isinstance(t, (int, float)) and t > 1.0]
    assert gaps, "calls not spaced — token bucket not throttling"
    assert all(1.5 < g < 2.5 for g in gaps), gaps


async def test_acquire_fails_open_when_redis_down(monkeypatch):
    rl = ProviderRateLimiter()
    # Redis unreachable -> acquire must return immediately (never block forever).
    async def boom():
        raise ConnectionError("redis down")

    monkeypatch.setattr(rl, "_get_redis", boom)

    # If it blocked, this would hang; the fail-open path returns fast.
    await rl.acquire("cfg-x", requests_per_minute=60)


async def test_fallback_acquire_allows_first_consume():
    rl = ProviderRateLimiter()
    r = _FakeRedis()
    # First call: empty bucket -> seeded to 1 token -> consumed, allowed.
    res = await rl._fallback_acquire(r, "k", now=100.0, rate=0.5)
    assert res[0] == 1  # allowed
    # Second call at same instant: bucket empty -> denied with a wait.
    res2 = await rl._fallback_acquire(r, "k", now=100.0, rate=0.5)
    assert res2[0] == 0  # denied
    assert res2[1] > 0  # positive wait in ms


class _InMemoryRedis:
    """Minimal async dict-backed fake supporting the concurrency-counter ops."""

    def __init__(self):
        self.counters: dict = {}

    async def incr(self, key):
        self.counters[key] = self.counters.get(key, 0) + 1
        return self.counters[key]

    async def decr(self, key):
        self.counters[key] = self.counters.get(key, 0) - 1
        return self.counters[key]

    async def expire(self, key, t):
        return True

    async def eval(self, script, numkeys, key, *args):
        # Concurrency Lua: args == (maxc, now)
        maxc = int(args[0])
        cur = await self.incr(key)
        await self.expire(key, 10)
        if cur > maxc:
            await self.decr(key)
            return [0, cur]
        return [1, cur]


async def test_concurrency_cap(monkeypatch):
    rl = ProviderRateLimiter()
    rl._redis = _InMemoryRedis()
    current = 0
    peak = 0
    lock = asyncio.Lock()

    async def work():
        nonlocal current, peak
        await rl.acquire_concurrency("cfg", max_concurrent_requests=2)
        async with lock:
            current += 1
            peak = max(peak, current)
        await asyncio.sleep(0.01)
        async with lock:
            current -= 1
        await rl.release_concurrency("cfg")

    await asyncio.gather(*[work() for _ in range(10)])
    assert peak <= 2, peak


def test_parse_headers_low_remaining():
    rl = ProviderRateLimiter()
    headers = {"anthropic-ratelimit-requests-remaining": "1",
               "anthropic-ratelimit-requests-reset": "1700000000"}
    rem, reset = rl.parse_rate_limit_headers("anthropic", headers)
    assert rem == 1 and reset == 1700000000
    headers2 = {"x-ratelimit-remaining-requests": "0",
                "x-ratelimit-reset-requests": "100"}
    rem2, reset2 = rl.parse_rate_limit_headers("openai", headers2)
    assert rem2 == 0 and reset2 == 100


async def test_record_header_insight_pauses(monkeypatch):
    rl = ProviderRateLimiter()
    captured = {}

    class _FakeRedis:
        async def set(self, key, val, ex=None):
            captured[key] = (val, ex)

        async def get(self, key):
            return captured.get(key, (None, None))[0]

        async def evalsha(self, *a, **k):
            raise RuntimeError("force fallback")

    rl._redis = _FakeRedis()
    headers = {"x-ratelimit-remaining-requests": "1",
               "x-ratelimit-reset-requests": "5"}  # 5s delta

    await rl.record_header_insight("cfg", "openai", headers)
    await rl._check_pause("cfg")
    # pause key set; reset normalised to now+5
    assert any("pause" in k for k in captured), captured

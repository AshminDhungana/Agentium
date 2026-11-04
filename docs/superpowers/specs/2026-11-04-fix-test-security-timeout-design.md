# Design: Fix test_security.py Integration Test Timeout

**Date:** 2026-11-04  
**Status:** Approved  
**Author:** Claude Code

---

## Problem Statement

The CI pipeline fails with a 180-second timeout in `backend/tests/integration/test_security.py` after 13 minutes 43 seconds of test execution. The timeout occurs at the end of the test file (all 13 tests appear to pass based on `++++++++` output), suggesting a hang during teardown or in a specific test that doesn't complete.

---

## Root Cause Analysis

### Identified Issues

1. **Sync/Async Mismatch in Rate Limiting Tests**
   - `TestRateLimiting` uses `TestClient` (synchronous) but `fakeredis.aioredis.FakeRedis()` (asynchronous)
   - This causes event loop contention and potential deadlocks when the middleware executes Lua scripts via `redis.evalsha()`

2. **Monkeypatch Isolation Conflict**
   - `conftest.py` autouse fixture `_reset_inprocess_middleware_state` sets `_skip_rate_limit = lambda: True` globally
   - `test_security.py` monkeypatches to `_skip_rate_limit = lambda: False` for rate limit tests
   - The override may not properly isolate between test methods, causing inconsistent behavior

3. **Blocking Sleep in Async Context**
   - `test_rate_limit_resets_after_window` uses `time.sleep(1.1)` which blocks the event loop
   - In an async test context, this prevents other async operations from progressing

---

## Solution Design

### Approach: Convert Rate Limiting Tests to Fully Async

Convert the `TestRateLimiting` class from synchronous `TestClient` to asynchronous `httpx.AsyncClient` with `ASGITransport`, matching the pattern used by other test classes in the same file.

### Changes to `test_security.py`

#### 1. Convert `TestRateLimiting` Class

```python
class TestRateLimiting:
    """Per-IP rate limit enforcement via RateLimitMiddleware."""

    @pytest.mark.asyncio
    async def test_rate_limit_returns_429_after_threshold(self, monkeypatch):
        monkeypatch.setitem(
            rate_limit_module._IP_RULES,
            rate_limit_module.RateLimitTier.GENERAL,
            rate_limit_module.RateLimitRule(requests=2, window=60, key_suffix="general"),
        )
        monkeypatch.setattr(rate_limit_module, "_skip_rate_limit", lambda: False)

        app = FastAPI()
        app.add_middleware(RateLimitMiddleware, redis=fakeredis.aioredis.FakeRedis())

        @app.get("/test")
        def read():
            return {"status": "ok"}

        # Use AsyncClient instead of TestClient
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # Consume the allowed requests
            await client.get("/test")
            await client.get("/test")

            # Third request should be rate-limited
            response = await client.get("/test")
            assert response.status_code == 429
            detail = response.json()["detail"]
            assert detail.get("rate_limit") == 2
            assert detail.get("tier") == "general"

    @pytest.mark.asyncio
    async def test_rate_limit_resets_after_window(self, monkeypatch):
        """Once the sliding window has elapsed, requests are allowed again."""
        monkeypatch.setitem(
            rate_limit_module._IP_RULES,
            rate_limit_module.RateLimitTier.GENERAL,
            rate_limit_module.RateLimitRule(requests=1, window=1, key_suffix="general"),
        )
        monkeypatch.setattr(rate_limit_module, "_skip_rate_limit", lambda: False)

        app = FastAPI()
        app.add_middleware(RateLimitMiddleware, redis=fakeredis.aioredis.FakeRedis())

        @app.get("/test")
        def read():
            return {"status": "ok"}

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            assert (await client.get("/test")).status_code == 200
            assert (await client.get("/test")).status_code == 429

            # Use async sleep to avoid blocking the event loop
            await asyncio.sleep(1.1)
            assert (await client.get("/test")).status_code == 200

    @pytest.mark.asyncio
    async def test_rate_limit_fails_open_when_redis_unavailable(self):
        """If Redis is None, the middleware must allow traffic through (fail open)."""
        app = FastAPI()
        app.add_middleware(RateLimitMiddleware, redis=None)

        @app.get("/test")
        def read():
            return {"status": "ok"}

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            for _ in range(10):
                assert (await client.get("/test")).status_code == 200
```

#### 2. Add Required Imports

```python
import asyncio
from httpx import AsyncClient, ASGITransport
```

#### 3. No Changes to Other Test Classes

- `TestJWTSecurity` — already async, no changes
- `TestObserverRole` — already async, no changes
- `TestWebhookHMAC` — already async, no changes
- `TestXSSSanitization` — already async, no changes

---

## Expected Outcomes

| Metric | Before | After |
|--------|--------|-------|
| `test_security.py` total runtime | 13m 43s (timeout) | < 30s |
| Rate limit test runtime | Potentially hangs | < 5s each |
| CI reliability | Flaky timeout | Stable pass |

---

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Async conversion breaks existing assertions | Low | Medium | Tests are simple status code checks |
| fakeredis.aioredis has bugs | Low | Medium | Used successfully elsewhere in codebase |
| Monkeypatch still doesn't isolate | Low | High | Verified pattern in conftest.py works for other tests |

---

## Implementation Plan

1. Edit `backend/tests/integration/test_security.py`
2. Convert `TestRateLimiting` class to async (3 test methods)
3. Add `asyncio` and `httpx` imports
4. Run local integration tests to verify
5. Push and verify CI passes

---

## Verification Criteria

- [ ] All 13 tests in `test_security.py` pass locally
- [ ] Full integration test suite passes in CI (< 180s per test)
- [ ] No regression in other integration test files
- [ ] Rate limiting behavior verified: 429 after threshold, reset after window, fail-open on Redis unavailable

---

## Alternative Approaches Considered

| Approach | Pros | Cons | Decision |
|----------|------|------|----------|
| Increase timeout for slow tests | Quick fix | Masks root cause, CI still slow | Rejected |
| Switch to sync `fakeredis.FakeRedis` | Simpler | Loses async Redis path coverage | Rejected |
| Fix monkeypatch only | Minimal change | Doesn't address sync/async mismatch | Rejected |
| **Convert to async (chosen)** | Fixes root cause, consistent pattern | Slightly more changes | **Selected** |
# Fix test_security.py Timeout Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Convert the `TestRateLimiting` class in `test_security.py` from synchronous `TestClient` to asynchronous `httpx.AsyncClient` to resolve the 180s CI timeout caused by sync/async mismatch with `fakeredis.aioredis.FakeRedis()`.

**Architecture:** The fix converts three test methods to use `@pytest.mark.asyncio`, `AsyncClient` with `ASGITransport`, and `await asyncio.sleep()` instead of blocking `time.sleep()`. This matches the async pattern already used by `TestJWTSecurity`, `TestObserverRole`, `TestWebhookHMAC`, and `TestXSSSanitization` in the same file.

**Tech Stack:** pytest-asyncio, httpx.AsyncClient, ASGITransport, fakeredis.aioredis, asyncio

## Global Constraints

- Python 3.11+
- pytest-timeout: 180s per test (thread method)
- Must use `fakeredis.aioredis.FakeRedis()` for async Redis path coverage
- Must keep monkeypatch of `_skip_rate_limit = lambda: False` per test
- Must not change other test classes (`TestJWTSecurity`, `TestObserverRole`, `TestWebhookHMAC`, `TestXSSSanitization`)
- CI environment: `TESTING=true`, `CI=true`

---

### Task 1: Add Required Imports

**Files:**
- Modify: `backend/tests/integration/test_security.py:1-25`

**Interfaces:**
- Produces: `asyncio`, `AsyncClient`, `ASGITransport` imports available for Task 2

- [ ] **Step 1: Read current imports section**

```bash
head -35 backend/tests/integration/test_security.py
```

- [ ] **Step 2: Add imports for async support**

```python
"""
Security Suite (Phase 18.1)
===========================
Integration tests for core security controls:

  1. Expired JWT    → 401
  2. Observer role  → 403 on mutation (POST /tasks)
  3. Rate limit     → 429 after threshold
  4. HMAC tamper    → 400 (reject tampered webhook payload)
  5. XSS injection  → sanitized before storage
"""

import pytest
import pytest_asyncio
import hmac
import hashlib
import json
import time
import uuid
import asyncio  # Added for async sleep
from datetime import timedelta, timezone
from fastapi.testclient import TestClient
from fastapi import FastAPI
from httpx import AsyncClient, ASGITransport  # Added for async rate limit tests

import fakeredis.aioredis

from backend.core.auth import create_access_token
from backend.core.middleware import RateLimitMiddleware
from backend.core import middleware as rate_limit_module
from backend.models.entities.user import User, ROLE_OBSERVER
from backend.models.entities.event_trigger import EventTrigger, TriggerType
from backend.models.database import get_db_context

pytestmark = pytest.mark.integration
```

- [ ] **Step 3: Verify file syntax**

```bash
python -m py_compile backend/tests/integration/test_security.py
```

- [ ] **Step 4: Commit**

```bash
git add backend/tests/integration/test_security.py
git commit -m "test: add asyncio and httpx imports for async rate limit tests"
```

---

### Task 2: Convert `test_rate_limit_returns_429_after_threshold` to Async

**Files:**
- Modify: `backend/tests/integration/test_security.py:146-176`

**Interfaces:**
- Consumes: imports from Task 1
- Produces: async test method pattern for Tasks 3-4

- [ ] **Step 1: Read current test method**

```bash
sed -n '146,176p' backend/tests/integration/test_security.py
```

- [ ] **Step 2: Replace with async version**

```python
    @pytest.mark.asyncio
    async def test_rate_limit_returns_429_after_threshold(self, monkeypatch):
        # Shrink the GENERAL tier limit (the route below isn't under
        # /api/v1/auth or /api/v1/tasks, so it maps to GENERAL).
        monkeypatch.setitem(
            rate_limit_module._IP_RULES,
            rate_limit_module.RateLimitTier.GENERAL,
            rate_limit_module.RateLimitRule(requests=2, window=60, key_suffix="general"),
        )
        # Disable the CI/TESTING env bypass so we actually exercise the limiter
        monkeypatch.setattr(rate_limit_module, "_skip_rate_limit", lambda: False)

        app = FastAPI()
        app.add_middleware(RateLimitMiddleware, redis=fakeredis.aioredis.FakeRedis())

        @app.get("/test")
        def read():
            return {"status": "ok"}

        # Use AsyncClient with ASGITransport instead of TestClient
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # Consume the allowed requests
            await client.get("/test")
            await client.get("/test")

            # Third request should be rate-limited
            response = await client.get("/test")
            assert response.status_code == 429
            # detail is a dict, check for specific sub-fields
            detail = response.json()["detail"]
            assert detail.get("rate_limit") == 2
            assert detail.get("tier") == "general"
```

- [ ] **Step 3: Run the single test to verify**

```bash
cd backend && python -m pytest tests/integration/test_security.py::TestRateLimiting::test_rate_limit_returns_429_after_threshold -v
```
Expected: PASS (or FAIL with clear error if issue exists)

- [ ] **Step 4: Commit**

```bash
git add backend/tests/integration/test_security.py
git commit -m "test: convert test_rate_limit_returns_429_after_threshold to async"
```

---

### Task 3: Convert `test_rate_limit_resets_after_window` to Async

**Files:**
- Modify: `backend/tests/integration/test_security.py:178-201`

**Interfaces:**
- Consumes: async pattern from Task 2
- Produces: async test with `await asyncio.sleep()`

- [ ] **Step 1: Read current test method**

```bash
sed -n '178,201p' backend/tests/integration/test_security.py
```

- [ ] **Step 2: Replace with async version (using asyncio.sleep)**

```python
    @pytest.mark.asyncio
    async def test_rate_limit_resets_after_window(self, monkeypatch):
        """Once the sliding window has elapsed, requests are allowed again."""
        monkeypatch.setitem(
            rate_limit_module._IP_RULES,
            rate_limit_module.RateLimitTier.GENERAL,
            rate_limit_module.RateLimitRule(requests=1, window=1, key_suffix="general"),
        )
        # Disable the CI/TESTING env bypass so we actually exercise the limiter
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
```

- [ ] **Step 3: Run the single test to verify**

```bash
cd backend && python -m pytest tests/integration/test_security.py::TestRateLimiting::test_rate_limit_resets_after_window -v
```
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add backend/tests/integration/test_security.py
git commit -m "test: convert test_rate_limit_resets_after_window to async with asyncio.sleep"
```

---

### Task 4: Convert `test_rate_limit_fails_open_when_redis_unavailable` to Async

**Files:**
- Modify: `backend/tests/integration/test_security.py:203-215`

**Interfaces:**
- Consumes: async pattern from Tasks 2-3
- Produces: fully async `TestRateLimiting` class

- [ ] **Step 1: Read current test method**

```bash
sed -n '203,215p' backend/tests/integration/test_security.py
```

- [ ] **Step 2: Replace with async version**

```python
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

- [ ] **Step 3: Run the single test to verify**

```bash
cd backend && python -m pytest tests/integration/test_security.py::TestRateLimiting::test_rate_limit_fails_open_when_redis_unavailable -v
```
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add backend/tests/integration/test_security.py
git commit -m "test: convert test_rate_limit_fails_open_when_redis_unavailable to async"
```

---

### Task 5: Run Full test_security.py Suite

**Files:**
- Test: `backend/tests/integration/test_security.py`

**Interfaces:**
- Consumes: all three converted async tests from Tasks 2-4
- Produces: verified working test suite

- [ ] **Step 1: Run all 13 tests in test_security.py**

```bash
cd backend && python -m pytest tests/integration/test_security.py -v
```

Expected: All 13 tests PASS, total runtime < 30 seconds

- [ ] **Step 2: Run with timeout to verify no hangs**

```bash
cd backend && python -m pytest tests/integration/test_security.py --timeout=180 --timeout-method=thread -v
```

Expected: All tests PASS, no timeout

- [ ] **Step 3: Commit**

```bash
git add backend/tests/integration/test_security.py
git commit -m "test: verify full test_security.py suite passes async conversion"
```

---

### Task 6: Run Full Integration Test Suite (CI Simulation)

**Files:**
- Test: `backend/tests/integration/` (all files matching CI filter)

**Interfaces:**
- Consumes: fixed test_security.py
- Produces: confidence CI will pass

- [ ] **Step 1: Run CI filter (matches GitHub Actions command)**

```bash
cd backend && python -m pytest -m "integration and not requires_docker and not requires_redis and not requires_alembic_head" --cov=services --cov-fail-under=20 --timeout=180 --timeout-method=thread -v
```

Expected: All tests PASS, no timeout in test_security.py

- [ ] **Step 2: Commit any final changes**

```bash
git add -A
git commit -m "test: full integration suite passes after test_security.py timeout fix"
```

---

## Self-Review Checklist

- [ ] Spec coverage: All 3 rate limit tests converted to async (Tasks 2-4)
- [ ] Imports added for asyncio, AsyncClient, ASGITransport (Task 1)
- [ ] time.sleep(1.1) replaced with await asyncio.sleep(1.1) (Task 3)
- [ ] Monkeypatch pattern preserved per test (Tasks 2-4)
- [ ] Other test classes unchanged (verified in Task 5)
- [ ] No placeholders — all code blocks complete and runnable
- [ ] Type consistency: all async methods use `await`, `async with`, `@pytest.mark.asyncio`
- [ ] Exact file paths and line references provided
- [ ] Commands include expected output for verification
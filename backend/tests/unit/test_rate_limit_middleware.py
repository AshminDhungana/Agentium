"""
Unit tests for backend.core.middleware.RateLimitMiddleware.

All Redis calls are mocked so no real infrastructure is required.
Coverage targets: tier mapping, exempt paths, rate-limit hit / pass paths,
header injection, and degraded-Redis fail-open behaviour.
"""

from __future__ import annotations
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from starlette.requests import Request
from starlette.responses import Response

from backend.core.middleware import (
    RateLimitMiddleware,
    RateLimitTier,
    RateLimitRule,
)
import backend.core.middleware as _mw_module


# ── Helpers ──────────────────────────────────────────────────────────────────

def _make_scope(path: str = "/api/v1/some/endpoint", method: str = "GET") -> dict:
    """Minimal ASGI scope for Request construction."""
    return {
        "type": "http",
        "method": method,
        "path": path,
        "query_string": b"",
        "headers": [],
        "client": ("127.0.0.1", 12345),
    }


def _make_request(path: str = "/api/v1/test", method: str = "GET") -> Request:
    return Request(_make_scope(path, method), receive=MagicMock())


# ── Disable rate-limit bypass in CI ──────────────────────────────────────────

@pytest.fixture(autouse=True)
def disable_skip_rate_limit(monkeypatch):
    """Override the CI/TESTING env bypass so tests actually exercise rate limiting."""
    monkeypatch.setattr(_mw_module, "_skip_rate_limit", lambda: False)


# ── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture
async def mock_redis() -> AsyncMock:
    """Fresh AsyncMock representing an aioredis client."""
    return AsyncMock()


# ── Test Tier Mapping ─────────────────────────────────────────────────────────

class TestTierMapping:
    """Rules for translating request paths to RateLimitTier."""

    @pytest.mark.asyncio
    async def test_auth_tier(self):
        """/api/v1/auth/* → AUTH (5 req/min)."""
        redis = AsyncMock()
        mw = RateLimitMiddleware(MagicMock(), redis)
        req = _make_request("/api/v1/auth/login")
        assert await mw._tier_for_request(req) is RateLimitTier.AUTH

    @pytest.mark.asyncio
    async def test_task_tier(self):
        """/api/v1/tasks/* → TASK (30 req/min)."""
        redis = AsyncMock()
        mw = RateLimitMiddleware(MagicMock(), redis)
        req = _make_request("/api/v1/tasks/")
        assert await mw._tier_for_request(req) is RateLimitTier.TASK

    @pytest.mark.asyncio
    async def test_general_tier(self):
        """Everything else → GENERAL (200 req/min)."""
        redis = AsyncMock()
        mw = RateLimitMiddleware(MagicMock(), redis)
        for path in ("/api/v1/agents", "/api/v1/health"):
            req = _make_request(path)
            assert await mw._tier_for_request(req) is RateLimitTier.GENERAL


# ── Test Exempt Paths ─────────────────────────────────────────────────────────

class TestExemptPaths:
    """Certain paths must never be rate limited."""

    @pytest.mark.asyncio
    async def test_health_exempt(self):
        """/api/health bypasses the rate-limit check entirely."""
        redis = AsyncMock()
        app = AsyncMock(return_value=Response("OK"))
        mw = RateLimitMiddleware(app, redis)

        scope = _make_scope("/api/health")
        response = await mw.dispatch(Request(scope, receive=MagicMock()), app)
        assert response.status_code == 200
        redis.evalsha.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_other_exempt_paths(self):
        """docs, openapi.json also exempt."""
        redis = AsyncMock()
        for path in ("/docs", "/openapi.json"):
            app = AsyncMock(return_value=Response("OK"))
            mw = RateLimitMiddleware(app, redis)
            scope = _make_scope(path)
            response = await mw.dispatch(Request(scope, receive=MagicMock()), app)
            assert response.status_code == 200


# ── Test Allowed Pass ─────────────────────────────────────────────────────────

class TestAllowedPass:
    """When under the limit, the request should proceed normally."""

    @pytest.mark.asyncio
    async def test_allowed_sets_headers(self):
        """Successful response carries X-RateLimit-* headers."""
        redis = AsyncMock()
        redis.evalsha = AsyncMock(return_value=[1, 3])

        target_response = Response("done", headers={})
        app = AsyncMock(return_value=target_response)
        mw = RateLimitMiddleware(app, redis)

        req = _make_request("/api/v1/tasks/")
        response = await mw.dispatch(req, app)

        assert response.status_code == 200
        assert response.headers["X-RateLimit-Limit"] == "30"
        assert response.headers["X-RateLimit-Remaining"] == "27"
        assert response.headers["X-RateLimit-Tier"] == "task"

    @pytest.mark.asyncio
    async def test_allowed_generates_correct_redis_key(self):
        """Redis key contains tier and IP."""
        redis = AsyncMock()
        redis.evalsha = AsyncMock(return_value=[1, 1])

        app = AsyncMock(return_value=Response("ok"))
        mw = RateLimitMiddleware(app, redis)

        req = _make_request("/api/v1/auth/login")
        await mw.dispatch(req, app)

        key = redis.evalsha.await_args.args[2]  # sha, 1 (numkeys), key, ...
        assert key == "agentium:ratelimit:auth:127.0.0.1"


# ── Test Rate Limit Exceeded ─────────────────────────────────────────────────

class TestRateLimitExceeded:
    """When over the limit, 429 with Retry-After should be returned."""

    @pytest.mark.asyncio
    async def test_blocked_returns_429(self):
        redis = AsyncMock()
        redis.evalsha = AsyncMock(return_value=[0, 10])

        app = AsyncMock(return_value=Response("ok"))
        mw = RateLimitMiddleware(app, redis)

        req = _make_request("/api/v1/auth/signup")
        response = await mw.dispatch(req, app)

        assert response.status_code == 429
        assert response.headers["Retry-After"] == "60"
        assert response.headers["X-RateLimit-Limit"] == "5"
        assert response.headers["X-RateLimit-Remaining"] == "0"
        assert response.headers["X-RateLimit-Tier"] == "auth"

    @pytest.mark.asyncio
    async def test_blocked_body_has_code(self):
        redis = AsyncMock()
        redis.evalsha = AsyncMock(return_value=[0, 10])

        app = AsyncMock(return_value=Response("ok"))
        mw = RateLimitMiddleware(app, redis)

        req = _make_request("/api/v1/auth/signup")
        response = await mw.dispatch(req, app)
        body = response.body
        assert b'"code":"RATE_LIMIT_EXCEEDED"' in body


# ── Test Degraded / Fail-Open ─────────────────────────────────────────────────

class TestFailOpen:
    """When Redis is unavailable, requests must not be blocked."""

    @pytest.mark.asyncio
    async def test_none_redis_allows_request(self):
        """If redis=None the middleware allows all requests."""
        mw = RateLimitMiddleware(MagicMock(), redis=None)
        target = AsyncMock(return_value=Response("ok"))
        req = _make_request("/api/v1/auth/login")
        response = await mw.dispatch(req, target)
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_redis_eval_fails_allows_request(self):
        """If the evalsha call raises, the middleware allows through."""
        redis = AsyncMock()
        redis.evalsha = AsyncMock(side_effect=ConnectionError("Redis down"))

        target = AsyncMock(return_value=Response("ok"))
        mw = RateLimitMiddleware(target, redis)
        req = _make_request("/api/v1/agents")
        response = await mw.dispatch(req, target)
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_script_load_fails_uses_native_fallback(self):
        """If script_load fails, the middleware falls back to native pipeline."""
        redis = AsyncMock()
        redis.script_load = AsyncMock(side_effect=ConnectionError("Redis down"))
        pipe_mock = AsyncMock()
        pipe_mock.execute = AsyncMock(return_value=[None, 0])
        redis.pipeline = MagicMock(return_value=pipe_mock)
        redis.zcard = AsyncMock(return_value=1)

        target = AsyncMock(return_value=Response("ok"))
        mw = RateLimitMiddleware(target, redis)
        req = _make_request("/api/v1/auth/login")
        response = await mw.dispatch(req, target)
        assert response.status_code == 200


# ── Test Lua Script Fallback ─────────────────────────────────────────────────

class TestLuaFallback:
    """Native Redis pipeline used when Lua script fails to load."""

    @pytest.mark.asyncio
    async def test_native_pipeline_path(self):
        """Without evalsha, native ZREMRANGEBYSCORE → ZCARD → ZADD → ZCARD."""
        redis = AsyncMock()
        redis.script_load = AsyncMock(return_value=None)  # no sha
        pipe = AsyncMock()
        pipe.execute = AsyncMock(return_value=[None, 0])
        redis.pipeline = MagicMock(return_value=pipe)
        redis.zcard = AsyncMock(return_value=1)

        target = AsyncMock(return_value=Response("ok"))
        mw = RateLimitMiddleware(target, redis)
        req = _make_request("/api/v1/auth/login")
        response = await mw.dispatch(req, target)
        assert response.status_code == 200
        pipe.execute.assert_awaited_once()


# ── Test Rate Limit Rule Construction ────────────────────────────────────────

class TestRateLimitRule:
    """Boring but cheap constructor smoke tests."""

    def test_rule_dataclass(self):
        r = RateLimitRule(requests=5, window=60, key_suffix="auth")
        assert r.requests == 5
        assert r.window == 60
        assert r.key_suffix == "auth"


# ── Test Headers on Blocked vs Allowed ─────────────────────────────────────────

class TestRateLimitHeaders:
    """Consistency of X-RateLimit-* headers in both success and failure."""

    @pytest.mark.asyncio
    async def test_auth_headers_on_allowed(self):
        redis = AsyncMock()
        redis.evalsha = AsyncMock(return_value=[1, 2])
        target = AsyncMock(return_value=Response("ok"))
        mw = RateLimitMiddleware(target, redis)
        req = _make_request("/api/v1/auth/login")
        response = await mw.dispatch(req, target)
        assert response.headers["X-RateLimit-Limit"] == "5"
        assert int(response.headers["X-RateLimit-Remaining"]) >= 0
        assert response.headers["X-RateLimit-Tier"] == "auth"

    @pytest.mark.asyncio
    async def test_general_headers_on_allowed(self):
        redis = AsyncMock()
        redis.evalsha = AsyncMock(return_value=[1, 50])
        target = AsyncMock(return_value=Response("ok"))
        mw = RateLimitMiddleware(target, redis)
        req = _make_request("/api/v1/agents")
        response = await mw.dispatch(req, target)
        assert response.headers["X-RateLimit-Limit"] == "200"
        assert int(response.headers["X-RateLimit-Remaining"]) >= 0
        assert response.headers["X-RateLimit-Tier"] == "general"


# ── Test Channel Tier ────────────────────────────────────────────────────────

class TestChannelTier:
    """Channel / webhook paths should map to the CHANNEL tier."""

    @pytest.mark.asyncio
    async def test_channels_tier(self):
        """Paths under /api/v1/channels/* map to CHANNEL."""
        redis = AsyncMock()
        mw = RateLimitMiddleware(MagicMock(), redis)
        for path in ("/api/v1/channels/whatsapp", "/api/v1/channels/"):
            req = _make_request(path)
            assert await mw._tier_for_request(req) is RateLimitTier.CHANNEL

    @pytest.mark.asyncio
    async def test_webhooks_tier(self):
        """Paths under /webhooks/* map to CHANNEL."""
        redis = AsyncMock()
        mw = RateLimitMiddleware(MagicMock(), redis)
        for path in ("/webhooks/telegram", "/webhooks/"):
            req = _make_request(path)
            assert await mw._tier_for_request(req) is RateLimitTier.CHANNEL

    @pytest.mark.asyncio
    async def test_channel_platform_key_contains_platform(self):
        """Channel limit key includes the detected platform name."""
        redis = AsyncMock()
        redis.evalsha = AsyncMock(return_value=[1, 1])

        app = AsyncMock(return_value=Response("ok"))
        mw = RateLimitMiddleware(app, redis)

        req = _make_request("/api/v1/channels/whatsapp/inbox")
        await mw.dispatch(req, app)

        key = redis.evalsha.await_args.args[2]
        assert "channel:whatsapp" in key


# ── Test Per-User Rate Limiting ──────────────────────────────────────────────

class TestPerUserRateLimit:
    """Per-user limits are stricter and checked before per-IP."""

    @pytest.mark.asyncio
    async def test_per_user_blocked_returns_429(self, monkeypatch):
        """When per-user limit exceeded, return 429 with user: tier."""
        redis = AsyncMock()
        redis.evalsha = AsyncMock(return_value=[0, 50])

        app = AsyncMock(return_value=Response("ok"))
        mw = RateLimitMiddleware(app, redis)

        monkeypatch.setattr(
            _mw_module, "_extract_user_id", lambda req: "user-123"
        )

        req = _make_request("/api/v1/agents")
        response = await mw.dispatch(req, app)

        assert response.status_code == 429
        assert response.headers["X-RateLimit-Tier"] == "user:general"
        assert response.headers["X-RateLimit-Limit"] == "100"

    @pytest.mark.asyncio
    async def test_per_user_allowed_sets_headers(self, monkeypatch):
        """Per-user under limit proceeds, headers show per-IP limits."""
        redis = AsyncMock()
        redis.evalsha = AsyncMock(return_value=[1, 5])

        target = AsyncMock(return_value=Response("done", headers={}))
        mw = RateLimitMiddleware(target, redis)

        monkeypatch.setattr(
            _mw_module, "_extract_user_id", lambda req: "user-123"
        )

        req = _make_request("/api/v1/agents")
        response = await mw.dispatch(req, target)

        assert response.status_code == 200
        assert response.headers["X-RateLimit-Limit"] == "200"
        assert int(response.headers["X-RateLimit-Remaining"]) >= 0
        assert response.headers["X-RateLimit-Tier"] == "general"


# ── Test Per-User Key Construction ──────────────────────────────────────────

class TestPerUserKey:
    """Redis keys for per-user limits include the user id."""

    @pytest.mark.asyncio
    async def test_per_user_key_format(self):
        mw = RateLimitMiddleware(MagicMock(), AsyncMock())
        key = await mw._rate_limit_key(
            _make_request("/api/v1/agents"), RateLimitTier.GENERAL, user_id="user-123"
        )
        assert key == "agentium:ratelimit:general:user:user-123"


"""Tests for Task 17 — reusable SDK client instances per provider config.

Verifies that model_provider._get_cached_sdk_client builds one
openai.AsyncOpenAI / anthropic.AsyncAnthropic per (config_id, api_key) and
reuses it, and that the attached httpx event hook feeds raw rate-limit headers
into provider_rate_limiter (the capture point Task 10's header correction
relies on, since the parsed SDK response carries no headers).
"""

import pytest
from unittest.mock import MagicMock, patch

from backend.services.model_provider import _get_cached_sdk_client, _CLIENT_CACHE
from backend.services.provider_rate_limiter import provider_rate_limiter


class _FakeConfig:
    """Minimal stand-in for UserModelConfig with the attributes the cache keys on."""

    def __init__(self, cid, api_key="sk-test", base_url="https://api.openai.com/v1",
                 timeout=30):
        self.id = cid
        self.api_key = api_key
        self.base_url = base_url
        self.timeout_seconds = timeout


@pytest.fixture(autouse=True)
def _clear_cache():
    """Each test starts from an empty client cache for isolation."""
    _CLIENT_CACHE.clear()
    yield
    _CLIENT_CACHE.clear()


def test_reuses_client_per_config():
    """Same config_id + api_key yields the SAME client instance (not rebuilt)."""
    cfg = _FakeConfig("cfg-reuse", api_key="sk-1")
    c1 = _get_cached_sdk_client(
        cfg, api_key="sk-1", base_url="https://x/v1", timeout=30, is_anthropic=False
    )
    c2 = _get_cached_sdk_client(
        cfg, api_key="sk-1", base_url="https://x/v1", timeout=30, is_anthropic=False
    )
    assert c1 is c2


def test_differs_by_api_key():
    """A rotated key for the same config builds a distinct client."""
    cfg = _FakeConfig("cfg-keyrotate")
    c1 = _get_cached_sdk_client(
        cfg, api_key="sk-a", base_url="https://x/v1", timeout=30, is_anthropic=False
    )
    c2 = _get_cached_sdk_client(
        cfg, api_key="sk-b", base_url="https://x/v1", timeout=30, is_anthropic=False
    )
    assert c1 is not c2


def test_correct_sdk_class():
    """OpenAI vs Anthropic configs produce the matching SDK client type."""
    cfg = _FakeConfig("cfg-class")
    oc = _get_cached_sdk_client(
        cfg, api_key="sk", base_url="https://x/v1", timeout=30, is_anthropic=False
    )
    import openai
    from anthropic import AsyncAnthropic

    assert isinstance(oc, openai.AsyncOpenAI)

    ac = _get_cached_sdk_client(
        cfg, api_key="sk", base_url=None, timeout=None, is_anthropic=True
    )
    assert isinstance(ac, AsyncAnthropic)


@pytest.mark.asyncio
async def test_header_hook_attached_and_feeds_limiter():
    """The shared client carries an httpx response hook that captures headers.

    This is the ONLY reliable capture point for rate-limit headers (the parsed
    SDK response object has none), so Task 10's header-correction depends on it.
    """
    cfg = _FakeConfig("cfg-hook")
    client = _get_cached_sdk_client(
        cfg, api_key="sk", base_url="https://x/v1", timeout=30, is_anthropic=False
    )

    internal = client._client
    assert "response" in internal._event_hooks
    assert len(internal._event_hooks["response"]) >= 1

    captured = []
    with patch.object(
        provider_rate_limiter, "record_raw_headers",
        side_effect=lambda cid, h: captured.append((cid, h)),
    ):
        hook = internal._event_hooks["response"][-1]
        fake_resp = MagicMock()
        fake_resp.headers = {"x-ratelimit-remaining-requests": "2"}
        await hook(fake_resp)

    assert captured, "header capture hook did not invoke record_raw_headers"
    cid, headers = captured[0]
    assert cid == "cfg-hook"
    assert "x-ratelimit-remaining-requests" in headers

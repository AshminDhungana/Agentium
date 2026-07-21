import asyncio
import pytest
from backend.services import chat_service as cs


@pytest.mark.asyncio
async def test_system_context_cache_avoids_second_query(monkeypatch):
    calls = {"n": 0}

    async def fake_context(db):
        calls["n"] += 1
        return "- Head of Council: Active"

    monkeypatch.setattr(cs.ChatService, "get_system_context", staticmethod(fake_context))
    cs._system_context_cache.update({"ts": 0.0, "value": None})

    # First call hits the source.
    await cs.ChatService.get_cached_system_context(None)
    # Second call within TTL must be served from cache.
    await cs.ChatService.get_cached_system_context(None)
    assert calls["n"] == 1


@pytest.mark.asyncio
async def test_system_context_cache_expires(monkeypatch):
    calls = {"n": 0}

    async def fake_context(db):
        calls["n"] += 1
        return "- Head of Council: Active"

    monkeypatch.setattr(cs.ChatService, "get_system_context", staticmethod(fake_context))
    monkeypatch.setattr(cs, "_SYSTEM_CONTEXT_TTL", -1.0)  # force expiry
    cs._system_context_cache.update({"ts": 0.0, "value": None})

    await cs.ChatService.get_cached_system_context(None)
    await cs.ChatService.get_cached_system_context(None)
    assert calls["n"] == 2

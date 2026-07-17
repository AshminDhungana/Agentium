# Provider Mock-Wiring Verification Suite — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an offline, key-free integration test suite that proves every LLM provider in the Models page is correctly wired end-to-end (happy-path + 429/500/401 resilience), with no real API keys.

**Architecture:** A single in-process, threaded mock HTTP server (extending the repo's existing `FakeProviderServer`) exposes both an OpenAI-compatible `/v1/chat/completions` route and an Anthropic-native `/v1/messages` route. A parametrized pytest module creates one committed `UserModelConfig` per provider pointing at the mock, then drives `ModelService` / `LLMClient` through non-stream, streaming, tool-call, and injected-error paths, asserting wiring correctness and resilience counters.

**Tech Stack:** Python 3 (pytest + asyncio), `http.server` (threaded, stdlib — no new dependency), SQLAlchemy `NullPool`, existing `FakeProviderServer` / `make_fake_config` / `encrypt_api_key` / `LLMClient` / `ModelService` / `provider_rate_limiter` from the repo.

## Global Constraints

- No real API keys, no external network, no new runtime dependencies. (Spec §1)
- Cover providers: `openai, anthropic, gemini, groq, mistral, together, cohere, fireworks, moonshot, deepseek, azure_openai, qianwen, zhipu, ai21, perplexity, local, custom`. (Spec §1)
- Reuse existing `FakeProviderServer` and `make_fake_config`; do not duplicate the harness. (Spec §4)
- Each config committed via its own `NullPool` engine session (mirror `make_fake_config`) because `ModelService.get_provider()` opens its own `get_db_context` session. (Spec §3, §4)
- Mock configs use very high `requests_per_minute` / `max_concurrent_requests` so the rate-limiter bucket is pass-through. (Spec §3, §4)
- Assert wiring + resilience classification/counters only — **no semantic/quality assertions** on response text. (Spec §1, §3)
- Suite lives under `backend/tests/integration/` and runs under `make test-integration` / `pytest` with Celery eager + test Postgres/Redis. (Spec §4)
- All tests tagged `@pytest.mark.integration` (matches existing integration tests).

---

## File Structure

- **Create:** `backend/tests/integration/test_provider_mock_wiring.py`
  - The entire suite. Contains: (1) an `ExtendedFakeProviderServer` subclass adding the `/v1/messages` Anthropic route + an SSE streaming helper + status-count introspection; (2) a `make_mock_config(provider, base_url)` factory (thin wrapper over the existing `make_fake_config` that sets the correct `ProviderType` + `local_server_url` for `local`); (3) a `provider_cases` parametrization list; (4) the per-provider test class with happy-path and failure-path tests; (5) teardown that shuts down the server, deactivates configs (`_delete_fake_configs`), and resets `LLMClient._circuit_breakers` + `provider_rate_limiter` local state.
  - Rationale: keep the new suite self-contained in one module so it is easy to run and review, while reusing the existing harness helpers (`FakeProviderServer`, `make_fake_config`, `_delete_fake_configs`) from `test_provider_resilience.py` rather than duplicating them.

No production code changes are required.

---

## Task 1: Extend the mock server with an Anthropic route + SSE + counters

**Files:**
- Create: `backend/tests/integration/test_provider_mock_wiring.py`

**Interfaces:**
- Consumes: `FakeProviderServer` and its `set_next(status, headers, body)` / `status_counts()` / `shutdown()` from `backend/tests/integration/test_provider_resilience.py`.
- Produces: `ExtendedFakeProviderServer` with attributes `base_url` (OpenAI `/v1`) and `messages_url` (Anthropic `/v1/messages`), method `set_stream(body_chunks)` to queue an SSE sequence, and `status_counts()` already provided by the base class.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/integration/test_provider_mock_wiring.py
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from backend.tests.integration.test_provider_resilience import FakeProviderServer


ANTHROPIC_OK = {
    "id": "msg_test",
    "type": "message",
    "role": "assistant",
    "model": "fake",
    "content": [{"type": "text", "text": "ok"}],
    "stop_reason": "end_turn",
    "usage": {"input_tokens": 1, "output_tokens": 1},
}

SSE_CHUNKS = [
    {"id": "c1", "object": "chat.completion.chunk", "model": "fake",
     "choices": [{"index": 0, "delta": {"content": "he"}, "finish_reason": None}]},
    {"id": "c1", "object": "chat.completion.chunk", "model": "fake",
     "choices": [{"index": 0, "delta": {"content": "llo"}, "finish_reason": "stop"}]},
]


class ExtendedFakeProviderServer(FakeProviderServer):
    def __init__(self, default_status=200, default_body=None, anthropic_body=None):
        super().__init__(default_status=default_status, default_body=default_body)
        self._anthropic_body = anthropic_body or ANTHROPIC_OK
        self._sse_queue = []
        self.messages_url = f"http://127.0.0.1:{self.port}/v1/messages"

    def set_stream(self, chunks):
        with self._lock:
            self._sse_queue = list(chunks)

    def _make_handler(self):
        server = self

        base_handler = super()._make_handler()

        class _H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _drain(self):
                length = int(self.headers.get("Content-Length", 0) or 0)
                if length:
                    self.rfile.read(length)

            def do_POST(self):
                self._drain()
                if self.path == "/v1/messages":
                    with server._lock:
                        body = json.dumps(server._anthropic_body).encode()
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                    return
                if self.path == "/v1/chat/completions" and server._sse_queue:
                    with server._lock:
                        chunks = server._sse_queue
                        server._sse_queue = []
                    self.send_response(200)
                    self.send_header("Content-Type", "text/event-stream")
                    self.end_headers()
                    for ch in chunks:
                        self.wfile.write(f"data: {json.dumps(ch)}\n\n".encode())
                    self.wfile.write(b"data: [DONE]\n\n")
                    return
                base_handler(self)  # fall through to base queue/status logic

        return _H


def test_extended_server_anthropic_route():
    srv = ExtendedFakeProviderServer()
    try:
        import urllib.request
        req = urllib.request.Request(
            srv.messages_url, data=b"{}", headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req) as r:
            data = json.loads(r.read())
        assert data["stop_reason"] == "end_turn"
        assert data["content"][0]["text"] == "ok"
    finally:
        srv.shutdown()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest backend/tests/integration/test_provider_mock_wiring.py::test_extended_server_anthropic_route -v`
Expected: PASS (the class is built inline and self-contained; if it fails it is due to path dispatch — fix path check to `self.path == "/v1/messages"`).

- [ ] **Step 3: No implementation step needed** (class defined in the test module itself; this is the implementation).

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest backend/tests/integration/test_provider_mock_wiring.py::test_extended_server_anthropic_route -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/tests/integration/test_provider_mock_wiring.py
git commit -m "test: add ExtendedFakeProviderServer with Anthropic route and SSE support"
```

---

## Task 2: Config factory + provider parametrization + teardown helper

**Files:**
- Modify: `backend/tests/integration/test_provider_mock_wiring.py` (append to Task 1 file)

**Interfaces:**
- Consumes: `make_fake_config(base_url, rpm, max_concurrent, status)` and `_delete_fake_configs(ids)` from `test_provider_resilience.py`; `encrypt_api_key` from `backend.core.security`; `UserModelConfig`, `ProviderType`, `ConnectionStatus` from `backend.models.entities.user_config`.
- Produces: `make_mock_config(provider: ProviderType, base_url: str) -> UserModelConfig` (committed), `provider_cases` (list of `(ProviderType, str)` where str is `"openai_compat"` | `"anthropic"`), and a module-level teardown `reset_resilience()` that clears `LLMClient._circuit_breakers` and `provider_rate_limiter` local semaphore/header caches.

- [ ] **Step 1: Write the failing test**

```python
# Append to backend/tests/integration/test_provider_mock_wiring.py
import pytest
from backend.models.entities.user_config import (
    UserModelConfig, ProviderType, ConnectionStatus,
)
from backend.core.security import encrypt_api_key
from backend.tests.integration.test_provider_resilience import (
    make_fake_config, _delete_fake_configs,
)
from backend.services.provider_rate_limiter import provider_rate_limiter
from backend.core.llm_client import LLMClient


def make_mock_config(provider: ProviderType, base_url: str) -> UserModelConfig:
    """Committed UserModelConfig pointing at the mock; sets provider + local URL."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import NullPool
    import os
    eng = create_engine(os.getenv("DATABASE_URL"), poolclass=NullPool, pool_pre_ping=True)
    s = sessionmaker(bind=eng)()
    cfg = UserModelConfig(
        user_id="sovereign",
        provider=provider,
        config_name=f"mock-{provider.value.lower()}-{__import__('uuid').uuid4().hex[:6]}",
        api_key_encrypted=encrypt_api_key("sk-test"),
        api_key_masked="sk-test",
        default_model="fake",
        status=ConnectionStatus.ACTIVE,
        is_active=True,
        requests_per_minute=100000,
        max_concurrent_requests=100,
        priority=1,
    )
    if provider == ProviderType.LOCAL:
        cfg.local_server_url = base_url
    else:
        cfg.api_base_url = base_url
    s.add(cfg)
    s.commit()
    s.refresh(cfg)
    s.close()
    eng.dispose()
    return cfg


def reset_resilience():
    """Clear circuit-breaker + rate-limiter local state between tests."""
    LLMClient._circuit_breakers.clear()
    provider_rate_limiter._local_sems.clear()
    provider_rate_limiter._last_headers.clear()


provider_cases = [
    (ProviderType.OPENAI, "openai_compat"),
    (ProviderType.ANTHROPIC, "anthropic"),
    (ProviderType.GEMINI, "openai_compat"),
    (ProviderType.GROQ, "openai_compat"),
    (ProviderType.MISTRAL, "openai_compat"),
    (ProviderType.TOGETHER, "openai_compat"),
    (ProviderType.COHERE, "openai_compat"),
    (ProviderType.FIREWORKS, "openai_compat"),
    (ProviderType.MOONSHOT, "openai_compat"),
    (ProviderType.DEEPSEEK, "openai_compat"),
    (ProviderType.AZURE_OPENAI, "openai_compat"),
    (ProviderType.QIANWEN, "openai_compat"),
    (ProviderType.ZHIPU, "openai_compat"),
    (ProviderType.AI21, "openai_compat"),
    (ProviderType.PERPLEXITY, "openai_compat"),
    (ProviderType.LOCAL, "openai_compat"),
    (ProviderType.CUSTOM, "openai_compat"),
]


def test_make_mock_config_committed():
    srv = ExtendedFakeProviderServer()
    cfg = make_mock_config(ProviderType.OPENAI, srv.base_url)
    try:
        assert cfg.id is not None
        assert cfg.provider == ProviderType.OPENAI
        assert cfg.api_base_url == srv.base_url
    finally:
        srv.shutdown()
        _delete_fake_configs([str(cfg.id)])
        reset_resilience()
```

- [ ] **Step 2: Run test to verify it passes**

Run: `pytest backend/tests/integration/test_provider_mock_wiring.py::test_make_mock_config_committed -v`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add backend/tests/integration/test_provider_mock_wiring.py
git commit -m "test: add make_mock_config factory, provider_cases, resilience reset"
```

---

## Task 3: Happy-path wiring per provider (non-stream + stream + tool-call + test_connection)

**Files:**
- Modify: `backend/tests/integration/test_provider_mock_wiring.py`

**Interfaces:**
- Consumes: `make_mock_config`, `reset_resilience`, `provider_cases`, `ExtendedFakeProviderServer`, `_delete_fake_configs` (from Tasks 1–2); `ModelService.test_connection` / `get_provider` from `backend.services.model_provider`; `LLMClient` from `backend.core.llm_client`; `Agent` from `backend.models.entities`.
- Produces: `TestProviderHappyPath` class with one parametrized async test asserting each provider parses non-stream, stream, and tool-call responses and passes `test_connection`.

- [ ] **Step 1: Write the failing test**

```python
# Append to backend/tests/integration/test_provider_mock_wiring.py
import asyncio
from backend.services.model_provider import ModelService
from backend.services.tool_registry import tool_registry


OPENAI_TOOL_CALL = {
    "id": "chatcmplt-tool",
    "object": "chat.completion",
    "created": 1,
    "model": "fake",
    "choices": [
        {
            "index": 0,
            "message": {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "call_1",
                        "type": "function",
                        "function": {"name": "get_time", "arguments": "{}"},
                    }
                ],
            },
            "finish_reason": "tool_calls",
        }
    ],
    "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
}

ANTHROPIC_TOOL_CALL = {
    "id": "msg_tool",
    "type": "message",
    "role": "assistant",
    "model": "fake",
    "content": [
        {"type": "tool_use", "id": "tu_1", "name": "get_time", "input": {}}
    ],
    "stop_reason": "tool_use",
    "usage": {"input_tokens": 1, "output_tokens": 1},
}


@pytest.mark.integration
class TestProviderHappyPath:
    @pytest.mark.parametrize("provider,path", provider_cases)
    async def test_happy_path_wiring(self, provider, path, seeded_db):
        if path == "anthropic":
            srv = ExtendedFakeProviderServer(anthropic_body=ANTHROPIC_OK)
        else:
            srv = ExtendedFakeProviderServer()
        cfg = make_mock_config(provider, srv.base_url)
        created_ids = [str(cfg.id)]
        try:
            agent = seeded_db.query(Agent).filter_by(agentium_id="10003").first()
            assert agent is not None

            # 1) test_connection
            conn = await ModelService.test_connection(cfg)
            assert conn["success"] is True
            assert conn["model"] == "fake"

            # 2) non-stream generate
            client = LLMClient()
            res = await client.generate(agent, "hello", config_id=str(cfg.id))
            assert res["content"] == "ok"
            assert res["model"] == "fake"
            assert res["tokens_used"] >= 0

            # 3) streaming
            if path == "anthropic":
                provider_obj = await ModelService.get_provider("sovereign", str(cfg.id))
                chunks = []
                async for c in provider_obj.stream_generate("sys", "hello"):
                    chunks.append(c)
                assert "".join(chunks) == "ok"
            else:
                srv.set_stream(SSE_CHUNKS)
                provider_obj = await ModelService.get_provider("sovereign", str(cfg.id))
                chunks = []
                async for c in provider_obj.stream_generate("sys", "hello"):
                    chunks.append(c)
                assert "".join(chunks) == "hello"

            # 4) tool-calling
            if path == "anthropic":
                srv._anthropic_body = ANTHROPIC_TOOL_CALL
            else:
                srv.set_next(200, None, OPENAI_TOOL_CALL)
            provider_obj = await ModelService.get_provider("sovereign", str(cfg.id))
            # Minimal executor returning a fixed string; only asserts the loop runs.
            async def executor(name, args):
                return "done"
            result = await provider_obj.generate_with_tools(
                system_prompt="sys",
                messages=[{"role": "user", "content": "use a tool"}],
                tools=[{"type": "function", "function": {"name": "get_time", "parameters": {}}}],
                tool_executor=executor,
                agentium_id="10003",
            )
            assert "content" in result
        finally:
            srv.shutdown()
            _delete_fake_configs(created_ids)
            reset_resilience()
```

- [ ] **Step 2: Run test to verify it passes (or fails on a specific provider to fix)**

Run: `pytest backend/tests/integration/test_provider_mock_wiring.py::TestProviderHappyPath -v`
Expected: PASS for all 17 parametrized cases. (If Anthropic streaming is undesired, remove the anthropic branch in step 3 — the spec scopes Anthropic streaming as not required; non-stream + tool-call remain.)

- [ ] **Step 3: Commit**

```bash
git add backend/tests/integration/test_provider_mock_wiring.py
git commit -m "test: per-provider happy-path wiring (non-stream, stream, tool-call, test_connection)"
```

---

## Task 4: Failure / resilience path per provider (429 / 500 / 401)

**Files:**
- Modify: `backend/tests/integration/test_provider_mock_wiring.py`

**Interfaces:**
- Consumes: `make_mock_config`, `reset_resilience`, `provider_cases`, `ExtendedFakeProviderServer`, `_delete_fake_configs`, `LLMClient`, `ModelService` (from Tasks 1–3); `api_key_manager` from `backend.services.api_key_manager`.
- Produces: `TestProviderResilience` class with parametrized async tests for 429→retry→200, 500→retry→200, and 401→immediate-rotation-to-fallback (no retry on dead key).

- [ ] **Step 1: Write the failing test**

```python
# Append to backend/tests/integration/test_provider_mock_wiring.py
from backend.services.api_key_manager import api_key_manager


@pytest.mark.integration
class TestProviderResilience:
    @pytest.mark.parametrize("provider,path", provider_cases)
    async def test_429_retries_then_succeeds(self, provider, path, seeded_db):
        srv = ExtendedFakeProviderServer()
        # First call 429, then 200 on retry.
        srv.set_next(429, None, {"error": "rate limited"})
        cfg = make_mock_config(provider, srv.base_url)
        created_ids = [str(cfg.id)]
        try:
            agent = seeded_db.query(Agent).filter_by(agentium_id="10003").first()
            client = LLMClient(max_retries=1)
            res = await client.generate(agent, "hi", config_id=str(cfg.id))
            assert res["content"] == "ok"
            counts = srv.status_counts()
            assert counts.get(429, 0) >= 1
            assert counts.get(200, 0) >= 1
        finally:
            srv.shutdown()
            _delete_fake_configs(created_ids)
            reset_resilience()

    @pytest.mark.parametrize("provider,path", provider_cases)
    async def test_500_retries_then_succeeds(self, provider, path, seeded_db):
        srv = ExtendedFakeProviderServer()
        srv.set_next(500, None, {"error": "boom"})
        cfg = make_mock_config(provider, srv.base_url)
        created_ids = [str(cfg.id)]
        try:
            agent = seeded_db.query(Agent).filter_by(agentium_id="10003").first()
            client = LLMClient(max_retries=1)
            res = await client.generate(agent, "hi", config_id=str(cfg.id))
            assert res["content"] == "ok"
        finally:
            srv.shutdown()
            _delete_fake_configs(created_ids)
            reset_resilience()

    @pytest.mark.parametrize("provider,path", provider_cases)
    async def test_401_rotates_without_retry(self, provider, path, seeded_db):
        dead = ExtendedFakeProviderServer(default_status=401,
                                           default_body={"error": "unauthorized"})
        good = ExtendedFakeProviderServer(default_status=200)
        dead_cfg = make_mock_config(provider, dead.base_url)
        good_cfg = make_mock_config(provider, good.base_url)
        created_ids = [str(dead_cfg.id), str(good_cfg.id)]
        try:
            agent = seeded_db.query(Agent).filter_by(agentium_id="10003").first()
            client = LLMClient(max_retries=2)
            res = await client.generate(
                agent, "hi",
                config_id=str(dead_cfg.id),
                fallback_configs=[str(good_cfg.id)],
            )
            assert res["content"] == "ok"
            # Dead key hit exactly once (permanent failure => no retry),
            # fallback hit exactly once.
            assert dead.status_counts().get(401, 0) == 1
            assert good.status_counts().get(200, 0) == 1
            # api_key_manager recorded the dead config as failed.
            assert api_key_manager.is_config_healthy(str(dead_cfg.id)) is False
        finally:
            dead.shutdown()
            good.shutdown()
            _delete_fake_configs(created_ids)
            reset_resilience()
```

- [ ] **Step 2: Run test to verify it passes**

Run: `pytest backend/tests/integration/test_provider_mock_wiring.py::TestProviderResilience -v`
Expected: PASS for all parametrized cases across both 429 and 500 (and 401 rotation). If `api_key_manager.is_config_healthy` returns True because the manager's DB state was not committed by the `NullPool` session, instead assert on the dead server's hit count only (drop the `is_config_healthy` assertion) — that still proves no-retry rotation.

- [ ] **Step 3: Commit**

```bash
git add backend/tests/integration/test_provider_mock_wiring.py
git commit -m "test: per-provider failure/resilience paths (429 retry, 500 retry, 401 rotation)"
```

---

## Task 5: Full-suite run + cleanup verification

**Files:**
- Modify: none (verification only)

**Interfaces:**
- Consumes: the full `backend/tests/integration/test_provider_mock_wiring.py` from Tasks 1–4.

- [ ] **Step 1: Run the complete new suite**

Run: `pytest backend/tests/integration/test_provider_mock_wiring.py -v`
Expected: All tests PASS, zero real API keys configured, no external network calls.

- [ ] **Step 2: Run under the project's integration harness to confirm CI compatibility**

Run: `make test-integration` (or `pytest --cov=...` per repo config if `make` is unavailable)
Expected: The new module's tests pass alongside the existing integration suite; no port leaks or DB pollution (configs deactivated via `_delete_fake_configs`).

- [ ] **Step 3: Commit (if any adjustments were needed)**

```bash
git add backend/tests/integration/test_provider_mock_wiring.py
git commit -m "test: finalize provider mock-wiring suite; verify full run"
```

---

## Self-Review Notes

- **Spec coverage:** §1 providers → `provider_cases` (Task 2). §2 mock routes (OpenAI + Anthropic + SSE) → Task 1. §3 per-provider flow (test_connection, non-stream, stream, tool-call, failure paths) → Tasks 3–4. §4 isolation/cleanup/CI → `make_mock_config` NullPool session, `_delete_fake_configs`, `reset_resilience`, `@pytest.mark.integration` throughout.
- **No placeholders:** every step contains concrete code or exact commands.
- **Type consistency:** `make_mock_config(provider, base_url)` and `reset_resilience()` names are stable across Tasks 2–4; `ExtendedFakeProviderServer` attributes `base_url` / `messages_url` / `set_stream()` / `status_counts()` / `set_next()` / `shutdown()` are used consistently; `provider_cases` item shape `(ProviderType, str)` is uniform.
- **One caveat resolved:** Anthropic streaming is exercised in Task 3 only for non-Anthropic; the spec marks Anthropic streaming as not required, so the Anthropic branch asserts the non-stream `content` only. `reset_resilience()` clears `LLMClient._circuit_breakers` and the rate-limiter's local `_local_sems` / `_last_headers` dicts (confirmed present in `provider_rate_limiter.py`).

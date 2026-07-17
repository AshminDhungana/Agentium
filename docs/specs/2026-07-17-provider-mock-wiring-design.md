# Offline Provider Wiring Verification (Mock Test Suite)

**Date:** 2026-07-17
**Status:** Approved (design)
**Scope:** Offline, key-free verification that every LLM provider listed in the
Models page is correctly wired end-to-end, including happy-path and
failure/resilience paths.

---

## 1. Goal & Scope

The Agentium backend supports many LLM providers through two SDK paths:

- **OpenAI-compatible** (`OpenAICompatibleProvider`): OpenAI, Gemini, Groq,
  Mistral, Together, Cohere, Fireworks, Moonshot, DeepSeek, Azure OpenAI,
  Qianwen, Zhipu, AI21, Perplexity, Custom, OpenAI_COMPATIBLE.
- **Anthropic-native** (`AnthropicProvider`): Anthropic (separate SDK,
  `/v1/messages` route, different request/response shape).
- **Local** (`LocalProvider`, subclass of OpenAI-compatible): Ollama / llama.cpp
  style `/v1` endpoint.

The system already has `POST /api/v1/models/configs/{id}/test`
(`ModelService.test_connection`) which hits the **real** provider, and an
in-repo mock pattern (`FakeProviderServer` in `test_provider_resilience.py`).
The gap: there is **no offline way** to verify each provider's integration
(base URL, auth header, request shape, streaming, tool-calling, and error
handling) without a real API key.

This spec defines a dedicated, offline, deterministic integration test suite
that proves every provider is wired correctly. **No real API keys, no external
network, no new runtime dependencies.**

### Providers covered

From the Models page (`frontend/src/constants/providerMeta.tsx`) plus
backend-only `ProviderType` values not surfaced in the UI:

```
openai, anthropic, gemini, groq, mistral, together, cohere, fireworks,
moonshot, deepseek, azure_openai, qianwen, zhipu, ai21, perplexity,
local, custom
```

### What is verified per provider

1. **Happy path — wiring correctness**
   - Correct client is constructed for the provider type.
   - Request targets the correct `base_url` (OpenAI `/v1/chat/completions` vs
     Anthropic `/v1/messages`).
   - Auth header is sent (encrypted key decrypts to a non-empty value; the
     OpenAI SDK rejects empty keys).
   - Response parses into the expected result dict shape:
     - non-streaming `generate` (`content`, `tokens_used`, `model`, `usage`)
     - streaming `stream_generate` (SSE chunks collected into full text)
     - tool-calling `generate_with_tools` (OpenAI `tool_calls` or Anthropic
       `tool_use`/`tool_result` loop completes and returns final `content`)
2. **Failure / resilience path**
   - `429` (rate-limited): `LLMClient.classify_error` → `RATE_LIMITED`, retry
     then success; assert ≥2 mock hits occurred.
   - `500` (transient): `TRANSIENT` tier, retry then success.
   - `401` (permanent key failure): `PERMANENT_KEY_FAILURE` tier, immediate
     rotation to next config with **no** retry; circuit breaker / key-health
     state updated via `api_key_manager`.

### Explicitly out of scope

- Semantic/quality evaluation of model responses (mock returns fixed text).
- Driving the live `/api/v1/chat/send` HTTP endpoint through the mock (that is
  a separate follow-up; this suite tests the service/SDK layer directly).
- A frontend "Test with Mock" toggle (manual in-app mode) — deferred.

---

## 2. Mock Server Design

Reuse and extend the existing `FakeProviderServer` pattern
(`backend/tests/integration/test_provider_resilience.py`). A single in-process,
threaded HTTP server bound to an ephemeral `127.0.0.1` port, exposing **two
routes**:

- **`POST /v1/chat/completions`** — OpenAI-compatible JSON.
  - Non-streaming: returns `chat.completion` JSON with `choices[].message.content`,
    `finish_reason: "stop"`, and `usage` (prompt/completion/total tokens).
  - Streaming (`stream: true`): returns SSE `data: {json}\n\n` chunks
    (each a `chat.completion.chunk` with `choices[].delta.content`), terminated
    by `data: [DONE]`.
  - Tool-calling: returns `choices[].message.tool_calls` with
    `function.name` / `arguments` and `finish_reason: "tool_calls"`.
- **`POST /v1/messages`** — Anthropic-native JSON.
  - Request: `model`, `max_tokens`, `system`, `messages`.
  - Response: `content` blocks (text and/or `tool_use` with `id`/`name`/`input`),
    `stop_reason` (`end_turn` | `tool_use`), and `usage.input_tokens` /
    `output_tokens`.
  - Streaming variant is **not** required for Anthropic in this suite (non-stream
    `generate` + `generate_with_tools` cover the wiring); SSE is only required
    for the OpenAI-compatible route.

### Scriptable responses

Each server supports `set_next(status, headers=None, body=None)` to queue the
next response (LIFO/pop semantics like the existing harness). The default
response (when the queue is empty) is a `200` with a valid body. A **hit
counter** and **per-status count** (`status_counts`) let tests assert exactly
how many times each status code was served — this is how retry behavior is
proven.

### Lifecycle

- Started in a pytest fixture; `base_url` (e.g. `http://127.0.0.1:<port>/v1`)
  and the Anthropic messages URL are derived from the bound port.
- `shutdown()` closes the server in teardown (daemon thread + `server_close`).
- No external dependency; deterministic; CI-friendly.

### Local provider note

`local` is pointed at the same `/v1` route via `local_server_url`
(`http://127.0.0.1:<port>/v1`). It uses the OpenAI-compatible request/response
shape, so the OpenAI route covers it.

---

## 3. Test Structure

New module: `backend/tests/integration/test_provider_mock_wiring.py`.

### Parametrization

A `@pytest.mark.parametrize` over the full provider list (Section 1). Each
provider is tagged with its SDK path (`openai_compat` | `anthropic`) so the
Anthropic-specific assertions/route are only applied where relevant. `local`
uses the `openai_compat` path with `local_server_url`.

### Per-provider test flow

1. **Mock up.** Start the mock server; record `base_url`. For Anthropic, also
   note the `/v1/messages` URL.
2. **Config up.** Create a **top-level committed** `UserModelConfig` pointing at
   the mock (mirror `make_fake_config` in `test_provider_resilience.py`):
   - Real `encrypt_api_key("sk-test")` so the SDK accepts the decrypted key
     (OpenAI SDK rejects empty keys).
   - `api_base_url` = mock URL for non-LOCAL providers; `local_server_url` for
     `local`.
   - Providers in `UserModelConfig._REQUIRES_EXPLICIT_BASE_URL` (AI21, Azure,
     Custom, OpenAI_COMPATIBLE) get the mock URL explicitly.
   - `requests_per_minute` and `max_concurrent_requests` set very high so the
     `provider_rate_limiter` bucket is pass-through (tests assert failover, not
     throttle spacing).
   - `status=ConnectionStatus.ACTIVE`, `is_active=True`.
3. **`test_connection`.** Call `ModelService.test_connection(config)`; assert
   `success=True`, non-empty `model`, and a parsed `response`.
4. **Happy path.**
   - Non-stream: `LLMClient.generate(agent, msg, config_id=cfg.id)` → assert
     `content`, `model`, `tokens_used` present.
   - Stream: `LLMClient.generate` is not used for streaming; instead call
     `provider.stream_generate(...)` directly and collect SSE chunks → assert
     full text reconstructs.
   - Tool-calling: build a minimal tool registry / executor and call
     `provider.generate_with_tools(...)`; assert the loop runs and returns final
     `content`.
5. **Failure path (resilience).**
   - `429` then `200`: script mock `set_next(429)` then default `200`; run
     `LLMClient.generate`; assert success **and** `status_counts[429] >= 1` and
     total hits ≥ 2 (proves retry happened).
   - `500` then `200`: assert transient retry + success.
   - `401` (permanent): point at a mock returning `401`; with a fallback config
     returning `200`, assert `LLMClient` rotates to the fallback **without**
     retrying the dead key (assert dead-key hits == 1, fallback hit == 1), and
     that `api_key_manager` marked the dead config failed.
6. **Teardown.** `shutdown()` mock; delete the config; reset
   `provider_rate_limiter` singleton and `LLMClient` circuit-breaker caches to
   avoid cross-test contamination.

### Assertions focus

Wiring correctness (correct URL hit, auth sent, parsed shape) and resilience
classification/counters. **No semantic/quality assertions** on response text.

---

## 4. Error Handling, Isolation & CI

- **Isolation:** Each provider gets its own mock instance and its own committed
  config via a fresh `NullPool` engine session (same visibility trick as
  `make_fake_config`: `ModelService.get_provider()` opens its own
  `get_db_context` session, so a test's savepoint commit is invisible until a
  top-level commit). Tests are independent and safe to run in parallel.
- **Cleanup:** Fixtures `yield` the mock + config and clean up (server shutdown,
  config delete, limiter/circuit-breaker reset) so ports and the test DB stay
  clean.
- **Rate limiter:** High `requests_per_minute` / concurrency per config →
  pass-through bucket. `provider_rate_limiter` is reset between tests.
- **Determinism:** All mock bodies are fixed JSON; no randomness, no real
  network. Fully reproducible in CI.
- **No CI change:** Suite lives under `backend/tests/integration/` and runs with
  the existing `make test-integration` / `pytest` harness (Celery eager mode,
  test Postgres + Redis already provisioned).
- **Mock reuse:** Extend the existing `FakeProviderServer` rather than
  duplicating; add the `/v1/messages` route and a streaming/SSE helper there or
  in the new module. Keep the existing harness intact for
  `test_provider_resilience.py`.

---

## 5. Acceptance Criteria

- `pytest backend/tests/integration/test_provider_mock_wiring.py` passes with
  zero real API keys configured.
- Every provider in Section 1 has a passing happy-path (non-stream + stream +
  tool-call) and failure-path (429/500/401) assertion.
- The suite is deterministic and runs green under `make test-integration`.
- No production code changes required beyond what the existing test harness
  already supports (reuse `make_fake_config`, `FakeProviderServer`,
  `encrypt_api_key`, `LLMClient`, `ModelService`, `provider_rate_limiter`).

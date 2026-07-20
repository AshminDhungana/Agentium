# Enable Deep Thinking Where Supported (Task 8.3) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Verify agents invoke extended/deep-thinking when configured, fix the defects that prevented it (Anthropic generation-aware thinking + `max_tokens` guard, OpenAI `xhigh` mapping), and surface observable thinking traces (logs + usage metadata).

**Architecture:** A single source of truth `_resolve_thinking_kwargs(config)` already drives every provider call site via `self._thinking_kwargs()`. We make it generation-aware for Anthropic (new-gen → adaptive+effort via `extra_body`; legacy → budget+`temperature:1`), add a `max_tokens` guard for legacy budgets, then add a structured log + `ModelUsageLog` metadata so thinking activation is observable. Tests prove the agent loop forwards the right params.

**Tech Stack:** Python 3, FastAPI/asyncio, `anthropic==0.84.0` (pinned; new-gen params sent via `extra_body` passthrough), `openai` SDK, pytest.

## Global Constraints

- `anthropic==0.84.0` is **pinned and must not be upgraded** — new-gen Anthropic params (`output_config`, `thinking:{type:"adaptive"}`) are sent via `extra_body` passthrough, which forwards them verbatim and bypasses SDK validation.
- `effort` values are exactly `none|low|medium|high|xhigh` (from `UserModelConfig.effort` + frontend `Effort` type). `none` MUST always resolve to `{}` so `is_thinking_config` stays correct for the chat "Thinking…" indicator.
- No DB migrations: `ModelUsageLog.request_metadata` is already a JSON column.
- No new UI components: the chat "Thinking…" indicator is already wired via `websocket.py` → `is_thinking_config(head_cfg)`.
- YAGNI: do not switch OpenAI to the Responses API; `reasoning_effort` is correct for Chat Completions.

---

### Task 1: Generation-aware Anthropic thinking resolution

**Files:**
- Modify: `backend/services/model_provider.py:503-540` (`_OPENAI_EFFORT`, `_ANTHROPIC_BUDGET`, add `_ANTHROPIC_EFFORT`, add `_ANTHROPIC_ADAPTIVE` + `_is_anthropic_adaptive`, rewrite the `kind == "anthropic"` branch in `_resolve_thinking_kwargs`)
- Test: `backend/tests/unit/test_model_provider_thinking.py` (correct the `test_anthropic_new_generation_*` assertions, add `test_anthropic_adaptive_effort_levels`)

**Interfaces:**
- Consumes: `PROVIDER_THINKING`, `re` (already imported), `UserModelConfig.effort`, `UserModelConfig.default_model`, `UserModelConfig.provider`.
- Produces: `_resolve_thinking_kwargs(config)` now returns, for new-gen Anthropic: `{"extra_body": {"thinking": {"type": "adaptive"}, "output_config": {"effort": <level>}}}`;
  for legacy Anthropic: `{"thinking": {"type": "enabled", "budget_tokens": <n>}, "temperature": 1}`; for `effort="none"` or unsupported: `{}`.

- [ ] **Step 1: Write/adjust the failing tests** (replace the broken assertions that encode the old `budget_tokens` behavior for new-gen models)

In `backend/tests/unit/test_model_provider_thinking.py`, change the three new-generation tests and add an effort-level test:

```python
def test_anthropic_new_generation_fable5():
    kw = _resolve_thinking_kwargs(_Cfg("ANTHROPIC", "claude-fable-5", "high"))
    assert kw["extra_body"]["thinking"] == {"type": "adaptive"}
    assert kw["extra_body"]["output_config"] == {"effort": "high"}


def test_anthropic_new_generation_opus48():
    kw = _resolve_thinking_kwargs(_Cfg("ANTHROPIC", "claude-opus-4-8", "high"))
    assert kw["extra_body"]["thinking"] == {"type": "adaptive"}
    assert kw["extra_body"]["output_config"] == {"effort": "high"}


def test_anthropic_new_generation_sonnet5():
    kw = _resolve_thinking_kwargs(_Cfg("ANTHROPIC", "claude-sonnet-5", "high"))
    assert kw["extra_body"]["thinking"] == {"type": "adaptive"}
    assert kw["extra_body"]["output_config"] == {"effort": "high"}


def test_anthropic_adaptive_effort_levels():
    for effort, level in [("low", "low"), ("medium", "medium"), ("high", "high"), ("xhigh", "xhigh")]:
        kw = _resolve_thinking_kwargs(_Cfg("ANTHROPIC", "claude-opus-4-8", effort))
        assert kw["extra_body"]["output_config"] == {"effort": level}


def test_anthropic_legacy_still_budget():
    # opus-4-5 / haiku-4-5 are legacy -> manual budget_tokens, not adaptive
    kw = _resolve_thinking_kwargs(_Cfg("ANTHROPIC", "claude-opus-4-5", "high"))
    assert kw["thinking"] == {"type": "enabled", "budget_tokens": 16000}
    assert kw["temperature"] == 1
    kw2 = _resolve_thinking_kwargs(_Cfg("ANTHROPIC", "claude-haiku-4-5", "xhigh"))
    assert kw2["thinking"] == {"type": "enabled", "budget_tokens": 32000}
```

- [ ] **Step 2: Run the tests to verify they FAIL** (code still emits `budget_tokens` for new-gen)

Run: `cd backend && python -m pytest tests/unit/test_model_provider_thinking.py -v -k "new_generation or adaptive"`
Expected: FAIL — `AssertionError` (code returns `budget_tokens`, not `extra_body.adaptive`).

- [ ] **Step 3: Implement the generation-aware resolution**

In `backend/services/model_provider.py`, edit lines 503-505 to add the effort map and a comment:

```python
_OPENAI_EFFORT = {"low": "low", "medium": "medium", "high": "high", "xhigh": "xhigh"}
_ANTHROPIC_BUDGET = {"low": 2000, "medium": 8000, "high": 16000, "xhigh": 32000}  # legacy (opus-4-5 / haiku-4-5) only
_ANTHROPIC_EFFORT = {"low": "low", "medium": "medium", "high": "high", "xhigh": "xhigh"}  # adaptive (fable/sonnet5/opus4.6+) models
_GEMINI_BUDGET = {"low": 1024, "medium": 4096, "high": 8192, "xhigh": 24576}
```

Insert the classifier immediately before `_resolve_thinking_kwargs` (after line 505):

```python
# New-gen Anthropic models reject manual `budget_tokens` (HTTP 400) and instead
# use adaptive thinking + an `effort` parameter. Sent via extra_body for SDK 0.84.0.
_ANTHROPIC_ADAPTIVE = re.compile(
    r"claude-(fable|mythos|opus[- ]?4[-.]?(6|7|8)|sonnet[- ]?4[-.]?6|sonnet[- ]?5)"
)

def _is_anthropic_adaptive(model: str) -> bool:
    """True for Anthropic models that require adaptive thinking (no budget_tokens)."""
    return bool(_ANTHROPIC_ADAPTIVE.search(model or ""))
```

Replace the `if kind == "anthropic":` branch (lines 526-530) with:

```python
    if kind == "anthropic":
        if _is_anthropic_adaptive(model):
            # SDK 0.84.0 lacks output_config/adaptive -> send via extra_body passthrough.
            return {"extra_body": {
                "thinking": {"type": "adaptive"},
                "output_config": {"effort": _ANTHROPIC_EFFORT[effort]},
            }}
        # Legacy: manual extended thinking. Call sites enforce max_tokens > budget.
        return {
            "thinking": {"type": "enabled", "budget_tokens": _ANTHROPIC_BUDGET[effort]},
            "temperature": 1,
        }
```

- [ ] **Step 4: Run the tests to verify they PASS**

Run: `cd backend && python -m pytest tests/unit/test_model_provider_thinking.py -v`
Expected: PASS (all, including corrected new-generation + legacy tests). Confirm `test_anthropic_new_generation_*` and `test_anthropic_legacy_still_budget` pass.

- [ ] **Step 5: Commit**

```bash
git add backend/services/model_provider.py backend/tests/unit/test_model_provider_thinking.py
git commit -m "fix(models): generation-aware Anthropic thinking (adaptive for new-gen)"
```

---

### Task 2: Anthropic `max_tokens` guard for legacy budgets

**Files:**
- Modify: `backend/services/model_provider.py` — add `_enforce_anthropic_budget_max_tokens` helper (place right after `_is_anthropic_adaptive`); call it in `AnthropicProvider.generate` (after line 1097 `create_kwargs.update(self._thinking_kwargs())`), `AnthropicProvider.stream_generate` (after line 1157 `stream_kwargs.update(self._thinking_kwargs())`), and `AnthropicProvider.generate_with_tools` (after line 1266 `create_kwargs.update(self._thinking_kwargs())`).

**Interfaces:**
- Consumes: `self._thinking_kwargs()` output (legacy form contains `thinking:{budget_tokens:N}`).
- Produces: `create_kwargs["max_tokens"]` is raised to `budget_tokens + 2048` when a legacy budget is present and `max_tokens` is too small (prevents the HTTP 400). Adaptive path is untouched.

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/unit/test_model_provider_thinking.py`:

```python
from services.model_provider import _enforce_anthropic_budget_max_tokens

def test_enforce_max_tokens_bumps_when_below_budget():
    ck = {"thinking": {"type": "enabled", "budget_tokens": 32000}, "max_tokens": 4000}
    _enforce_anthropic_budget_max_tokens(ck)
    assert ck["max_tokens"] == 34048  # 32000 + 2048

def test_enforce_max_tokens_keeps_larger_value():
    ck = {"thinking": {"type": "enabled", "budget_tokens": 2000}, "max_tokens": 8000}
    _enforce_anthropic_budget_max_tokens(ck)
    assert ck["max_tokens"] == 8000

def test_enforce_max_tokens_noop_without_budget():
    ck = {"max_tokens": 4000}
    _enforce_anthropic_budget_max_tokens(ck)
    assert ck["max_tokens"] == 4000
```

- [ ] **Step 2: Run to verify FAIL**

Run: `cd backend && python -m pytest tests/unit/test_model_provider_thinking.py -v -k enforce`
Expected: FAIL — `ImportError` (`_enforce_anthropic_budget_max_tokens` not defined).

- [ ] **Step 3: Implement the helper**

Insert after `_is_anthropic_adaptive`:

```python
def _enforce_anthropic_budget_max_tokens(create_kwargs: Dict[str, Any]) -> None:
    """Legacy manual thinking requires max_tokens > budget_tokens (else HTTP 400).

    Bumps max_tokens to budget_tokens + 2048 (headroom for the final answer) when
    too small. Adaptive thinking carries no budget, so it is unaffected.
    """
    thinking = create_kwargs.get("thinking")
    if isinstance(thinking, dict):
        budget = thinking.get("budget_tokens")
        if isinstance(budget, int):
            min_max = budget + 2048
            if create_kwargs.get("max_tokens", 0) < min_max:
                create_kwargs["max_tokens"] = min_max
```

- [ ] **Step 4: Apply at the three Anthropic call sites**

In `AnthropicProvider.generate`, after:
```python
            create_kwargs.update(self._thinking_kwargs())
```
add:
```python
            _enforce_anthropic_budget_max_tokens(create_kwargs)
```

In `AnthropicProvider.stream_generate`, after:
```python
            stream_kwargs.update(self._thinking_kwargs())
```
add:
```python
            _enforce_anthropic_budget_max_tokens(stream_kwargs)
```

In `AnthropicProvider.generate_with_tools`, after:
```python
                create_kwargs.update(self._thinking_kwargs())
```
add:
```python
                _enforce_anthropic_budget_max_tokens(create_kwargs)
```

- [ ] **Step 5: Run to verify PASS**

Run: `cd backend && python -m pytest tests/unit/test_model_provider_thinking.py -v -k enforce`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/services/model_provider.py backend/tests/unit/test_model_provider_thinking.py
git commit -m "fix(models): enforce max_tokens > budget for legacy Anthropic thinking"
```

---

### Task 3: OpenAI `xhigh` effort mapping

**Files:**
- Modify: `backend/services/model_provider.py:503` (`_OPENAI_EFFORT`)

**Interfaces:**
- Consumes: `effort` value from config (`xhigh`).
- Produces: OpenAI/OpenAI-compatible `extra_body.reasoning_effort` now maps `xhigh -> "xhigh"` (gpt-5.x supports it).

- [ ] **Step 1: Update the map**

Change line 503 from:
```python
_OPENAI_EFFORT = {"low": "low", "medium": "medium", "high": "high", "xhigh": "high"}
```
to:
```python
_OPENAI_EFFORT = {"low": "low", "medium": "medium", "high": "high", "xhigh": "xhigh"}
```

- [ ] **Step 2: Add a regression test**

Append to `backend/tests/unit/test_model_provider_thinking.py`:

```python
def test_openai_xhigh_maps_to_xhigh():
    kw = _resolve_thinking_kwargs(_Cfg("OPENAI", "gpt-5.6", "xhigh"))
    assert kw["extra_body"]["reasoning_effort"] == "xhigh"
```

- [ ] **Step 3: Run to verify PASS**

Run: `cd backend && python -m pytest tests/unit/test_model_provider_thinking.py::test_openai_xhigh_maps_to_xhigh -v`
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add backend/services/model_provider.py backend/tests/unit/test_model_provider_thinking.py
git commit -m "fix(models): map OpenAI xhigh effort to xhigh (gpt-5.x)"
```

---

### Task 4: Surface thinking traces (log + usage metadata)

**Files:**
- Modify: `backend/services/model_provider.py` — add `_thinking_mode_from_kwargs` helper; extend `_log_usage` to record thinking metadata in `request_metadata` and emit an INFO log when thinking is active.

**Interfaces:**
- Consumes: `self._thinking_kwargs()`, `self.config.effort`, `self.config.provider`, `model_used`, `completion_tokens`, `latency_ms` (all already available inside `_log_usage`).
- Produces: every `ModelUsageLog` row now carries `request_metadata` with `thinking_mode` (`adaptive|budget|openai|gemini|deepseek|none`), `effort`, `budget_tokens` (if any), `output_tokens`. An INFO log line is emitted when thinking is active.

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/unit/test_model_provider_thinking.py`:

```python
from services.model_provider import _thinking_mode_from_kwargs

def test_thinking_mode_labels():
    assert _thinking_mode_from_kwargs({}) == "none"
    assert _thinking_mode_from_kwargs({"thinking": {"type": "enabled", "budget_tokens": 8000}}) == "budget"
    assert _thinking_mode_from_kwargs({"extra_body": {"thinking": {"type": "adaptive"}, "output_config": {"effort": "high"}}}) == "adaptive"
    assert _thinking_mode_from_kwargs({"extra_body": {"reasoning_effort": "high"}}) == "openai"
    assert _thinking_mode_from_kwargs({"extra_body": {"thinkingConfig": {"thinkingBudget": 1024}}}) == "gemini"
    assert _thinking_mode_from_kwargs({"extra_body": {"thinking": {"type": "enabled"}, "reasoning_effort": "medium"}}) == "deepseek"
```

- [ ] **Step 2: Run to verify FAIL**

Run: `cd backend && python -m pytest tests/unit/test_model_provider_thinking.py -v -k thinking_mode`
Expected: FAIL — `ImportError`.

- [ ] **Step 3: Implement the helper + metadata + log**

Add the helper near `_is_anthropic_adaptive`:

```python
def _thinking_mode_from_kwargs(tk: Dict[str, Any]) -> str:
    """Classify the resolved thinking shape for logs/metadata."""
    if not tk:
        return "none"
    eb = tk.get("extra_body")
    if isinstance(eb, dict):
        if isinstance(eb.get("output_config"), dict) and "effort" in eb["output_config"]:
            return "adaptive"
        if "reasoning_effort" in eb:
            return "openai"
        if "thinkingConfig" in eb:
            return "gemini"
        if "thinking" in eb:
            return "deepseek"
    if isinstance(tk.get("thinking"), dict):
        return "budget"
    return "none"
```

In `_log_usage` (current signature `async def _log_usage(self, *, model_used, prompt_tokens, completion_tokens, latency_ms, success, error=None, agentium_id="system", request_type="chat")`), replace the `request_metadata` line:

```python
                    request_metadata={"agentium_id": agentium_id},
```
with:
```python
                    request_metadata={
                        "agentium_id": agentium_id,
                        "thinking_mode": _thinking_mode_from_kwargs(tk),
                        "effort": getattr(self.config, "effort", "none") or "none",
                        "budget_tokens": (
                            tk.get("thinking", {}).get("budget_tokens")
                            if isinstance(tk.get("thinking"), dict) else None
                        ),
                        "output_tokens": completion_tokens,
                    },
```
and, just before that `with get_db_context() as db:` block in `_log_usage`, compute `tk` and emit the log:

```python
        tk = self._thinking_kwargs()
        if tk:
            logger.info(
                "[thinking] active mode=%s provider=%s model=%s effort=%s budget=%s latency_ms=%d output_tokens=%d",
                _thinking_mode_from_kwargs(tk),
                getattr(self.config, "provider", "?"),
                model_used,
                getattr(self.config, "effort", "none") or "none",
                (tk.get("thinking", {}).get("budget_tokens")
                 if isinstance(tk.get("thinking"), dict) else None),
                latency_ms, completion_tokens,
            )
```

- [ ] **Step 4: Run to verify PASS**

Run: `cd backend && python -m pytest tests/unit/test_model_provider_thinking.py -v -k thinking_mode`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/services/model_provider.py backend/tests/unit/test_model_provider_thinking.py
git commit -m "feat(models): surface thinking traces in logs and usage metadata"
```

---

### Task 5: Agent-loop thinking forwarding test (NEW file)

**Files:**
- Create: `backend/tests/unit/test_agent_loop_thinking.py`

**Interfaces:**
- Consumes: `AnthropicProvider`, `OpenAICompatibleProvider` (from `services.model_provider`), `model_provider._get_cached_sdk_client`, `model_provider.provider_rate_limiter`, `model_provider._record_provider_headers`.
- Produces: proof that `provider.generate_with_tools(...)` forwards the correct thinking kwargs into the captured SDK `create`/`messages.create` call; and that `effort="none"` forwards nothing.

The test monkeypatches the SDK client builder and the rate limiter so no network/Redis is touched, then inspects `mock_client.messages.create.call_args.kwargs`.

- [ ] **Step 1: Write the test file**

Create `backend/tests/unit/test_agent_loop_thinking.py`:

```python
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from services import model_provider as mp


class _ThinkConfig:
    """Minimal UserModelConfig stand-in for provider construction."""
    def __init__(self, provider, model, effort="none", max_tokens=4000):
        self.id = "cfg-test"
        self.provider = provider
        self.default_model = model
        self.effort = effort
        self.max_tokens = max_tokens
        self.temperature = 0.7
        self.top_p = 1.0
        self.timeout_seconds = 60
        self.max_concurrent_requests = 10
        self.requests_per_minute = 60
        self.api_key_encrypted = None
        self.api_base_url = None
        self.base_url = None

    def requires_api_key(self):
        return False

    def get_effective_base_url(self):
        return None


@pytest.fixture
def mock_client(monkeypatch):
    client = MagicMock()
    client.messages.create = AsyncMock(return_value=SimpleNamespace(
        stop_reason="end_turn",
        content=[SimpleNamespace(type="text", text="answer")],
        usage=SimpleNamespace(input_tokens=10, output_tokens=20),
        model="claude-opus-4-8",
    ))
    client.chat.completions.create = AsyncMock(return_value=SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content="answer"), finish_reason="stop")],
        usage=SimpleNamespace(prompt_tokens=10, completion_tokens=20),
        model="gpt-5.6",
    ))
    monkeypatch.setattr(mp, "_get_cached_sdk_client", lambda *a, **k: client)
    # Rate limiter + header hooks are no-ops in the unit harness.
    monkeypatch.setattr(mp.provider_rate_limiter, "acquire_concurrency", AsyncMock())
    monkeypatch.setattr(mp.provider_rate_limiter, "release_concurrency", AsyncMock())
    monkeypatch.setattr(mp.provider_rate_limiter, "acquire", AsyncMock())
    monkeypatch.setattr(mp, "_record_provider_headers", AsyncMock())
    return client


async def _run(provider, config):
    prov = provider(config)
    return await prov.generate_with_tools(
        system_prompt="sys",
        messages=[{"role": "user", "content": "hi"}],
        tools=[],
        tool_executor=AsyncMock(return_value="{}"),
        max_iterations=1,
        agentium_id="test",
    )


def test_anthropic_adaptive_forwarded(mock_client):
    asyncio.run(_run(mp.AnthropicProvider, _ThinkConfig("ANTHROPIC", "claude-opus-4-8", "high")))
    kwargs = mock_client.messages.create.call_args.kwargs
    assert kwargs["extra_body"]["thinking"] == {"type": "adaptive"}
    assert kwargs["extra_body"]["output_config"] == {"effort": "high"}


def test_anthropic_legacy_budget_forwarded(mock_client):
    asyncio.run(_run(mp.AnthropicProvider, _ThinkConfig("ANTHROPIC", "claude-opus-4-5", "high")))
    kwargs = mock_client.messages.create.call_args.kwargs
    assert kwargs["thinking"] == {"type": "enabled", "budget_tokens": 16000}
    assert kwargs["max_tokens"] >= 16000 + 2048  # guard applied


def test_anthropic_none_forwards_no_thinking(mock_client):
    asyncio.run(_run(mp.AnthropicProvider, _ThinkConfig("ANTHROPIC", "claude-opus-4-8", "none")))
    kwargs = mock_client.messages.create.call_args.kwargs
    assert "extra_body" not in kwargs
    assert "thinking" not in kwargs


def test_openai_reasoning_effort_forwarded(mock_client):
    asyncio.run(_run(mp.OpenAICompatibleProvider, _ThinkConfig("OPENAI", "gpt-5.6", "xhigh")))
    kwargs = mock_client.chat.completions.create.call_args.kwargs
    assert kwargs["extra_body"]["reasoning_effort"] == "xhigh"
```

- [ ] **Step 2: Run to verify PASS**

Run: `cd backend && python -m pytest tests/unit/test_agent_loop_thinking.py -v`
Expected: PASS — all four forwarding assertions (adaptive, legacy+budget guard, none, openai).

- [ ] **Step 3: Commit**

```bash
git add backend/tests/unit/test_agent_loop_thinking.py
git commit -m "test(models): prove agent loop forwards thinking params per provider"
```

---

### Task 6: Full suite + lint

**Files:** (none new — verification only)

- [ ] **Step 1: Run the affected unit tests**

Run: `cd backend && python -m pytest tests/unit/test_model_provider_thinking.py tests/unit/test_agent_loop_thinking.py -v`
Expected: PASS (all).

- [ ] **Step 2: Run repo lint/typecheck if available**

Run: `cd backend && python -m ruff check services/model_provider.py 2>/dev/null || echo "ruff not configured; skipping"`
Expected: no new errors introduced.

- [ ] **Step 3: Commit any lint fixes (if produced)**

```bash
git add -A && git commit -m "style(models): lint fixes from deep-thinking verification" || echo "nothing to commit"
```

---

## Self-Review Notes (done by planner)

- **Spec coverage:** Section 1 (generation-aware resolution) → Task 1; Section 2 (`max_tokens` guard) → Task 2; Section 3 (OpenAI xhigh) → Task 3; Section 4 (log + usage metadata) → Task 4; Section 5 (tests, including corrected broken assertions + new agent-loop test) → Tasks 1 & 5. All spec sections mapped.
- **Placeholders:** None. Each step has concrete code or exact commands.
- **Type consistency:** `_resolve_thinking_kwargs`, `_is_anthropic_adaptive`, `_enforce_anthropic_budget_max_tokens`, `_thinking_mode_from_kwargs` names are identical across definition (Task 1/2/4) and use (Task 5). `extra_body`/`output_config`/`effort` keys match the spec exactly.
- **Cross-task dependency:** Task 5 imports `_get_cached_sdk_client`, `provider_rate_limiter`, `_record_provider_headers` — all existing module names; monkeypatched in the fixture. The legacy `max_tokens` guard (Task 2) is asserted in Task 5's `test_anthropic_legacy_budget_forwarded`, so Task 2 must land before Task 5 is trusted to pass.

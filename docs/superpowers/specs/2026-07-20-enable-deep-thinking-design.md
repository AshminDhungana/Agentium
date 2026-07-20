# Enable Deep Thinking Where Supported (Task 8.3)

**Date:** 2026-07-20
**Status:** Approved design, pending implementation plan
**Scope:** Verify agents actually invoke extended/deep-thinking when configured (5.6's `effort` setting), fix the real defects that prevent it, and surface observable thinking traces.

## Context

Task 8.3 from `docs/documents/todo_verify.md`:

> **Task:** For models with extended/deep-thinking support, confirm agents actually invoke that mode when configured to.
> **Acceptance criteria:** A thinking-capable model shows thinking traces/latency consistent with the mode being active when enabled via 5.6's setting.

"5.6's setting" is the `effort` control on a model config (`UserModelConfig.effort`, column added in Alembic `017_add_effort`, default `"none"`, values `none|low|medium|high|xhigh`). The frontend `ModelConfigForm.tsx` exposes it behind `supportsThinking(provider, model)`, which mirrors `PROVIDER_THINKING` in `backend/services/model_provider.py`.

### Existing wiring (as found)

- `UserModelConfig.effort` → `_resolve_thinking_kwargs(config)` → provider-specific kwargs.
- Every provider call site spreads `**self._thinking_kwargs()`:
  - `OpenAICompatibleProvider.generate` / `stream_generate` / `generate_with_tools`
  - `AnthropicProvider.generate` / `stream_generate` / `generate_with_tools`
  - `LocalProvider.generate`
- `ModelService.generate_with_agent_tools` (the agent-loop entry point used by `AgentOrchestrator._execute_task_inner`) builds the provider from the config and calls `provider.generate_with_tools(...)`, so `effort` reaches the loop automatically.
- The chat "Thinking…" indicator is already wired: `websocket.py` computes `is_thinking_config(head_cfg)` and sends `thinking: true` on `message_start`, which `ChatPage.tsx` renders via `TypingIndicator`.

### What web research (2026-07-20) revealed — the real gaps

The current `_resolve_thinking_kwargs` emits a single Anthropic shape for **all** Anthropic models:

```python
{"thinking": {"type": "enabled", "budget_tokens": _ANTHROPIC_BUDGET[effort]}, "temperature": 1}
```

Per the official Anthropic docs, this is **actively broken for the current model generation**:

- **New-gen models** (Claude Fable 5, Mythos 5, Sonnet 5, Opus 4.8, Opus 4.7, Opus 4.6, Sonnet 4.6, Mythos Preview) **reject manual `budget_tokens` with HTTP 400**. They use **adaptive thinking** (`thinking:{type:"adaptive"}`) with depth controlled by a top-level `output_config:{effort:...}` parameter. Some (Fable 5, Sonnet 5, Mythos) have thinking always-on and reject `thinking:{type:"disabled"}`.
- **Legacy models** (Claude Opus 4.5, Haiku 4.5, earlier 4.x) still support `thinking:{type:"enabled", budget_tokens:N}` + `temperature:1`. For these, `budget_tokens` **must be less than `max_tokens`** — and `UserModelConfig.max_tokens` defaults to **4000** while the xhigh budget is **32000**, so the agent loop 400s for every legacy thinking config too.
- The installed SDK is **pinned at `anthropic==0.84.0`**, which predates `output_config`/`adaptive`. New-gen params must therefore be sent via the SDK's `extra_body` passthrough (forwarded verbatim, bypasses SDK validation).
- OpenAI: `reasoning_effort` (in `extra_body`) is correct for Chat Completions (the `reasoning:{effort,summary}` shape is Responses-API-only — out of scope; Agentium uses Chat Completions). Gemini `thinkingConfig` shape is already correct.
- The **existing tests encode the bug**: `test_anthropic_new_generation_fable5/opus48/sonnet5` assert `budget_tokens` for exactly the models that 400 on it. These were added by the catalog-refresh work and must be corrected as part of this task.

## Target Changes

### 1. `backend/services/model_provider.py` — `_resolve_thinking_kwargs` (generation-aware)

Add a model-generation classifier and branch the Anthropic path:

```python
# New-gen Anthropic models: manual budget_tokens returns HTTP 400.
# They use adaptive thinking + an effort parameter instead.
_ANTHROPIC_ADAPTIVE = re.compile(
    r"claude-(fable|mythos|opus[- ]?4[-.]?(6|7|8)|sonnet[- ]?4[-.]?6|sonnet[- ]?5)"
)

def _is_anthropic_adaptive(model: str) -> bool:
    return bool(_ANTHROPIC_ADAPTIVE.search(model or ""))
```

Update `_ANTHROPIC_BUDGET` (legacy only) and add `_ANTHROPIC_EFFORT` (applies to adaptive):

```python
_ANTHROPIC_BUDGET = {"low": 2000, "medium": 8000, "high": 16000, "xhigh": 32000}  # legacy only
_ANTHROPIC_EFFORT = {"low": "low", "medium": "medium", "high": "high", "xhigh": "xhigh"}
```

In `_resolve_thinking_kwargs`, the `kind == "anthropic"` branch becomes:

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

Contract preserved: `effort == "none"` still returns `{}` (so `is_thinking_config` stays correct for the chat indicator), and unsupported providers/models still return `{}`.

### 2. `backend/services/model_provider.py` — Anthropic `max_tokens` guard

Add a helper and call it at the three Anthropic call sites (`generate`, `stream_generate`, `generate_with_tools`) immediately after `create_kwargs.update(self._thinking_kwargs())`:

```python
def _enforce_anthropic_budget_max_tokens(create_kwargs: Dict[str, Any]) -> None:
    """Legacy manual thinking requires max_tokens > budget_tokens (else HTTP 400)."""
    thinking = create_kwargs.get("thinking")
    if isinstance(thinking, dict):
        budget = thinking.get("budget_tokens")
        if isinstance(budget, int):
            min_max = budget + 2048  # headroom for the final answer
            if create_kwargs.get("max_tokens", 0) < min_max:
                create_kwargs["max_tokens"] = min_max
```

Adaptive path needs no bump (no budget). This fixes the 400 on every legacy thinking config.

### 3. OpenAI effort mapping (minor)

`_OPENAI_EFFORT` currently maps `xhigh → "high"`. Change to `xhigh → "xhigh"` so gpt-5.x gets the intended depth (the provider supports it). Leave `none` handling as-is (returns `{}`).

### 4. `backend/services/model_provider.py` — surfaced thinking traces

- **Structured log** in each provider's `_log_usage` (or a shared wrapper) when thinking was active. Capture `thinking_mode` (`adaptive` | `budget` | `openai` | `gemini` | `deepseek` | `none`), `effort`, `budget_tokens` (if any), and `output_tokens`. Emit:
  `logger.info("[thinking] active mode=%s provider=%s model=%s effort=%s budget=%s latency_ms=%d output_tokens=%d", ...)`.
- **Usage metadata**: extend `ModelUsageLog.request_metadata` (JSON column, already used for `agentium_id`) with `thinking_mode`, `effort`, `budget_tokens`, `output_tokens`. `request_metadata` is a `JSON` column — no migration needed.

### 5. Tests

- **`backend/tests/unit/test_model_provider_thinking.py`** — correct the broken assertions:
  - `test_anthropic_new_generation_fable5/opus48/sonnet5` → assert `extra_body.thinking.type == "adaptive"` and `extra_body.output_config.effort == "high"` (no `budget_tokens`).
  - Keep legacy asserts (`claude-opus-4-5`, `claude-haiku-4-5`) as budget form.
  - Add `test_anthropic_adaptive_effort_levels` (low/medium/high/xhigh → correct `output_config.effort`).
- **NEW `backend/tests/unit/test_agent_loop_thinking.py`** — build a `UserModelConfig` (effort per level), mock the SDK client, instantiate the provider, call `generate_with_tools(...)`, and assert the captured `create`/`messages.create` kwargs contain the correct thinking params. Mirror for `effort="none"` (assert absent). This proves the **agent loop** forwards thinking, satisfying the acceptance criterion at the loop level.

## Data Flow (unchanged, now correct)

1. User sets `effort` on a model config (Models page, 5.6 setting).
2. `AgentOrchestrator` allocates that config → `ModelService.generate_with_agent_tools(config_id=...)` builds the provider.
3. Provider's `generate_with_tools` merges `_thinking_kwargs()` → correct per-generation shape (adaptive+effort for new Anthropic, budget+temp for legacy, `extra_body` for OpenAI/Gemini/DeepSeek).
4. Call fires; for legacy Anthropic the `max_tokens` guard prevents the 400.
5. Usage is logged with thinking metadata + an INFO trace; chat "Thinking…" indicator reflects `is_thinking_config`.

## Error Handling

- `effort="none"` → `{}` everywhere; no behavior change, `is_thinking_config` contract intact.
- Unsupported provider/model (regex miss) → `{}`; the UI already hides the effort control for those.
- Adaptive params sent via `extra_body` so the pinned `anthropic==0.84.0` SDK is not required to understand them; if a future SDK version rejects `extra_body` passthrough, the call degrades to a normal (non-thinking) request rather than crashing the loop.
- New-gen Anthropic defaults `display:"omitted"` for thinking text, so raw thinking text is not returned over the wire. **Documented limitation:** the observable trace is latency + token count (thinking tokens counted in `output_tokens`), which satisfies the acceptance criterion. We do not force `display:"summarized"` (adds latency).

## Testing

- `pytest backend/tests/unit/test_model_provider_thinking.py -v` — corrected + new unit assertions pass.
- `pytest backend/tests/unit/test_agent_loop_thinking.py -v` — agent-loop forwarding proven for each provider/effort.
- Manual (optional, needs live keys): set `effort=high` on an Anthropic new-gen config, run a Head chat, confirm the "Thinking…" indicator shows and `ModelUsageLog` carries `thinking_mode:"adaptive"` with elevated latency/output tokens; repeat with `effort=none` to confirm no thinking kwargs are sent.

## Out of Scope

- Switching OpenAI to the Responses API (`reasoning:{effort,summary}`) — Agentium is Chat-Completions-based; `reasoning_effort` is correct there.
- Surfacing raw thinking text in the chat UI (provider returns omitted thinking for new-gen; would add latency).
- Upgrading the `anthropic` SDK (kept pinned at 0.84.0; `extra_body` passthrough covers the new params).
- Editing the catalog-refresh plan itself — but its `test_anthropic_new_generation_*` assertions are corrected here as a required side effect.

## Files Touched

- `backend/services/model_provider.py` (`_resolve_thinking_kwargs`, `_ANTHROPIC_BUDGET`/`_ANTHROPIC_EFFORT`, `_is_anthropic_adaptive`, `_enforce_anthropic_budget_max_tokens`, log + usage metadata)
- `backend/tests/unit/test_model_provider_thinking.py` (correct broken assertions)
- `backend/tests/unit/test_agent_loop_thinking.py` (NEW — agent-loop forwarding)

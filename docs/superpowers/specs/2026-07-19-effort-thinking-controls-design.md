# Design: Extended-Thinking / Effort Controls on Model Config (5.6)

**Date:** 2026-07-19
**Status:** Approved design (pending user review of written spec)

## Goal

Add a model-level **Reasoning Effort** control to the Model Configuration page. The
value is wired through to each provider's native extended-thinking / reasoning-effort
parameter where supported, and is a no-op where unsupported. While a generation that
uses thinking is in progress, the chat page shows a **"Thinking…"** label instead of
the animated three-dot typing indicator.

## Effort value scheme

```
none | low | medium | high | xhigh
```

- `none` — thinking disabled. Nothing is injected into the provider call; `temperature`
  behaves normally. This is the default.
- `low|medium|high|xhigh` — thinking enabled at increasing intensity. Mapped per
  provider (see Wiring).

## Support detection — every provider in the Model Config page

The Model Config page exposes these providers (from `list_providers()` + the
Custom/Universal card): `OPENAI`, `ANTHROPIC`, `GEMINI`, `GROQ`, `MISTRAL`,
`TOGETHER`, `COHERE`, `MOONSHOT`, `DEEPSEEK`, `AZURE_OPENAI`, `LOCAL`, and
`CUSTOM` (OpenAI-compatible). The control must be accounted for on **all** of them.

Each provider maps to a thinking *strategy*. A single registry
`PROVIDER_THINKING` (in `model_provider.py`, mirrored on the frontend as a small
`providerThinking` table in `ModelConfigForm.tsx`) defines, per provider:

- `param_kind`: how the effort value is translated — one of
  `reasoning_effort` (OpenAI-style), `anthropic_thinking`, `gemini_thinking`,
  `deepseek_thinking`, or `none`.
- `model_hint`: an optional regex on `default_model`. When present, the control is
  only **shown** (and the param only **emitted**) if the model name matches. When
  `None`, the provider's API always accepts the thinking param, so the control is
  always shown for that provider.
- `always_show`: when `True` and there is no `model_hint`, the control renders for
  every model of that provider.

| Provider        | param_kind            | model_hint (shown/emitted only if matches)        |
|-----------------|-----------------------|--------------------------------------------------|
| `OPENAI`        | `reasoning_effort`    | `o1`, `o3`, `o4`, `gpt-5.*`                    |
| `AZURE_OPENAI`  | `reasoning_effort`    | same as OPENAI                                   |
| `ANTHROPIC`     | `anthropic_thinking`  | none (Claude Opus/Haiku 4.5 + earlier support thinking) |
| `GEMINI`        | `gemini_thinking`     | none (Gemini 2.5 Flash/Pro support thinking)     |
| `DEEPSEEK`      | `deepseek_thinking`   | `reasoner` (and `v4` reasoning modes)            |
| `GROQ`          | `reasoning_effort`    | `gpt-oss`, `qwen`, `r1`, `qwq`, `reason`         |
| `MISTRAL`       | `reasoning_effort`    | `magistral`, `thinking`                          |
| `TOGETHER`      | `reasoning_effort`    | `r1`, `qwq`, `reasoner`, `thinking`, `gpt-oss` |
| `MOONSHOT`      | `deepseek_thinking`   | `k2`, `kimi` (Kimi thinking)                    |
| `LOCAL`         | `reasoning_effort`    | `qwq`, `r1`, `deepseek`, `thinking`, `z1`, `qwen3` |
| `CUSTOM`        | `reasoning_effort`    | `o1/o3/o4`, `qwq`, `r1`, `reasoner`, `thinking`, `gpt-oss` |
| `COHERE`        | `none`                | — (Command models have no native extended thinking; control hidden) |

> **Implementation note:** Exact parameter *shape* must be verified against the real
> call site in `model_provider.py` (chat/completions vs Responses API). OpenAI's
> current API takes `reasoning: {effort: "..."}` on the Responses API but many
> OpenAI-compatible servers (and older chat/completions) still accept the flat
> `reasoning_effort` field — the helper is the single choke point, so this is the
> only place that needs adjustment.

If a provider/model combination is unsupported, the saved value is coerced to `none`
and no provider param is emitted (no-op). This satisfies the "present only for models
that support it (or is a no-op/hidden otherwise)" acceptance criterion for **every**
provider in the page.

## Backend changes

### ORM — `backend/models/entities/user_config.py`
- New column on `UserModelConfig` (after `timeout_seconds`):
  ```python
  effort = Column(String(16), default="none", nullable=False,
                  comment="Reasoning effort: none|low|medium|high|xhigh")
  ```
- Existing rows default to `none`.

### API schema — `backend/api/routes/models.py`
- `ModelConfigCreate`: `effort: str = "none"` with a `field_validator` constraining
  to the 5 allowed values (raises `ValueError` otherwise → 422 with a clear message).
- `ModelConfigUpdate`: `effort: Optional[str] = None` with the same validator.
- `ModelConfigResponse`: `effort: str = "none"`; included in `_serialize_config`'s
  `settings` dict as `effort`.
- `create_config` / `update_config`: write `effort=config.effort` into the
  `UserModelConfig` row.

### Provider wiring — `backend/services/model_provider.py`
The actual LLM call builders (around lines 491, 564, 722, 995, 1051) read
`self.config.effort` and the resolved `param_kind` for the config's provider. A single
helper `_resolve_thinking_param(effort, provider, model)` consults `PROVIDER_THINKING`
and returns the provider-specific kwarg dict, or `{}` when effort is `none` / the
provider or model is unsupported. Effort → provider-param mapping:

- **`reasoning_effort`** (OpenAI, Azure OpenAI, Groq, Mistral, Together, Local,
  Custom/OpenAI-compatible):
  chat/completions form → `{"reasoning_effort": V}` where
  `V = {"low":"low","medium":"medium","high":"high","xhigh":"high"}[effort]`;
  Responses-API form (if `model_provider.py` uses `/responses`) →
  `{"reasoning": {"effort": V, "summary": "auto"}}`. `xhigh` caps at `"high"`
  (OpenAI's max for `reasoning_effort`; GPT-OSS on Groq caps at `high` too).
  Omitted when `none` or the model doesn't match `model_hint`.

- **`anthropic_thinking`** (Anthropic Claude Opus/Haiku 4.5 and earlier):
  `{"thinking": {"type": "enabled", "budget_tokens": B}}` where
  `B = {"low":2000,"medium":8000,"high":16000,"xhigh":32000}[effort]`.
  When thinking is on, `temperature` is forced to `1` (required by Anthropic)
  — applied only in the thinking branch.

- **`gemini_thinking`** (Gemini):
  `{"thinkingConfig": {"thinkingBudget": B, "includeThoughts": True}}` where
  `B = {"low":1024,"medium":4096,"high":8192,"xhigh":24576}[effort]`.

- **`deepseek_thinking`** (DeepSeek reasoner, Moonshot Kimi):
  `{"thinking": {"type": "enabled"}, "reasoning_effort": V}` where `V` maps as
  above (`xhigh`→`high`). Both fields are accepted by the DeepSeek/Kimi
  OpenAI-compatible API; budget is provider-managed, so effort scales the
  `reasoning_effort` knob.

- **`none`** (Cohere, and any unsupported provider/model): returns `{}` (no-op).

The helper is the single source of truth: it returns `{}` for any unsupported
combo, so a thinking param is **never** sent to a provider/model that would reject
it. This makes the no-op path robust across all 12 providers in the page.

### WebSocket signal — chat generation
When the Head's active config has `effort != "none"` and the provider supports it,
stamp `thinking: true` onto the `message_start` event metadata so the frontend can
render the "Thinking…" label.

## Frontend changes

### Types — `frontend/src/types/index.ts`
- Add `effort?: 'none' | 'low' | 'medium' | 'high' | 'xhigh'` to `ModelConfig`.
- Add `effort` to `ModelConfig['settings']` (kept in settings for serialization parity).

### Service — `frontend/src/services/models.ts`
- Add `effort?: string` to `createConfig` and `updateConfig` payload shapes.

### Form — `frontend/src/components/models/ModelConfigForm.tsx`
- Add `effort: 'none'` to `formData` initial state and to the edit-prep effect.
- A `supportsThinking` boolean derived from `(formData.provider, formData.default_model)`
  using the same detection table.
- Inside **Advanced Settings**, render a "Reasoning Effort" `<select>` (none/low/
  medium/high/xhigh) **only when `supportsThinking` is true**. Included in both the
  test payload and the submit payload (`base`).

### Typing indicator — `frontend/src/components/chat/TypingIndicator.tsx`
- New prop `thinking?: boolean`. When true, render a `Thinking…` text label
  (theme-consistent, `aria-live="polite"`) instead of the three-dot shimmer. Keep
  `data-testid="typing-indicator"` for tests.

### Chat page — `frontend/src/pages/ChatPage.tsx`
- On `message_start`, capture `thinking` from `msg.metadata`. Track it in state
  (`isThinking`) and pass `thinking={isThinking}` to `<TypingIndicator />`. Reset to
  `false` on `message_delta` / `message_end` / legacy `message` (same points where
  `setIsAwaitingReply(false)` is already called).

## Error handling
- Invalid effort value from API → Pydantic 422 with explicit message (no page crash,
  consistent with existing `extractErrorMessage` handling in the form).
- Provider rejects thinking param (e.g. non-reasoning model) → call still proceeds
  with the param omitted (graceful degradation): the helper is the single source of
  truth and returns `{}` for unsupported combos, so we never send thinking to a
  model that rejects it.

## Testing
- Backend unit test: `_resolve_thinking_param` emits correct kwarg per provider/effort
  and `{}` for `none`/unsupported.
- Backend test: `ModelConfigCreate` rejects invalid effort; `ModelConfigResponse`
  round-trips `effort`.
- Frontend `ChatPage.typing.test.tsx`: extend to assert the "Thinking…" label renders
  when `thinking` prop is true, and that `typing-indicator` test id is preserved.
- `supportsThinking` detection covered by a small unit test on the matcher helper.

## Out of scope (YAGNI)
- Per-message effort override in the chat composer.
- Persistence of thinking scratchpad text to the user (the reasoning_trace service
  already captures agent-side thinking separately).
- UI for non-Head agents' effort configs.

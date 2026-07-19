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

## Support detection (which models get the control)

The setting is **only rendered for models that support extended thinking**, satisfying
the "present only for models that support it" acceptance criterion. Detection is a
prefix/contains match on `(provider, default_model)`:

| Provider        | Match rule (model name contains)                |
|-----------------|------------------------------------------------|
| `OPENAI`        | `o1`, `o3`, `o4`, `gpt-5` (reasoning-capable) |
| `ANTHROPIC`     | `claude` (opus/sonnet/haiku 4.x all support thinking) |
| `DEEPSEEK`      | `reasoner`                                     |
| `QIANWEN`/`ZHIPU`/`MOONSHOT` | any (best-effort)                     |
| all others       | not shown (control hidden, value stays `none`)  |

If unsupported, the saved value is coerced to `none` and no provider param is emitted.

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
`self.config.effort`. A small helper `_resolve_thinking_param(effort, provider, model)`
returns the provider-specific kwarg dict or `{}`:

- **OpenAI-compatible reasoning** (`reasoning_effort`):
  `{"reasoning_effort": {"none":None,"low":"low","medium":"medium","high":"high","xhigh":"high"}[effort]}`
  — `xhigh` caps at `"high"` (OpenAI's max). Omitted entirely when `none`.
- **Anthropic** (`thinking`):
  `{"thinking": {"type": "enabled", "budget_tokens": B}}` where `B` scales
  `low=2000, medium=8000, high=16000, xhigh=32000`. When thinking is on,
  `temperature` is forced to `1` (required by Anthropic) — applied only in the
  thinking branch.
- **DeepSeek reasoner**: passes `{"thinking": True}` (or provider-specific flag).
- **All other providers / unsupported models**: returns `{}` (no-op).

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

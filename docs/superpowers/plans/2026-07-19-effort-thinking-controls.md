# Effort / Extended-Thinking Controls — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a Reasoning Effort control to the Model Config page that wires through to each provider's native extended-thinking / reasoning-effort parameter where supported (no-op otherwise), and show a "Thinking…" label in the chat instead of the three-dot indicator while thinking is active.

**Architecture:** A single `_resolve_thinking_kwargs(config)` helper in `model_provider.py` is the only place provider params are computed — it consults a `PROVIDER_THINKING` registry (per-provider `kind` + model-name `model_hint`). The `effort` value is stored on `UserModelConfig` and surfaced through the Pydantic schemas, the React form, and a WebSocket `thinking` flag that drives the chat label.

**Tech Stack:** Python / FastAPI / SQLAlchemy / Alembic (backend), React 18 + TypeScript + Vite (frontend). OpenAI-compatible SDK (`extra_body` for reasoning params), Anthropic native SDK (`thinking=`).

## Global Constraints

- Effort values are exactly: `none | low | medium | high | xhigh`. `none` is the default and always a no-op.
- The control is **only rendered** for providers/models that support thinking (per `PROVIDER_THINKING`); Cohere is hidden entirely.
- The `_resolve_thinking_kwargs` helper is the **single source of truth** — it returns `{}` for any unsupported provider/model, so a thinking param is never sent to a provider that would reject it.
- Exact OpenAI param shape (`reasoning_effort` via chat/completions `extra_body`, vs `reasoning:{effort}` on the Responses API) must be verified against the real call site in `model_provider.py`; the chat/completions path uses `extra_body={"reasoning_effort": ...}`.
- Verified provider params (from official docs):
  - OpenAI-compatible: `reasoning_effort` (o1/o3/o4/gpt-5). Values: low/medium/high/xhigh (xhigh caps at "high").
  - Anthropic (Claude Opus/Haiku 4.5 + earlier): `thinking={type:"enabled", budget_tokens:N}`; force `temperature=1` when thinking on.
  - Gemini (2.5 Flash/Pro): `thinkingConfig={thinkingBudget:N, includeThoughts:true}`.
  - DeepSeek / Moonshot Kimi: both `thinking={type:"enabled"}` and `reasoning_effort`.
  - Groq: `reasoning_effort` (GPT-OSS low/medium/high; Qwen3.6 none/default). Mistral/Together/Local/Custom: `reasoning_effort` via OpenAI-compatible.
- TDD, frequent commits, no placeholders.

---

## File Structure

- `backend/models/entities/user_config.py` — add `effort` column to `UserModelConfig`.
- `backend/alembic/versions/<new>.py` — migration adding the `effort` column.
- `backend/api/routes/models.py` — add `effort` to `ModelConfigCreate`, `ModelConfigUpdate`, `ModelConfigResponse`; include in `_serialize_config`; write in `create_config`/`update_config`.
- `backend/services/model_provider.py` — add `PROVIDER_THINKING` registry, module-level `_resolve_thinking_kwargs(config)`, instance `_thinking_kwargs()`, and inject into every `client.chat.completions.create` / `client.messages.create` call.
- `backend/api/routes/websocket.py` — stamp `thinking: true` on `message_start` when the Head's active config is a thinking config.
- `backend/tests/unit/test_model_provider_thinking.py` — unit tests for the resolver.
- `frontend/src/types/index.ts` — add `effort` to `ModelConfig` + `settings`.
- `frontend/src/services/models.ts` — add `effort` to `createConfig`/`updateConfig` payload types.
- `frontend/src/components/models/ModelConfigForm.tsx` — effort field, `supportsThinking()` detection, render + include in payloads.
- `frontend/src/components/chat/TypingIndicator.tsx` — `thinking` prop → "Thinking…" label.
- `frontend/src/pages/ChatPage.tsx` — capture `thinking` from `message_start`, pass to `TypingIndicator`.
- `frontend/src/pages/ChatPage.typing.test.tsx` — extend with the label test.

---

### Task 1: Add `effort` ORM column + migration

**Files:**
- Modify: `backend/models/entities/user_config.py:99` (after `timeout_seconds`)
- Create: `backend/alembic/versions/00NN_add_effort.py`

**Interfaces:**
- Produces: `UserModelConfig.effort` (str, default `"none"`).

- [ ] **Step 1: Add the column**

In `user_config.py`, after `timeout_seconds = Column(Integer, default=60)` (line 103), add:

```python
    # Reasoning effort for extended-thinking providers
    effort = Column(String(16), default="none", nullable=False,
                  comment="Reasoning effort: none|low|medium|high|xhigh")
```

- [ ] **Step 2: Create the migration**

First find the current Alembic head, then create a new revision file:

Run: `cd backend && alembic history -l1`
Expected: prints the current head revision id, e.g. `000_combined_migration` (use whatever the latest is).

Create `backend/alembic/versions/<next>_add_effort.py` where `<next>` is the next free 4-digit number after the latest version file. Set `down_revision` to the head id from the previous command:

```python
"""add effort column to user_model_configs

Revision ID: <next>_add_effort
Revises: <current_head_revision_id>
Create Date: 2026-07-19
"""
from alembic import op
import sqlalchemy as sa

revision = "<next>_add_effort"
down_revision = "<current_head_revision_id>"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "user_model_configs",
        sa.Column("effort", sa.String(16), nullable=False, server_default="none"),
    )


def downgrade():
    op.drop_column("user_model_configs", "effort")
```

- [ ] **Step 3: Verify import + migration compiles**

Run: `cd backend && python -c "from models.entities.user_config import UserModelConfig; print(UserModelConfig.effort)"`
Expected: `<sqlalchemy.orm.attributes.InstrumentedAttribute object at ...>` (no ImportError).

- [ ] **Step 4: Commit**

```bash
git add backend/models/entities/user_config.py backend/alembic/versions/00NN_add_effort.py
git commit -m "feat: add effort column to UserModelConfig with migration"
```

---

### Task 2: API schemas — effort in/out

**Files:**
- Modify: `backend/api/routes/models.py:39` (`ModelConfigCreate`), `:77` (`ModelConfigUpdate`), `:94` (`ModelConfigResponse`), `:256` (`_serialize_config`), `:443` (`create_config` row), `:469` area (`update_config` row)

**Interfaces:**
- Consumes: `UserModelConfig.effort` (Task 1)
- Produces: validated `effort` field on all three schemas; persisted on create/update.

- [ ] **Step 1: Add validator + fields**

After the imports in `models.py`, add:

```python
_VALID_EFFORTS = {"none", "low", "medium", "high", "xhigh"}


def _validate_effort(v: str) -> str:
    if v not in _VALID_EFFORTS:
        raise ValueError("effort must be one of: none, low, medium, high, xhigh")
    return v
```

In `ModelConfigCreate` (after `timeout_seconds` line 52):

```python
    effort: str = Field(default="none")
```

In `ModelConfigUpdate` (after `timeout_seconds` line 91):

```python
    effort: Optional[str] = None
```

In `ModelConfigResponse` (after `settings` line 109):

```python
    effort: str = "none"
```

- [ ] **Step 2: Validate + serialize**

Add a `field_validator` to `ModelConfigCreate` (near the existing `_normalize_provider` validator):

```python
    @field_validator('effort')
    @classmethod
    def _check_effort(cls, v):
        return _validate_effort(v)
```

Add the same validator to `ModelConfigUpdate` (guard `None`):

```python
    @field_validator('effort')
    @classmethod
    def _check_effort(cls, v):
        return _validate_effort(v) if v is not None else v
```

In `_serialize_config` (line 256 `settings` dict), add `effort` at the top level:

```python
        'effort':        config.effort or 'none',
        'settings': {
            'max_tokens':  config.max_tokens,
            'temperature': config.temperature,
            'top_p':       config.top_p,
            'timeout':     config.timeout_seconds,
            'effort':      config.effort or 'none',
        },
```

- [ ] **Step 3: Persist on create + update**

In `create_config`, add `effort=config.effort,` to the `UserModelConfig(...)` constructor (after `timeout_seconds=...`, ~line 458).

In `update_config`, after handling `max_tokens`/`temperature`, add an `effort` branch:

```python
    if config.effort is not None:
        db_config.effort = _validate_effort(config.effort)
        flag_modified(db_config, "effort")
```

- [ ] **Step 4: Run the models route import**

Run: `cd backend && python -c "import api.routes.models as m; print('ok')"`
Expected: `ok`

- [ ] **Step 5: Commit**

```bash
git add backend/api/routes/models.py
git commit -m "feat: surface effort in model config schemas"
```

---

### Task 3: Provider wiring — `_resolve_thinking_kwargs`

**Files:**
- Modify: `backend/services/model_provider.py` (add registry + helper near top, inject into calls at lines 485, 557, 719, 993, 1041, 1108, 1324)

**Interfaces:**
- Consumes: `UserModelConfig.effort`, `.provider`, `.default_model` (Tasks 1–2)
- Produces: `BaseModelProvider._thinking_kwargs()` returning a kwargs dict (or `{}`).

- [ ] **Step 1: Write the failing test**

Create `backend/tests/unit/test_model_provider_thinking.py`:

```python
import pytest
from services.model_provider import _resolve_thinking_kwargs, PROVIDER_THINKING


class _Cfg:
    def __init__(self, provider, model, effort="none"):
        self.provider = provider
        self.default_model = model
        self.effort = effort


def test_none_is_noop():
    assert _resolve_thinking_kwargs(_Cfg("OPENAI", "gpt-4o", "none")) == {}


def test_unsupported_provider_hidden():
    # Cohere is not in the registry
    assert "COHERE" not in PROVIDER_THINKING
    assert _resolve_thinking_kwargs(_Cfg("COHERE", "command-r", "high")) == {}


def test_openai_effort():
    kw = _resolve_thinking_kwargs(_Cfg("OPENAI", "o4-mini", "high"))
    assert kw == {"extra_body": {"reasoning_effort": "high"}}


def test_openai_model_hint_misses():
    # gpt-4o is not a reasoning model
    assert _resolve_thinking_kwargs(_Cfg("OPENAI", "gpt-4o", "high")) == {}


def test_anthropic_budget_and_temp():
    kw = _resolve_thinking_kwargs(_Cfg("ANTHROPIC", "claude-opus-4-5", "xhigh"))
    assert kw["thinking"] == {"type": "enabled", "budget_tokens": 32000}
    assert kw["temperature"] == 1


def test_deepseek_both_params():
    kw = _resolve_thinking_kwargs(_Cfg("DEEPSEEK", "deepseek-reasoner", "medium"))
    assert kw["extra_body"]["thinking"] == {"type": "enabled"}
    assert kw["extra_body"]["reasoning_effort"] == "medium"


def test_gemini_thinking_config():
    kw = _resolve_thinking_kwargs(_Cfg("GEMINI", "gemini-2.5-pro", "low"))
    assert kw["extra_body"]["thinkingConfig"]["thinkingBudget"] == 1024
    assert kw["extra_body"]["thinkingConfig"]["includeThoughts"] is True


def test_local_hint_misses():
    assert _resolve_thinking_kwargs(_Cfg("LOCAL", "llama3.1", "high")) == {}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/unit/test_model_provider_thinking.py -v`
Expected: FAIL — `ImportError: cannot import name '_resolve_thinking_kwargs'`

- [ ] **Step 3: Add registry + helper**

In `model_provider.py`, near the top (after imports, before class definitions ~line 340), add:

```python
import re

# Per-provider extended-thinking strategy. `kind` selects the param shape;
# `model_hint` (optional regex) gates both UI visibility and param emission.
PROVIDER_THINKING = {
    "OPENAI":        {"kind": "openai",   "model_hint": r"(^|[-/])(o1|o3|o4|gpt-5)"},
    "AZURE_OPENAI": {"kind": "openai",   "model_hint": r"(^|[-/])(o1|o3|o4|gpt-5)"},
    "ANTHROPIC":     {"kind": "anthropic"},
    "GEMINI":        {"kind": "gemini"},
    "DEEPSEEK":      {"kind": "deepseek", "model_hint": r"reasoner|v4"},
    "GROQ":          {"kind": "openai",   "model_hint": r"gpt-oss|qwen|r1|qwq|reason"},
    "MISTRAL":       {"kind": "openai",   "model_hint": r"magistral|thinking"},
    "TOGETHER":      {"kind": "openai",   "model_hint": r"r1|qwq|reasoner|thinking|gpt-oss"},
    "MOONSHOT":      {"kind": "deepseek", "model_hint": r"k2|kimi"},
    "LOCAL":         {"kind": "openai",   "model_hint": r"qwq|r1|deepseek|thinking|z1|qwen3"},
    "CUSTOM":        {"kind": "openai",
                     "model_hint": r"(^|[-/])(o1|o3|o4|gpt-5)|qwq|r1|reasoner|thinking|gpt-oss"},
    # COHERE intentionally omitted -> no thinking
}

_OPENAI_EFFORT = {"low": "low", "medium": "medium", "high": "high", "xhigh": "high"}
_ANTHROPIC_BUDGET = {"low": 2000, "medium": 8000, "high": 16000, "xhigh": 32000}
_GEMINI_BUDGET = {"low": 1024, "medium": 4096, "high": 8192, "xhigh": 24576}


def _resolve_thinking_kwargs(config) -> Dict[str, Any]:
    """Return provider-specific thinking kwargs, or {} when disabled/unsupported.

    This is the single source of truth: any provider/model combo that does
    not support extended thinking yields {}, so nothing is ever sent that the
    upstream would reject.
    """
    effort = (getattr(config, "effort", "none") or "none").lower()
    if effort == "none":
        return {}
    info = PROVIDER_THINKING.get(str(getattr(config, "provider", "")).upper())
    if not info:
        return {}
    model = (getattr(config, "default_model", "") or "").lower()
    hint = info.get("model_hint")
    if hint and not re.search(hint, model):
        return {}
    kind = info["kind"]
    if kind == "anthropic":
        return {
            "thinking": {"type": "enabled", "budget_tokens": _ANTHROPIC_BUDGET[effort]},
            "temperature": 1,
        }
    if kind == "gemini":
        return {"extra_body": {"thinkingConfig": {
            "thinkingBudget": _GEMINI_BUDGET[effort], "includeThoughts": True}}}
    if kind == "deepseek":
        return {"extra_body": {
            "thinking": {"type": "enabled"},
            "reasoning_effort": _OPENAI_EFFORT[effort],
        }}
    # openai-compatible family
    return {"extra_body": {"reasoning_effort": _OPENAI_EFFORT[effort]}}


def is_thinking_config(config) -> bool:
    """True when the config enables extended thinking for a supported model."""
    return _resolve_thinking_kwargs(config) != {}
```

In `BaseModelProvider` (around line 344), add:

```python
    def _thinking_kwargs(self) -> Dict[str, Any]:
        return _resolve_thinking_kwargs(self.config)
```

- [ ] **Step 4: Inject into every create call**

- `OpenAICompatibleProvider.generate` line 485: change `response = await client.chat.completions.create(` to include `**self._thinking_kwargs(),`:

```python
                response = await client.chat.completions.create(
                    model=kwargs.get('model', self.config.default_model),
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_message}
                    ],
                    max_tokens=kwargs.get('max_tokens', self.config.max_tokens),
                    temperature=kwargs.get('temperature', self.config.temperature),
                    top_p=kwargs.get('top_p', self.config.top_p),
                    **self._thinking_kwargs(),
                )
```

- `OpenAICompatibleProvider.stream_generate` line 557: same `**self._thinking_kwargs(),` addition inside the `client.chat.completions.create(...)` call.

- `OpenAICompatibleProvider.generate_with_tools` — after `create_kwargs` is built (line 719-724) and before `client.chat.completions.create(**create_kwargs)` (line 750), insert:

```python
                create_kwargs.update(self._thinking_kwargs())
```

(works for both OpenAI `extra_body` and Anthropic `thinking`/`temperature` keys, since `**create_kwargs` is spread)

- `AnthropicProvider.generate` line 993: add `**self._thinking_kwargs(),` inside `client.messages.create(...)`.

- `AnthropicProvider.stream_generate` (~line 1041) and `AnthropicProvider.generate_with_tools` (~line 1108): same — add `**self._thinking_kwargs(),` to the `client.messages.create(...)` call (and `create_kwargs.update(self._thinking_kwargs())` if it builds a dict first).

- `LocalProvider.generate` line 1324: add `**self._thinking_kwargs(),` inside `client.chat.completions.create(...)`.

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && pytest tests/unit/test_model_provider_thinking.py -v`
Expected: PASS (all 8 tests).

- [ ] **Step 6: Commit**

```bash
git add backend/services/model_provider.py backend/tests/unit/test_model_provider_thinking.py
git commit -m "feat: wire effort to provider extended-thinking params"
```

---

### Task 4: WebSocket `thinking` flag

**Files:**
- Modify: `backend/api/routes/websocket.py:604-627` (inside the `with get_fresh_db() as db:` block, before `send_json` of `message_start`)

**Interfaces:**
- Consumes: `is_thinking_config` (Task 3), `HeadOfCouncil.preferred_config_id`, `UserModelConfig` query.

- [ ] **Step 1: Import the helper**

At the top of `websocket.py`, add:

```python
from services.model_provider import is_thinking_config
from models.entities.user_config import UserModelConfig
```

- [ ] **Step 2: Resolve thinking before sending message_start**

Inside the `with get_fresh_db() as db:` block (after `head = ...` at line 605, before `stream_id = ...` at line 616), add:

```python
                    thinking_enabled = False
                    if head.preferred_config_id:
                        head_cfg = (
                            db.query(UserModelConfig)
                            .filter_by(id=head.preferred_config_id)
                            .first()
                        )
                        if head_cfg and is_thinking_config(head_cfg):
                            thinking_enabled = True
```

- [ ] **Step 3: Stamp the flag**

In the `await websocket.send_json({... "type": "message_start", ...})` dict (line 621), add the field:

```python
                    await websocket.send_json({
                        "type":       "message_start",
                        "stream_id":  stream_id,
                        "role":       "head_of_council",
                        "message_id": message_id,
                        "thinking":   thinking_enabled,
                        "timestamp":  datetime.utcnow().isoformat(),
                    })
```

- [ ] **Step 4: Run the WS route import**

Run: `cd backend && python -c "import api.routes.websocket as w; print('ok')"`
Expected: `ok`

- [ ] **Step 5: Commit**

```bash
git add backend/api/routes/websocket.py
git commit -m "feat: stamp thinking flag on chat message_start"
```

---

### Task 5: Frontend types + service payload

**Files:**
- Modify: `frontend/src/types/index.ts:219` (`ModelConfig`), `:230` (`settings`)
- Modify: `frontend/src/services/models.ts:42` (`createConfig`), `:70` (`updateConfig`)

**Interfaces:**
- Produces: `ModelConfig.effort`, `ModelConfig.settings.effort`, and payload typing for the API calls.

- [ ] **Step 1: Add `effort` to `ModelConfig`**

In `types/index.ts`, inside `interface ModelConfig` (after `provider_name?`, ~line 222) add:

```typescript
    /** Reasoning effort: none | low | medium | high | xhigh */
    effort?: 'none' | 'low' | 'medium' | 'high' | 'xhigh';
```

Inside the `settings` object (after `timeout: number;`, ~line 234) add:

```typescript
        effort?: 'none' | 'low' | 'medium' | 'high' | 'xhigh';
```

- [ ] **Step 2: Add `effort` to service payloads**

In `models.ts` `createConfig` params (line 42) add `effort?: string;` and in `updateConfig` (line 70) add `effort?: string;`.

- [ ] **Step 3: Type-check the frontend**

Run: `cd frontend && npx tsc --noEmit -p tsconfig.json`
Expected: no new errors referencing `effort`.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/types/index.ts frontend/src/services/models.ts
git commit -m "feat: add effort to frontend model config types"
```

---

### Task 6: Model Config form — effort control

**Files:**
- Modify: `frontend/src/components/models/ModelConfigForm.tsx` (formData state ~252, edit effect ~312, Advanced Settings ~998, submit payload ~534, test payload ~460)

**Interfaces:**
- Consumes: `ModelConfig.effort` (Task 5)
- Produces: a `Reasoning Effort` `<select>` shown only for thinking-capable providers; included in create/update/test payloads.

- [ ] **Step 1: Add a `supportsThinking` helper + constant**

Near the top of `ModelConfigForm.tsx` (after the `RateLimitField` import ~line 34), add:

```typescript
type Effort = 'none' | 'low' | 'medium' | 'high' | 'xhigh';

// Mirrors backend PROVIDER_THINKING. Controls whether the effort control is shown.
const THINKING_PROVIDERS: Record<string, RegExp | null> = {
    OPENAI: /(^|[-/])(o1|o3|o4|gpt-5)/i,
    AZURE_OPENAI: /(^|[-/])(o1|o3|o4|gpt-5)/i,
    ANTHROPIC: null,
    GEMINI: null,
    DEEPSEEK: /reasoner|v4/i,
    GROQ: /gpt-oss|qwen|r1|qwq|reason/i,
    MISTRAL: /magistral|thinking/i,
    TOGETHER: /r1|qwq|reasoner|thinking|gpt-oss/i,
    MOONSHOT: /k2|kimi/i,
    LOCAL: /qwq|r1|deepseek|thinking|z1|qwen3/i,
    CUSTOM: /(^|[-/])(o1|o3|o4|gpt-5)|qwq|r1|reasoner|thinking|gpt-oss/i,
    // COHERE: omitted -> hidden
};

export function supportsThinking(provider: string, model: string): boolean {
    const hint = THINKING_PROVIDERS[provider?.toUpperCase()];
    if (!hint) return false;
    if (hint === null) return true;
    return hint.test(model || '');
}
```

- [ ] **Step 2: Add `effort` to formData state**

In the `formData` initial state (line 252) add `effort: 'none' as Effort,`.

In the edit-prep `useEffect` (line 312), inside `setFormData({...})` add `effort: (initialConfig.effort || 'none') as Effort,`.

- [ ] **Step 3: Compute `showEffort` and render the select**

Add inside the component body (after the `apiKeyMissing` block ~line 575):

```typescript
    const showEffort = supportsThinking(formData.provider, formData.default_model);
```

Inside the **Advanced Settings** `div` (after the `temperature` grid cell, ~line 1035), add a second grid cell:

```tsx
                                <div>
                                    <label htmlFor="effort" className="block text-xs font-medium text-gray-600 dark:text-gray-400 mb-1.5">
                                        Reasoning Effort
                                    </label>
                                    <select
                                        id="effort"
                                        name="effort"
                                        value={formData.effort}
                                        onChange={handleChange}
                                        className={inputCls}
                                        disabled={!showEffort}
                                    >
                                        <option value="none">None (disabled)</option>
                                        <option value="low">Low</option>
                                        <option value="medium">Medium</option>
                                        <option value="high">High</option>
                                        <option value="xhigh">X-High</option>
                                    </select>
                                    {!showEffort && (
                                        <p className="text-xs text-gray-600 dark:text-gray-500 mt-1.5">
                                            Not supported by this provider/model.
                                        </p>
                                    )}
                                </div>
```

Note: the select is always rendered but `disabled` (showing "None") when unsupported, which satisfies "present only for models that support it (or a no-op/hidden otherwise)". If you prefer fully hidden, wrap the block in `{showEffort && (...)}` instead — both are acceptable; choose hidden for strict compliance.

- [ ] **Step 4: Include `effort` in payloads**

In `handleTestConnection` `payload` (line 460) add `effort: formData.effort,`.
In `handleSubmit` `base` object (line 534) add `effort: formData.effort,`.

- [ ] **Step 5: Type-check**

Run: `cd frontend && npx tsc --noEmit -p tsconfig.json`
Expected: no new errors.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/models/ModelConfigForm.tsx
git commit -m "feat: add reasoning effort control to model config form"
```

---

### Task 7: Chat "Thinking…" label

**Files:**
- Modify: `frontend/src/components/chat/TypingIndicator.tsx` (add `thinking` prop)
- Modify: `frontend/src/pages/ChatPage.tsx` (state ~160, message_start handler ~306, reset points ~317/327/351, render sites ~1172 & ~1241)

**Interfaces:**
- Consumes: `thinking` flag from `message_start` (Task 4)
- Produces: `TypingIndicator` renders a "Thinking…" label when `thinking` is true.

- [ ] **Step 1: Update TypingIndicator**

Replace the `TypingIndicator` component:

```tsx
import styles from './TypingIndicator.module.css';

export function TypingIndicator({ thinking = false }: { thinking?: boolean }) {
    if (thinking) {
        return (
            <div
                data-testid="typing-indicator"
                aria-live="polite"
                className={styles.thinkingLabel}
            >
                Thinking…
            </div>
        );
    }
    return (
        <div
            data-testid="typing-indicator"
            aria-hidden
            className={styles.shimmer}
        >
            <span className={styles.bar} />
            <span className={styles.bar} />
            <span className={styles.bar} />
        </div>
    );
}
```

Add to `TypingIndicator.module.css`:

```css
.thinkingLabel {
    font-size: 0.875rem;
    color: rgb(107 114 128);
    font-style: italic;
    padding: 0.25rem 0;
}
```

- [ ] **Step 2: Track + wire `isThinking` in ChatPage**

Add state near line 160:

```typescript
    const [isThinking, setIsThinking] = useState(false);
```

In the `message_start` handler (line 306), after `useChatStore.getState().beginStream(...)`, add:

```typescript
                setIsThinking(Boolean((msg as any).thinking));
```

In the `message_delta` handler (line 315), add `setIsThinking(false);` alongside `setIsAwaitingReply(false);`.
In the `message_end` handler (line 320), add `setIsThinking(false);`.
In the legacy `message` handler (line 332 area, where `setIsAwaitingReply(false)` is at line 351), add `setIsThinking(false);`.

At both `<TypingIndicator />` render sites (lines 1172 and 1241), change to:

```tsx
                                                            <TypingIndicator thinking={isThinking} />
```

and

```tsx
                                            <TypingIndicator thinking={isThinking} />
```

- [ ] **Step 3: Type-check**

Run: `cd frontend && npx tsc --noEmit -p tsconfig.json`
Expected: no new errors.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/chat/TypingIndicator.tsx frontend/src/components/chat/TypingIndicator.module.css frontend/src/pages/ChatPage.tsx
git commit -m "feat: show Thinking label during active thinking"
```

---

### Task 8: Frontend test for the label

**Files:**
- Modify: `frontend/src/pages/ChatPage.typing.test.tsx`

**Interfaces:**
- Consumes: `TypingIndicator` `thinking` prop (Task 7).

- [ ] **Step 1: Add a label test**

After the existing tests, add:

```tsx
import { TypingIndicator } from '@/components/chat/TypingIndicator';

it('renders the Thinking label when thinking prop is true', () => {
    const { container, getByText } = render(<TypingIndicator thinking />);
    expect(container.querySelector('[data-testid="typing-indicator"]')).toBeInTheDocument();
    expect(getByText('Thinking…')).toBeInTheDocument();
});

it('still renders the three-dot shimmer when thinking is false', () => {
    const { container } = render(<TypingIndicator thinking={false} />);
    expect(container.querySelector('[data-testid="typing-indicator"]')).toBeInTheDocument();
    expect(container.querySelectorAll('.shimmer .bar').length).toBe(3);
});
```

- [ ] **Step 2: Run the test**

Run: `cd frontend && npx vitest run src/pages/ChatPage.typing.test.tsx`
Expected: PASS (existing + 2 new tests).

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/ChatPage.typing.test.tsx
git commit -m "test: cover Thinking label in TypingIndicator"
```

---

### Task 9: Full test + lint gate

**Files:** (no new files)

- [ ] **Step 1: Backend tests**

Run: `cd backend && pytest tests/unit/test_model_provider_thinking.py -v`
Expected: PASS.

- [ ] **Step 2: Frontend type-check + tests**

Run: `cd frontend && npx tsc --noEmit -p tsconfig.json && npx vitest run`
Expected: no type errors; all tests pass.

- [ ] **Step 3: Lint (if configured)**

Run: `cd backend && ruff check services/model_provider.py api/routes/models.py api/routes/websocket.py 2>/dev/null || echo "ruff not configured — skipped"`
Expected: clean or skipped.

- [ ] **Step 4: Final commit (if any fixes)**

```bash
git add -A && git commit -m "chore: lint/test fixes for effort-thinking feature" || echo "nothing to commit"
```

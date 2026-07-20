# Refresh Model Catalog to Latest — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Update the hardcoded provider model lists (and effort/thinking regexes) so the Models page shows current (July 2026) models, keeping the effort control working on the new generations.

**Architecture:** Static-data change only. The backend `list_providers()` returns per-provider `popular_models` + `description`; the frontend mirrors the thinking-regex map. No new endpoints, no schema changes. Tests assert the exact lists and the thinking regex behavior.

**Tech Stack:** Python / FastAPI (backend), Pydantic; React 18 + TypeScript (frontend); pytest (backend unit), vitest + tsc (frontend).

## Global Constraints

- Existing test `backend/tests/unit/test_provider_seeds.py` asserts the EXACT `popular_models` list per provider — it MUST be updated to match or CI fails.
- `THINKING_PROVIDERS` in `frontend/src/components/models/ModelConfigForm.tsx` is a hand-copied mirror of `PROVIDER_THINKING` in `backend/services/model_provider.py` — the two MUST stay in sync (same keys + matching hints).
- `COHERE` must remain EXCLUDED from `PROVIDER_THINKING` (existing test `test_unsupported_provider_hidden` enforces this).
- Model IDs flagged ⚠️ in the spec (Gemini 3.5, Groq `llama-4-*`) are user-accepted; do not re-litigate.
- TDD: write/adjust the failing test first, then implement, then run green, then commit.

---

## File Structure

- `backend/api/routes/models.py` — `list_providers()`: the source of `popular_models` + `description` shown before fetch. (Modify)
- `backend/tests/unit/test_provider_seeds.py` — asserts exact `popular_models` lists. (Modify — Task 1 gate)
- `backend/services/model_provider.py` — `PROVIDER_THINKING` dict: gates effort/thinking params. (Modify)
- `backend/tests/unit/test_model_provider_thinking.py` — asserts thinking regex behavior. (Modify — Task 2 gate)
- `frontend/src/components/models/ModelConfigForm.tsx` — `THINKING_PROVIDERS`: mirror of `PROVIDER_THINKING`. (Modify)

---

### Task 1: Update provider model lists (backend data + test)

**Files:**
- Modify: `backend/api/routes/models.py:329-440` (the `list_providers()` `providers = [...]` block)
- Modify: `backend/tests/unit/test_provider_seeds.py:6-18` (`EXPECTED` dict)

**Interfaces:**
- Consumes: `GET /api/v1/models/providers` contract (unchanged shape).
- Produces: updated `popular_models` per provider consumed by the frontend provider grid + config-form default.

- [ ] **Step 1: Update the expected lists test to the new models**

In `backend/tests/unit/test_provider_seeds.py`, replace the `EXPECTED` dict (lines 6-18) with:

```python
EXPECTED = {
    "openai": ["gpt-5.6", "gpt-5.6-terra", "gpt-5.6-luna"],
    "anthropic": ["claude-opus-4-8", "claude-sonnet-5", "claude-fable-5", "claude-haiku-4-5"],
    "gemini": ["gemini-3.5-pro", "gemini-3.5-flash", "gemini-3.5-flash-lite"],
    "groq": ["llama-4-scout-17b-16e-instruct", "llama-4-maverick-17b-128e-instruct", "deepseek-r1-distill-llama-70b"],
    "mistral": ["mistral-medium-latest", "mistral-small-latest", "codestral-latest"],
    "together": ["Qwen/Qwen3.7-Max", "deepseek-ai/DeepSeek-V4-Pro", "meta-llama/Llama-3.3-70B-Instruct-Turbo"],
    "cohere": ["command-a-plus-05-2026", "command-a-03-2025", "command-a-reasoning-08-2025"],
    "moonshot": ["kimi-k2", "moonshot-v1-32k", "moonshot-v1-128k"],
    "deepseek": ["deepseek-chat", "deepseek-reasoner"],
    "azure_openai": ["gpt-5.6", "gpt-5.6-terra", "gpt-5.6-luna"],
    "local": ["llama3.3", "qwen2.5", "gemma2", "mistral"],
}
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd "E:\Ongoing Projects\Agentium" && pytest backend/tests/unit/test_provider_seeds.py -v`
Expected: FAIL — assertion error on `openai`/`anthropic`/etc. (lists differ).

- [ ] **Step 3: Update `list_providers()` `popular_models` and `description`**

In `backend/api/routes/models.py`, replace the `providers = [...]` list (lines 329-440) with:

```python
    providers = [
        ProviderInfo(
            id=ProviderType.OPENAI.value,
            name="openai",
            display_name="OpenAI",
            requires_api_key=True,
            requires_base_url=False,
            default_base_url="https://api.openai.com/v1",
            description="GPT-5.6 Sol, Terra, and Luna frontier models",
            popular_models=["gpt-5.6", "gpt-5.6-terra", "gpt-5.6-luna"]
        ),
        ProviderInfo(
            id=ProviderType.ANTHROPIC.value,
            name="anthropic",
            display_name="Anthropic Claude",
            requires_api_key=True,
            requires_base_url=False,
            default_base_url="https://api.anthropic.com/v1",
            description="Claude Opus 4.8, Sonnet 5, Fable 5, Haiku 4.5 - excellent reasoning and coding",
            popular_models=["claude-opus-4-8", "claude-sonnet-5", "claude-fable-5", "claude-haiku-4-5"]
        ),
        ProviderInfo(
            id=ProviderType.GEMINI.value,
            name="gemini",
            display_name="Google Gemini",
            requires_api_key=True,
            requires_base_url=False,
            default_base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
            description="Google's multimodal models (Gemini 3.5 Pro, 3.5 Flash)",
            popular_models=["gemini-3.5-pro", "gemini-3.5-flash", "gemini-3.5-flash-lite"]
        ),
        ProviderInfo(
            id=ProviderType.GROQ.value,
            name="groq",
            display_name="Groq",
            requires_api_key=True,
            requires_base_url=False,
            default_base_url="https://api.groq.com/openai/v1",
            description="Ultra-fast inference with Llama 4 and DeepSeek R1",
            popular_models=["llama-4-scout-17b-16e-instruct", "llama-4-maverick-17b-128e-instruct", "deepseek-r1-distill-llama-70b"]
        ),
        ProviderInfo(
            id=ProviderType.MISTRAL.value,
            name="mistral",
            display_name="Mistral AI",
            requires_api_key=True,
            requires_base_url=False,
            default_base_url="https://api.mistral.ai/v1",
            description="European AI with Mistral Medium 3.5, Small 4, and Codestral",
            popular_models=["mistral-medium-latest", "mistral-small-latest", "codestral-latest"]
        ),
        ProviderInfo(
            id=ProviderType.TOGETHER.value,
            name="together",
            display_name="Together AI",
            requires_api_key=True,
            requires_base_url=False,
            default_base_url="https://api.together.xyz/v1",
            description="100+ open-source models (Qwen3.7, DeepSeek V4, Llama 3.3)",
            popular_models=["Qwen/Qwen3.7-Max", "deepseek-ai/DeepSeek-V4-Pro", "meta-llama/Llama-3.3-70B-Instruct-Turbo"]
        ),
        ProviderInfo(
            id=ProviderType.COHERE.value,
            name="cohere",
            display_name="Cohere",
            requires_api_key=True,
            requires_base_url=False,
            default_base_url="https://api.cohere.ai/v1",
            description="Command A+, A, and A Reasoning models",
            popular_models=["command-a-plus-05-2026", "command-a-03-2025", "command-a-reasoning-08-2025"]
        ),
        ProviderInfo(
            id=ProviderType.MOONSHOT.value,
            name="moonshot",
            display_name="Moonshot (Kimi)",
            requires_api_key=True,
            requires_base_url=False,
            default_base_url="https://api.moonshot.cn/v1",
            description="Kimi - Long context (200K+ tokens), Chinese/English",
            popular_models=["kimi-k2", "moonshot-v1-32k", "moonshot-v1-128k"]
        ),
        ProviderInfo(
            id=ProviderType.DEEPSEEK.value,
            name="deepseek",
            display_name="DeepSeek",
            requires_api_key=True,
            requires_base_url=False,
            default_base_url="https://api.deepseek.com/v1",
            description="DeepSeek Chat and Reasoner models",
            popular_models=["deepseek-chat", "deepseek-reasoner"]
        ),
        ProviderInfo(
            id=ProviderType.AZURE_OPENAI.value,
            name="azure_openai",
            display_name="Azure OpenAI",
            requires_api_key=True,
            requires_base_url=True,
            default_base_url="https://{resource}.openai.azure.com",
            description="Enterprise OpenAI through Azure (requires Endpoint URL)",
            popular_models=["gpt-5.6", "gpt-5.6-terra", "gpt-5.6-luna"]
        ),
        ProviderInfo(
            id=ProviderType.LOCAL.value,
            name="local",
            display_name="Local (Ollama/LM Studio)",
            requires_api_key=False,
            requires_base_url=False,
            default_base_url=settings.OLLAMA_BASE_URL,
            description="Run models locally with Ollama or LM Studio",
            popular_models=["llama3.3", "qwen2.5", "gemma2", "mistral"]
        ),
    ]
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd "E:\Ongoing Projects\Agentium" && pytest backend/tests/unit/test_provider_seeds.py -v`
Expected: PASS (all provider assertions).

- [ ] **Step 5: Commit**

```bash
cd "E:\Ongoing Projects\Agentium" && git add backend/api/routes/models.py backend/tests/unit/test_provider_seeds.py && git commit -m "feat(models): refresh provider popular_models to July 2026 lineups"
```

---

### Task 2: Update thinking/effort regex (backend) + tests

**Files:**
- Modify: `backend/services/model_provider.py:487-501` (`PROVIDER_THINKING`)
- Modify: `backend/tests/unit/test_model_provider_thinking.py` (add new-ID cases)

**Interfaces:**
- Consumes: `default_model` string + `effort` from a config.
- Produces: `_resolve_thinking_kwargs(config)` returns provider-specific thinking kwargs for the new generations; `test_unsupported_provider_hidden` still requires `COHERE` absent.

- [ ] **Step 1: Add failing tests for the new model generations**

Append to `backend/tests/unit/test_model_provider_thinking.py`:

```python
def test_anthropic_new_generation_fable5():
    kw = _resolve_thinking_kwargs(_Cfg("ANTHROPIC", "claude-fable-5", "high"))
    assert kw["thinking"] == {"type": "enabled", "budget_tokens": 16000}
    assert kw["temperature"] == 1


def test_anthropic_new_generation_opus48():
    kw = _resolve_thinking_kwargs(_Cfg("ANTHROPIC", "claude-opus-4-8", "high"))
    assert kw["thinking"] == {"type": "enabled", "budget_tokens": 16000}
    assert kw["temperature"] == 1


def test_anthropic_new_generation_sonnet5():
    kw = _resolve_thinking_kwargs(_Cfg("ANTHROPIC", "claude-sonnet-5", "high"))
    assert kw["thinking"] == {"type": "enabled", "budget_tokens": 16000}
    assert kw["temperature"] == 1


def test_gemini_new_generation_35():
    kw = _resolve_thinking_kwargs(_Cfg("GEMINI", "gemini-3.5-pro", "low"))
    assert kw["extra_body"]["thinkingConfig"]["thinkingBudget"] == 1024
    assert kw["extra_body"]["thinkingConfig"]["includeThoughts"] is True
```

- [ ] **Step 2: Run the new tests to verify they fail**

Run: `cd "E:\Ongoing Projects\Agentium" && pytest backend/tests/unit/test_model_provider_thinking.py -v -k "new_generation"`
Expected: FAIL — `claude-fable-5` / `claude-opus-4-8` / `claude-sonnet-5` / `gemini-3.5-pro` do not match the old regex → `{}` returned.

- [ ] **Step 3: Update `PROVIDER_THINKING` hints**

In `backend/services/model_provider.py`, update the `ANTHROPIC` and `GEMINI` entries (keep all other entries identical, keep `COHERE` omitted):

```python
    "ANTHROPIC":     {"kind": "anthropic", "model_hint": r"claude-(fable|opus|sonnet|haiku)[- ]?(4|4[-.]5|4-8|5)"},
    "GEMINI":        {"kind": "gemini",    "model_hint": r"gemini-(2\.5|3|3\.5)"},
```

- [ ] **Step 4: Run the full thinking test suite**

Run: `cd "E:\Ongoing Projects\Agentium" && pytest backend/tests/unit/test_model_provider_thinking.py -v`
Expected: PASS — new cases pass AND existing cases (`test_anthropic_thinking_model_still_gated`, `test_gemini_thinking_model_still_gated`, `test_unsupported_provider_hidden`, etc.) still pass.

- [ ] **Step 5: Commit**

```bash
cd "E:\Ongoing Projects\Agentium" && git add backend/services/model_provider.py backend/tests/unit/test_model_provider_thinking.py && git commit -m "feat(models): extend thinking regex to Claude Fable/Opus4.8/Sonnet5 and Gemini 3.5"
```

---

### Task 3: Mirror thinking regex in frontend

**Files:**
- Modify: `frontend/src/components/models/ModelConfigForm.tsx:43-56` (`THINKING_PROVIDERS`)

**Interfaces:**
- Consumes: `supportsThinking(provider, model)` used by the config form to decide whether to render the effort control.
- Produces: identical matching behavior to backend `PROVIDER_THINKING` for `ANTHROPIC` and `GEMINI`.

- [ ] **Step 1: Update `THINKING_PROVIDERS` regexes**

In `frontend/src/components/models/ModelConfigForm.tsx`, replace the `ANTHROPIC` and `GEMINI` entries (all other entries unchanged):

```ts
    ANTHROPIC: /claude-(fable|opus|sonnet|haiku)[- ]?(4|4[-.]5|4-8|5)/i,
    GEMINI: /gemini-(2\.5|3|3\.5)/i,
```

- [ ] **Step 2: Typecheck the frontend**

Run: `cd "E:\Ongoing Projects\Agentium\frontend" && npx tsc --noEmit`
Expected: no type errors (exit 0).

- [ ] **Step 3: Commit**

```bash
cd "E:\Ongoing Projects\Agentium" && git add frontend/src/components/models/ModelConfigForm.tsx && git commit -m "feat(models): mirror thinking regex updates in frontend (Claude/Gemini new gens)"
```

---

### Task 4: Full verification

**Files:** none (verification only)

- [ ] **Step 1: Backend unit tests green**

Run: `cd "E:\Ongoing Projects\Agentium" && pytest backend/tests/unit/test_provider_seeds.py backend/tests/unit/test_model_provider_thinking.py -v`
Expected: all PASS.

- [ ] **Step 2: Frontend typecheck + unit tests green**

Run: `cd "E:\Ongoing Projects\Agentium\frontend" && npx tsc --noEmit && npm run test`
Expected: typecheck clean; vitest unit suite PASS.

- [ ] **Step 3: Manual smoke (optional but recommended)**

Start the stack (`make up`), open **Models → Add Provider → Anthropic**: confirm the grid chips show `claude-opus-4-8`, `claude-sonnet-5`, `claude-fable-5`, `claude-haiku-4-5` and the auto-selected default is `claude-opus-4-8`. Select a model, set **Effort** to a non-none value, confirm the effort control remains visible (not silently hidden). Repeat mentally for Gemini 3.5.

- [ ] **Step 4: Commit any follow-ups (only if manual fixes were needed)**

```bash
cd "E:\Ongoing Projects\Agentium" && git add -A && git commit -m "fix(models): address manual smoke-test findings for refreshed catalog"
```
(If no follow-ups, skip this step.)

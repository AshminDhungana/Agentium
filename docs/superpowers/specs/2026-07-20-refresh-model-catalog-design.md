# Refresh Model Catalog to Latest (Models Page)

**Date:** 2026-07-20
**Status:** Approved design, pending implementation plan
**Scope:** Update the hardcoded provider model lists shown in the Models page / model config form to current (July 2026) model IDs, and keep the effort/thinking controls working for the new generations.

## Context

The Models page (`frontend/src/pages/ModelsPage.tsx`) and the model config form
(`frontend/src/components/models/ModelConfigForm.tsx`) show a provider list fetched from
`GET /api/v1/models/providers` (backend `api/routes/models.py` → `list_providers()`). Each
`ProviderInfo` carries:

- `popular_models`: the suggestion list shown **before** the user fetches live models from the
  provider. `popular_models[0]` is auto-selected as the **default model** in the config form.
- `description`: short human-readable blurb.

The current lists are outdated (e.g. Anthropic shows `claude-opus-4-5`/`claude-sonnet-4-5`,
OpenAI shows `gpt-5.6-mini` which does not exist, Gemini shows `gemini-2.5`). The user asked to
refresh all providers to their latest models via web research.

A related, easily-missed bug: the **effort/thinking** controls are gated by regexes
(`PROVIDER_THINKING` in `backend/services/model_provider.py` and its hand-copied mirror
`THINKING_PROVIDERS` in `ModelConfigForm.tsx`). These only matched older generations
(`claude-opus-4-5`, `gemini-2.5`). If we only swap model names, the effort control would silently
disappear for the new generations (Opus 4.8, Sonnet 5, Fable 5, Gemini 3.5). The design updates
both.

## Target Changes

### 1. `backend/api/routes/models.py` — `list_providers()`

Update each `ProviderInfo`'s `popular_models` (and `description`) to:

| Provider | `popular_models` (newest first; `[0]` = default) | `description` |
|---|---|---|
| OpenAI | `gpt-5.6`, `gpt-5.6-terra`, `gpt-5.6-luna` | GPT-5.6 Sol/Terra/Luna frontier models |
| Azure OpenAI | `gpt-5.6`, `gpt-5.6-terra`, `gpt-5.6-luna` | Enterprise OpenAI through Azure |
| Anthropic | `claude-opus-4-8`, `claude-sonnet-5`, `claude-fable-5`, `claude-haiku-4-5` | Claude Opus 4.8, Sonnet 5, Fable 5, Haiku 4.5 |
| Gemini ⚠️ | `gemini-3.5-pro`, `gemini-3.5-flash`, `gemini-3.5-flash-lite` | Google Gemini 3.5 Pro/Flash multimodal |
| Groq ⚠️ | `llama-4-scout-17b-16e-instruct`, `llama-4-maverick-17b-128e-instruct`, `deepseek-r1-distill-llama-70b` | Ultra-fast Llama 4 + DeepSeek R1 |
| Mistral | `mistral-medium-latest`, `mistral-small-latest`, `codestral-latest` | Mistral Medium 3.5, Small 4, Codestral |
| Together | `Qwen/Qwen3.7-Max`, `deepseek-ai/DeepSeek-V4-Pro`, `meta-llama/Llama-3.3-70B-Instruct-Turbo` | 100+ open models (Qwen3.7, DeepSeek V4, Llama 3.3) |
| Cohere | `command-a-plus-05-2026`, `command-a-03-2025`, `command-a-reasoning-08-2025` | Command A+ / A / A Reasoning |
| Moonshot | `kimi-k2`, `moonshot-v1-32k`, `moonshot-v1-128k` | Kimi long-context chat |
| DeepSeek | `deepseek-chat`, `deepseek-reasoner` | DeepSeek Chat and Reasoner |
| Local | `llama3.3`, `qwen2.5`, `gemma2`, `mistral` | Ollama / LM Studio local models |

Verification legend: ✅ confirmed against official provider docs (July 2026);
⚠️ Gemini 3.5 per user-stated "Gemini 3.5 is latest" (Gemini docs timed out); Groq IDs are
known-stable model strings (Groq docs model table unavailable).

### 2. `backend/services/model_provider.py` — `PROVIDER_THINKING`

Update the model-hint regexes so effort/thinking stays enabled for new generations:

```python
"ANTHROPIC":     {"kind": "anthropic", "model_hint": r"claude-(fable|opus|sonnet|haiku)[- ]?(4|4[-.]5|4-8|5)"},
"GEMINI":        {"kind": "gemini",    "model_hint": r"gemini-(2\.5|3|3\.5)"},
```

`OPENAI` / `AZURE_OPENAI` already use `r"(^|[-/])(o1|o3|o4|gpt-5)"` which matches `gpt-5.6` —
no change needed. Other providers (DEEPSEEK, GROQ, MISTRAL, TOGETHER, MOONSHOT, LOCAL, CUSTOM)
are unchanged.

### 3. `frontend/src/components/models/ModelConfigForm.tsx` — `THINKING_PROVIDERS`

Hand-copied mirror of `PROVIDER_THINKING`. Apply identical updates so the UI shows the effort
control for the new generations:

```ts
ANTHROPIC: /claude-(fable|opus|sonnet|haiku)[- ]?(4|4[-.]5|4-8|5)/i,
GEMINI: /gemini-(2\.5|3|3\.5)/i,
```

`OPENAI` / `AZURE_OPENAI` unchanged (`/(^|[-/])(o1|o3|o4|gpt-5)/i` already covers `gpt-5.6`).

### 4. `backend/tests/unit/test_provider_seeds.py`

This test asserts the exact `popular_models` list per provider name. Update the expected
dictionaries to match the new lists above.

## Data Flow (unchanged)

1. Frontend calls `modelsApi.getProviders()` → backend `list_providers()`.
2. Provider grid shows `popular_models` chips; selecting a provider pre-fills
   `default_model = popular_models[0]` and `available_models = popular_models`.
3. User may click **Fetch Models** to replace `available_models` with the live provider list
   (this design does NOT change that path).
4. When a config enables `effort != none`, `_resolve_thinking_kwargs` uses `PROVIDER_THINKING`
   to decide whether to emit thinking params for the chosen model — now including the new gens.

## Error Handling

- No new network calls; this is static data. The existing error boundaries and validation remain.
- If a listed `popular_model` ID is later retired by a provider, the live **Fetch Models** path
  still gives the user correct current IDs — the static list is only a pre-fetch convenience.

## Testing

- Update `backend/tests/unit/test_provider_seeds.py` expected lists (must pass).
- `backend/tests/unit/test_model_provider_thinking.py` must continue to pass:
  - `COHERE` still excluded from `PROVIDER_THINKING`.
  - New IDs `claude-opus-4-8`, `claude-sonnet-5`, `claude-fable-5`, `gemini-3.5-pro` now match
    and enable thinking; unrelated models still excluded.
- Manual: open Models page → Add Provider → Anthropic shows Opus 4.8/Sonnet 5/Fable 5/Haiku 4.5;
  selecting one and setting effort shows the effort control (no silent disappearance).

## Out of Scope

- Genesis / Head-of-Council default model assignment logic.
- Live `/models` fetch implementation and pricing map (`PricingMap`).
- Adding new provider types.

## Files Touched

- `backend/api/routes/models.py` (data)
- `backend/services/model_provider.py` (thinking regex)
- `frontend/src/components/models/ModelConfigForm.tsx` (thinking regex mirror)
- `backend/tests/unit/test_provider_seeds.py` (test expectations)

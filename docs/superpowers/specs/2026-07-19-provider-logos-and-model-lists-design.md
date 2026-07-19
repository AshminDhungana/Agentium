# Provider Logos & Refreshed Model Lists — Design

**Date:** 2026-07-19
**Status:** Approved (pending implementation plan)

## Goal

1. Show official brand logos for each AI provider on the Models page (and the
   model config form), keeping the current Lucide glyph as a fallback.
2. Refresh the stale hardcoded `popular_models` seed list in the backend so the
   suggestion chips / default model reflect current flagship models instead of
   outdated ones (e.g. `gpt-4o`, `gpt-4-turbo`).

## Context

- `frontend/src/constants/providerMeta.tsx` is the single source of truth for
  provider visual identity. It currently renders Lucide glyphs (Sparkles,
  Shield, Atom, …) inside colored gradient pills — no brand logos.
- `ModelCard.tsx:168` (Models page provider badge) and `ModelConfigForm.tsx:663`
  (provider picker) + `:741` (configure header) consume that icon.
- `backend/api/routes/models.py` `list_providers()` hardcodes `popular_models`
  per provider. These seed the suggestion chips and the default model in
  `ModelConfigForm`. The full/correct list still comes from "Fetch" after an API
  key is set — the seed is only a suggestion, but it is currently outdated.

## Part A — Official Provider Logos

### Asset sourcing
Bundle official brand SVG files locally (offline-safe, version-controlled, no
external dependency — important because the app runs in Docker):

- New directory `frontend/src/assets/providers/`.
- One SVG per picker provider: `openai.svg`, `anthropic.svg`, `gemini.svg`,
  `groq.svg`, `mistral.svg`, `together.svg`, `cohere.svg`, `moonshot.svg`,
  `deepseek.svg`, `azureopenai.svg`, `local.svg`, `custom.svg`.

### New component
- New `frontend/src/components/models/ProviderLogo.tsx`.
- Build a lookup map via Vite `import.meta.glob('@/assets/providers/*.svg', { eager: true })`,
  keyed by normalized provider id (reuse `normaliseProviderId` from `providerMeta.tsx`).
- Render `<img src={logo} className="w-5 h-5" />` on a neutral surface
  (`bg-white dark:bg-slate-800` rounded) when a brand SVG exists.
- **Fallback:** when no brand SVG exists (or lookup misses), render the existing
  Lucide icon (`ProviderFormIcon` / `meta.cardIcon`) on the existing gradient
  pill (`getProviderFormGradient`). The current icon is preserved exactly as the
  fallback.

### Wiring
- `ModelCard.tsx:168` provider badge → `<ProviderLogo provider={config.provider} />`.
- `ModelConfigForm.tsx:663` picker card icon → `<ProviderLogo providerId={provider.id} />`.
- `ModelConfigForm.tsx:741` configure header icon → `<ProviderLogo providerId={selectedProvider?.id || 'custom'} />`.
- Keep `getProviderFormGradient` for the hover-glow / accent bar so brand colors
  show on a neutral surface while the gradient remains the subtle accent.

## Part B — Refreshed Model Seeds (backend)

Update `popular_models` (and the `description` strings) in
`backend/api/routes/models.py` `list_providers()`:

| Provider | `popular_models` |
|---|---|
| OpenAI | `gpt-5.6`, `gpt-5.6-mini`, `gpt-5.1`, `o4-mini` |
| Anthropic | `claude-opus-4-5`, `claude-sonnet-4-5`, `claude-haiku-4-5` |
| Gemini | `gemini-2.5-flash`, `gemini-2.5-pro`, `gemini-2.0-flash` |
| Groq | `llama-3.3-70b-versatile`, `llama-3.1-8b-instant`, `deepseek-r1-distill-llama-70b` |
| Mistral | `mistral-large-latest`, `mistral-small-latest`, `codestral-latest` |
| Together | `meta-llama/Llama-3.3-70B-Instruct-Turbo`, `Qwen/Qwen2.5-72B-Instruct-Turbo`, `deepseek-ai/DeepSeek-R1` |
| Cohere | `command-r-plus`, `command-r` |
| Moonshot | `kimi-k2`, `moonshot-v1-32k`, `moonshot-v1-128k` |
| DeepSeek | `deepseek-chat`, `deepseek-reasoner` |
| Azure OpenAI | `gpt-5.6`, `gpt-5.1`, `gpt-4o` |
| Local | `llama3.1`, `mistral`, `gemma2`, `qwen2` |

The model names above are suggestions and can be corrected; the authoritative
list is always the one returned by "Fetch" after an API key is configured.

## Files Touched

- **Added:** `frontend/src/assets/providers/*.svg` (12 files)
- **Added:** `frontend/src/components/models/ProviderLogo.tsx`
- **Edited:** `frontend/src/components/models/ModelCard.tsx` (line 168)
- **Edited:** `frontend/src/components/models/ModelConfigForm.tsx` (lines 663, 741)
- **Edited:** `backend/api/routes/models.py` (`list_providers()` seeds + descriptions)

## Testing

- `npx tsc --noEmit` (frontend typecheck) passes.
- Frontend lint passes.
- Existing `ModelCard.a11y.browser.test.tsx` still passes.
- Relevant backend tests for `list_providers()` pass (models route unit/integration).
- Manual: Models page shows brand logos; config form picker + configure header
  show brand logos; an unknown provider still falls back to the Lucide glyph.

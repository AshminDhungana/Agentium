# Provider Logos & Refreshed Model Lists — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Show official brand logos for each AI provider on the Models page and model config form (current Lucide glyph kept as fallback), and refresh the stale hardcoded `popular_models` seed in the backend to current flagship models.

**Architecture:** Bundle official monochrome brand SVGs locally under `frontend/src/assets/providers/`, load them via Vite `import.meta.glob`, and render through a new `ProviderLogo` component that falls back to the existing Lucide `ProviderFormIcon` when no SVG exists. Update the backend `list_providers()` seed lists. Brand SVGs use `currentColor` (black by default) rendered as `<img>` with `dark:invert` so they read correctly on both light and dark gradient pills.

**Tech Stack:** React 18 + TypeScript + Vite (frontend), FastAPI / Pydantic (backend), simple-icons brand SVGs, Vitest + Testing Library, `pytest`.

## Global Constraints

- Brand SVGs MUST be bundled locally (offline-safe, Docker-deployed app) — no runtime CDN.
- The existing Lucide glyph is the fallback for any provider without a bundled SVG.
- `popular_models` are only a suggestion seed; the authoritative list still comes from "Fetch" after an API key is set.
- Keep the existing colored gradient pill containers in `ModelCard.tsx` and `ModelConfigForm.tsx`; only swap the glyph for the brand logo.
- Provider IDs are normalized via `normaliseProviderId` (lowercase, alphanumeric only) — e.g. `azure_openai` → `azureopenai`, `local` → `local`.

---

### Task 1: Add provider brand-logo SVG assets

**Files:**
- Create: `frontend/src/assets/providers/openai.svg`
- Create: `frontend/src/assets/providers/anthropic.svg`
- Create: `frontend/src/assets/providers/gemini.svg`
- Create: `frontend/src/assets/providers/groq.svg`
- Create: `frontend/src/assets/providers/mistral.svg`
- Create: `frontend/src/assets/providers/together.svg`
- Create: `frontend/src/assets/providers/cohere.svg`
- Create: `frontend/src/assets/providers/moonshot.svg`
- Create: `frontend/src/assets/providers/deepseek.svg`
- Create: `frontend/src/assets/providers/azureopenai.svg`
- Create: `frontend/src/assets/providers/local.svg`

**Interfaces:**
- Each file is a single monochrome SVG (simple-icons style, `fill="currentColor"`). File name = normalized provider id. `custom` is intentionally omitted (falls back to the Lucide glyph).

- [ ] **Step 1: Fetch official brand SVGs from simple-icons and save them locally**

Run (from `frontend/`):

```bash
mkdir -p src/assets/providers
curl -fsSL https://raw.githubusercontent.com/simple-icons/simple-icons/develop/icons/openai.svg      -o src/assets/providers/openai.svg
curl -fsSL https://raw.githubusercontent.com/simple-icons/simple-icons/develop/icons/anthropic.svg   -o src/assets/providers/anthropic.svg
curl -fsSL https://raw.githubusercontent.com/simple-icons/simple-icons/develop/icons/googlegemini.svg -o src/assets/providers/gemini.svg
curl -fsSL https://raw.githubusercontent.com/simple-icons/simple-icons/develop/icons/groq.svg         -o src/assets/providers/groq.svg
curl -fsSL https://raw.githubusercontent.com/simple-icons/simple-icons/develop/icons/mistralai.svg    -o src/assets/providers/mistral.svg
curl -fsSL https://raw.githubusercontent.com/simple-icons/simple-icons/develop/icons/together.svg     -o src/assets/providers/together.svg
curl -fsSL https://raw.githubusercontent.com/simple-icons/simple-icons/develop/icons/cohere.svg       -o src/assets/providers/cohere.svg
curl -fsSL https://raw.githubusercontent.com/simple-icons/simple-icons/develop/icons/moonshot.svg     -o src/assets/providers/moonshot.svg
curl -fsSL https://raw.githubusercontent.com/simple-icons/simple-icons/develop/icons/deepseek.svg     -o src/assets/providers/deepseek.svg
curl -fsSL https://raw.githubusercontent.com/simple-icons/simple-icons/develop/icons/microsoftazure.svg -o src/assets/providers/azureopenai.svg
curl -fsSL https://raw.githubusercontent.com/simple-icons/simple-icons/develop/icons/ollama.svg       -o src/assets/providers/local.svg
```

- [ ] **Step 2: Verify all 11 files downloaded and contain SVG**

Run:
```bash
wc -l src/assets/providers/*.svg
head -c 120 src/assets/providers/openai.svg; echo
```
Expected: 11 files, each starting with `<svg` and containing a `<path`. If any slug 404s (e.g. `mistralai`/`googlegemini`), check the correct simple-icons slug at https://simple-icons.github.io/simple-icons/ and re-run that one `curl`.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/assets/providers/
git commit -m "feat: add official provider brand-logo SVGs"
```

---

### Task 2: Create the `ProviderLogo` component

**Files:**
- Create: `frontend/src/components/models/ProviderLogo.tsx`
- Create: `frontend/src/components/models/ProviderLogo.test.tsx`

**Interfaces:**
- Consumes: `normaliseProviderId`, `getProviderFormGradient`, `ProviderFormIcon` from `@/constants/providerMeta`.
- Produces: `ProviderLogo` — `React.FC<{ provider: string; className?: string }>`. Returns an `<img>` of the brand SVG when a matching file exists, otherwise the Lucide `ProviderFormIcon` (white, for use on gradient pills). Renders no outer container (callers supply the pill).

- [ ] **Step 1: Write the failing test**

`frontend/src/components/models/ProviderLogo.test.tsx`:
```tsx
import React from 'react';
import { render, screen } from '@testing-library/react';
import { ProviderLogo } from './ProviderLogo';

describe('ProviderLogo', () => {
  it('renders a brand <img> for a known provider', () => {
    const { container } = render(<ProviderLogo provider="openai" />);
    const img = container.querySelector('img');
    expect(img).not.toBeNull();
    expect(img?.getAttribute('alt')).toBe('');
  });

  it('falls back to the Lucide icon (no <img>) for an unknown provider', () => {
    const { container } = render(<ProviderLogo provider="some-unknown-provider" />);
    expect(container.querySelector('img')).toBeNull();
    // The fallback uses svg.lucide (no <img> tag)
    expect(container.querySelector('svg')).not.toBeNull();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/components/models/ProviderLogo.test.tsx`
Expected: FAIL (module `./ProviderLogo` does not exist).

- [ ] **Step 3: Write the implementation**

`frontend/src/components/models/ProviderLogo.tsx`:
```tsx
/**
 * Renders the official brand logo for a provider when one is bundled locally,
 * otherwise falls back to the existing Lucide glyph (ProviderFormIcon).
 *
 * Brand SVGs live in frontend/src/assets/providers/<normalisedId>.svg and are
 * loaded eagerly via Vite's import.meta.glob. They are monochrome (currentColor)
 * so we render them as <img> with `dark:invert` to read correctly on both the
 * light and dark gradient pills.
 */
import React from 'react';
import { normaliseProviderId, getProviderFormGradient, ProviderFormIcon } from '@/constants/providerMeta';

// eager glob → Record<path, { default: string }>  (string = resolved URL)
const logoModules = import.meta.glob('@/assets/providers/*.svg', {
  eager: true,
}) as Record<string, { default: string }>;

const LOGO_MAP: Record<string, string> = Object.fromEntries(
  Object.entries(logoModules).map(([path, mod]) => {
    const file = path.split('/').pop()!.replace(/\.svg$/, '');
    return [file, mod.default];
  }),
);

export const ProviderLogo: React.FC<{ provider: string; className?: string }> = ({
  provider,
  className = 'w-5 h-5',
}) => {
  const id = normaliseProviderId(provider);
  const src = LOGO_MAP[id];
  if (src) {
    // Brand mark is monochrome; invert in dark mode so it stays visible.
    return <img src={src} alt="" aria-hidden="true" className={`${className} dark:invert`} />;
  }
  // Fallback: the existing Lucide glyph (white, for coloured gradient pills).
  return <ProviderFormIcon providerId={provider} className={className} />;
};

export default ProviderLogo;
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npx vitest run src/components/models/ProviderLogo.test.tsx`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/models/ProviderLogo.tsx frontend/src/components/models/ProviderLogo.test.tsx
git commit -m "feat: add ProviderLogo with brand-logo + Lucide fallback"
```

---

### Task 3: Wire `ProviderLogo` into the Models page card

**Files:**
- Modify: `frontend/src/components/models/ModelCard.tsx:19` (import) and `:167-172` (badge)

**Interfaces:**
- Consumes: `ProviderLogo` from `@/components/models/ProviderLogo`.

- [ ] **Step 1: Add the import**

In `ModelCard.tsx`, change the line:
```tsx
import { ModelCardSkeleton } from '@/components/models/ModelCardSkeleton';
```
to also import:
```tsx
import { ModelCardSkeleton } from '@/components/models/ModelCardSkeleton';
import { ProviderLogo } from '@/components/models/ProviderLogo';
```

- [ ] **Step 2: Swap the badge glyph for `ProviderLogo`**

Replace lines 167-172:
```tsx
                    <div className={`flex items-center gap-2 px-3 py-1.5 rounded-lg ${meta.bg} border ${meta.border} border-transparent`}>
                        <span className={meta.color} aria-hidden="true">{meta.cardIcon}</span>
                        <span className={`text-sm font-semibold ${meta.color}`}>
                            {config.provider_name || meta.label}
                        </span>
                    </div>
```
with:
```tsx
                    <div className={`flex items-center gap-2 px-3 py-1.5 rounded-lg ${meta.bg} border ${meta.border} border-transparent`}>
                        <ProviderLogo provider={config.provider} />
                        <span className={`text-sm font-semibold ${meta.color}`}>
                            {config.provider_name || meta.label}
                        </span>
                    </div>
```

- [ ] **Step 3: Typecheck**

Run: `cd frontend && npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/models/ModelCard.tsx
git commit -m "feat: show brand logo on model cards"
```

---

### Task 4: Wire `ProviderLogo` into the model config form

**Files:**
- Modify: `frontend/src/components/models/ModelConfigForm.tsx:30` (import), `:659-664` (picker card icon), `:736-743` (configure header icon)

**Interfaces:**
- Consumes: `ProviderLogo` from `@/components/models/ProviderLogo`.

- [ ] **Step 1: Add the import**

In `ModelConfigForm.tsx`, change:
```tsx
import { getProviderFormGradient, ProviderFormIcon } from '@/constants/providerMeta';
```
to:
```tsx
import { getProviderFormGradient, ProviderFormIcon } from '@/constants/providerMeta';
import { ProviderLogo } from '@/components/models/ProviderLogo';
```

- [ ] **Step 2: Replace the picker-card icon (lines 659-664)**

Replace:
```tsx
                                            {/* Provider icon */}
                                            <div
                                                className={`w-11 h-11 rounded-lg bg-gradient-to-br ${getProviderFormGradient(provider.id)} flex items-center justify-center mb-4 shadow-lg`}
                                                aria-hidden="true"
                                            >
                                                <ProviderFormIcon providerId={provider.id} />
                                            </div>
```
with:
```tsx
                                            {/* Provider icon */}
                                            <div
                                                className={`w-11 h-11 rounded-lg bg-gradient-to-br ${getProviderFormGradient(provider.id)} flex items-center justify-center mb-4 shadow-lg`}
                                                aria-hidden="true"
                                            >
                                                <ProviderLogo provider={provider.id} className="w-6 h-6" />
                                            </div>
```

- [ ] **Step 3: Replace the configure-header icon (lines 736-743)**

Replace:
```tsx
                    {(selectedProvider || isUniversal) && (
                        <div
                            className={`w-12 h-12 rounded-xl bg-gradient-to-br ${getProviderFormGradient(selectedProvider?.id || 'custom')} flex items-center justify-center shadow-lg flex-shrink-0`}
                            aria-hidden="true"
                        >
                            <ProviderFormIcon providerId={selectedProvider?.id || 'custom'} />
                        </div>
                    )}
```
with:
```tsx
                    {(selectedProvider || isUniversal) && (
                        <div
                            className={`w-12 h-12 rounded-xl bg-gradient-to-br ${getProviderFormGradient(selectedProvider?.id || 'custom')} flex items-center justify-center shadow-lg flex-shrink-0`}
                            aria-hidden="true"
                        >
                            <ProviderLogo provider={selectedProvider?.id || 'custom'} className="w-6 h-6" />
                        </div>
                    )}
```

- [ ] **Step 4: Typecheck and run existing a11y test**

Run:
```bash
cd frontend && npx tsc --noEmit && npx vitest run src/components/models/__tests__/ModelCard.a11y.browser.test.tsx
```
Expected: typecheck clean; existing tests still PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/models/ModelConfigForm.tsx
git commit -m "feat: show brand logo in model config form"
```

---

### Task 5: Refresh backend `popular_models` and descriptions

**Files:**
- Modify: `backend/api/routes/models.py:304-415` (`list_providers()`)

**Interfaces:**
- Consumes: nothing new (edits string literals).
- Produces: updated `ProviderInfo.popular_models` and `description` values returned by `GET /api/v1/models/providers`.

- [ ] **Step 1: Write a backend test asserting current seeds**

Create `backend/tests/unit/test_provider_seeds.py`:
```python
from fastapi.testclient import TestClient
from backend.main import app

client = TestClient(app)

EXPECTED = {
    "openai": ["gpt-5.6", "gpt-5.6-mini", "gpt-5.1", "o4-mini"],
    "anthropic": ["claude-opus-4-5", "claude-sonnet-4-5", "claude-haiku-4-5"],
    "gemini": ["gemini-2.5-flash", "gemini-2.5-pro", "gemini-2.0-flash"],
    "groq": ["llama-3.3-70b-versatile", "llama-3.1-8b-instant", "deepseek-r1-distill-llama-70b"],
    "mistral": ["mistral-large-latest", "mistral-small-latest", "codestral-latest"],
    "together": ["meta-llama/Llama-3.3-70B-Instruct-Turbo", "Qwen/Qwen2.5-72B-Instruct-Turbo", "deepseek-ai/DeepSeek-R1"],
    "cohere": ["command-r-plus", "command-r"],
    "moonshot": ["kimi-k2", "moonshot-v1-32k", "moonshot-v1-128k"],
    "deepseek": ["deepseek-chat", "deepseek-reasoner"],
    "azure_openai": ["gpt-5.6", "gpt-5.1", "gpt-4o"],
    "local": ["llama3.1", "mistral", "gemma2", "qwen2"],
}

def test_provider_seeds_are_current():
    res = client.get("/api/v1/models/providers")
    assert res.status_code == 200
    by_name = {p["name"]: p for p in res.json()}
    for name, models in EXPECTED.items():
        assert by_name[name]["popular_models"] == models, name
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/unit/test_provider_seeds.py -v`
Expected: FAIL (current seeds still list `gpt-4o`, etc.).

- [ ] **Step 3: Update `list_providers()`**

In `backend/api/routes/models.py`, replace the `providers = [` block (lines 304-415) with:
```python
    providers = [
        ProviderInfo(
            id=ProviderType.OPENAI.value,
            name="openai",
            display_name="OpenAI",
            requires_api_key=True,
            requires_base_url=False,
            default_base_url="https://api.openai.com/v1",
            description="GPT-5.6, GPT-5.1, o4-mini and other OpenAI models",
            popular_models=["gpt-5.6", "gpt-5.6-mini", "gpt-5.1", "o4-mini"]
        ),
        ProviderInfo(
            id=ProviderType.ANTHROPIC.value,
            name="anthropic",
            display_name="Anthropic Claude",
            requires_api_key=True,
            requires_base_url=False,
            default_base_url="https://api.anthropic.com/v1",
            description="Claude Opus, Sonnet, Haiku - excellent reasoning and coding",
            popular_models=["claude-opus-4-5", "claude-sonnet-4-5", "claude-haiku-4-5"]
        ),
        ProviderInfo(
            id=ProviderType.GEMINI.value,
            name="gemini",
            display_name="Google Gemini",
            requires_api_key=True,
            requires_base_url=False,
            default_base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
            description="Google's multimodal models (Gemini 2.5 Flash, 2.5 Pro)",
            popular_models=["gemini-2.5-flash", "gemini-2.5-pro", "gemini-2.0-flash"]
        ),
        ProviderInfo(
            id=ProviderType.GROQ.value,
            name="groq",
            display_name="Groq",
            requires_api_key=True,
            requires_base_url=False,
            default_base_url="https://api.groq.com/openai/v1",
            description="Ultra-fast inference (100+ tokens/sec) with Llama 3.3",
            popular_models=["llama-3.3-70b-versatile", "llama-3.1-8b-instant", "deepseek-r1-distill-llama-70b"]
        ),
        ProviderInfo(
            id=ProviderType.MISTRAL.value,
            name="mistral",
            display_name="Mistral AI",
            requires_api_key=True,
            requires_base_url=False,
            default_base_url="https://api.mistral.ai/v1",
            description="European AI with Mistral, Mixtral, and Codestral",
            popular_models=["mistral-large-latest", "mistral-small-latest", "codestral-latest"]
        ),
        ProviderInfo(
            id=ProviderType.TOGETHER.value,
            name="together",
            display_name="Together AI",
            requires_api_key=True,
            requires_base_url=False,
            default_base_url="https://api.together.xyz/v1",
            description="Access to 100+ open-source models (Llama 3.3, Qwen 2.5)",
            popular_models=["meta-llama/Llama-3.3-70B-Instruct-Turbo", "Qwen/Qwen2.5-72B-Instruct-Turbo", "deepseek-ai/DeepSeek-R1"]
        ),
        ProviderInfo(
            id=ProviderType.COHERE.value,
            name="cohere",
            display_name="Cohere",
            requires_api_key=True,
            requires_base_url=False,
            default_base_url="https://api.cohere.ai/v1",
            description="Command R+ and Embed models",
            popular_models=["command-r-plus", "command-r"]
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
            popular_models=["gpt-5.6", "gpt-5.1", "gpt-4o"]
        ),
        ProviderInfo(
            id=ProviderType.LOCAL.value,
            name="local",
            display_name="Local (Ollama/LM Studio)",
            requires_api_key=False,
            requires_base_url=False,
            default_base_url=settings.OLLAMA_BASE_URL,
            description="Run models locally with Ollama or LM Studio",
            popular_models=["llama3.1", "mistral", "gemma2", "qwen2"]
        ),
    ]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/unit/test_provider_seeds.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/api/routes/models.py backend/tests/unit/test_provider_seeds.py
git commit -m "feat: refresh provider popular_models to current flagship models"
```

---

### Task 6: Final verification

**Files:** (no new changes — verification only)

- [ ] **Step 1: Frontend typecheck + lint + component tests**

Run:
```bash
cd frontend && npx tsc --noEmit && npm run lint && npx vitest run src/components/models/
```
Expected: clean typecheck, lint passes, all model-component tests PASS.

- [ ] **Step 2: Backend tests for the models route**

Run:
```bash
cd backend && python -m pytest tests/unit/test_provider_seeds.py tests/ -k models -v
```
Expected: PASS.

- [ ] **Step 3: Manual sanity (optional, local dev)**

Start the stack (`make up`), open the Models page and the Add Provider flow; confirm brand logos render for each provider, and an unknown/custom provider still shows the Lucide glyph. Confirm the suggestion chips now list the refreshed models.

- [ ] **Step 4: Final commit (only if any verification fixes were needed)**

```bash
git add -A && git commit -m "fix: address verification issues for provider logos + model seeds"
```

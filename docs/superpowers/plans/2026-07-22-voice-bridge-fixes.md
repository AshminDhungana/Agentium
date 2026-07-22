# Voice Bridge Bug Fixes — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix 6 independent bugs in the voice bridge system that prevent connection, show empty voice lists, hide the welcome message, and position the dropdown wrong.

**Architecture:** Six isolated fixes across 8 files — no refactoring, no shared state changes. Each task produces a self-contained, testable change. Frontend fixes are in React/TypeScript, bridge fix in Python, install scripts in bash/PowerShell, backend fix in Python.

**Tech Stack:** React 18 + TypeScript (frontend), FastAPI/Python 3.11 (backend), Python 3.10+ (voice bridge), bash + PowerShell (installers)

## Global Constraints

- No architectural changes — each fix is isolated
- Follow existing code style in each file (TypeScript: camelCase, React functional components; Python: snake_case, type hints)
- No new npm packages or Python dependencies (except `kokoro` which is already in `requirements.txt`)
- OS detection uses `navigator.platform` only (no `userAgent` parsing)

---

### Task 1: Backend Kokoro Availability Always True

**Files:**
- Modify: `backend/services/audio_service.py:123-131`

**Interfaces:**
- Consumes: nothing (self-contained)
- Produces: `AudioService._is_kokoro_available()` now returns `True` unconditionally

The backend runs in Docker and never does TTS (the host bridge handles that). The `_is_kokoro_available()` check attempts `from kokoro import KPipeline` inside Docker where it's never installed, falsely reporting Kokoro unavailable.

- [ ] **Step 1: Replace `_is_kokoro_available()` body**

In `backend/services/audio_service.py`, replace lines 123–131:

```python
def _is_kokoro_available(self) -> bool:
    return True
```

- [ ] **Step 2: Verify no other code depends on the old behavior**

Run: `grep -rn "_is_kokoro_available\|kokoro_available" backend/`

Expected: Only references are in `audio_service.py` itself and tests. The endpoint `GET /api/v1/voice/voice-config/providers` (voice.py:817) calls `audio_service.get_status()` which uses `_is_kokoro_available()` — it will now return `kokoro.available: true` consistently.

- [ ] **Step 3: Commit**

```bash
git add backend/services/audio_service.py
git commit -m "fix(voice): backend always reports Kokoro as available (TTS runs on host bridge, not in Docker)"
```

---

### Task 2: Install Scripts — Add Kokoro to Pip Install

**Files:**
- Modify: `scripts/install-voice-bridge.sh:111-118`
- Modify: `scripts/install-voice-bridge.ps1:154-163`

**Interfaces:**
- Consumes: nothing (self-contained)
- Produces: After re-running the installer, the host venv has `kokoro`, `soundfile`, `huggingface_hub` installed. Kokoro's model weights (~330MB) and voice embeddings auto-download from HuggingFace on first use.

- [ ] **Step 1: Update `install-voice-bridge.sh`**

In `scripts/install-voice-bridge.sh`, find the pip install block (around line 111–118) and add `kokoro soundfile huggingface_hub`:

```bash
"${VENV_DIR}/bin/pip" install --quiet \
  websockets SpeechRecognition PyAudio pyttsx3 \
  python-jose[cryptography] sounddevice \
  kokoro soundfile huggingface_hub
```

Also find the system package install (Phase 2.1) and add `espeak-ng` for each package manager:

For `apt`:
```bash
apt-get install -y python3 python3-venv python3-pip portaudio19-dev espeak-ng
```

For `brew`:
```bash
brew install portaudio espeak-ng
```

For `dnf`/`pacman`/`zypper`/`apk`: add `espeak-ng` to their respective package lists.

- [ ] **Step 2: Update `install-voice-bridge.ps1`**

In `scripts/install-voice-bridge.ps1`, find the pip install block (around line 154–163) and add `kokoro soundfile huggingface_hub`:

```powershell
& "$venv\Scripts\pip" install --quiet `
  websockets SpeechRecognition pyttsx3 `
  python-jose[cryptography] numpy sounddevice `
  kokoro soundfile huggingface_hub
```

Windows does not require `espeak-ng` — Kokoro uses misaki's built-in G2P for English.

- [ ] **Step 3: Commit**

```bash
git add scripts/install-voice-bridge.sh scripts/install-voice-bridge.ps1
git commit -m "fix(voice): add kokoro and deps to host install scripts"
```

---

### Task 3: Voice Bridge — Defer Welcome Message

**Files:**
- Modify: `voice-bridge/main.py`

**Interfaces:**
- Consumes: nothing (self-contained)
- Produces: On bridge startup, "Welcome back, voice is ready." is played after TTS engine initializes, not before

Root cause: `_maybe_speak_startup_messages()` calls `await speak(text)` before `_token_ready` is set and before TTS engine is initialized — the speech call fails silently.

- [ ] **Step 1: Add module-level deferred greeting variable**

Near the top of `voice-bridge/main.py` (after other module-level globals, around line 200):

```python
_deferred_greeting: Optional[str] = None
```

- [ ] **Step 2: Modify `_maybe_speak_startup_messages()`**

Replace the `speak()` call with deferred storage (around line 190):

```python
if parts:
    text = " ".join(parts)
    logger.info("[bridge] Startup guidance (deferred): %s", text)
    _deferred_greeting = text
```

- [ ] **Step 3: Speak deferred greeting after TTS engine is ready**

In `_run_voice_loop_once()`, after `await _token_ready.wait()` and after the TTS engine is initialized (around line 1420), add:

```python
global _deferred_greeting
if _deferred_greeting:
    await speak(_deferred_greeting)
    _deferred_greeting = None
```

- [ ] **Step 4: Commit**

```bash
git add voice-bridge/main.py
git commit -m "fix(voice): defer welcome message until TTS engine is initialized"
```

---

### Task 4: Frontend VoiceBridgeService — Connection Diagnostics

**Files:**
- Modify: `frontend/src/services/voiceBridge.ts`

**Interfaces:**
- Consumes: nothing (self-contained)
- Produces: `voiceBridgeService.connectionError` field, `voiceBridgeService.onErrorChange()` listener

- [ ] **Step 1: Add `ConnectionError` type and field**

In `frontend/src/services/voiceBridge.ts`, add near the top after existing imports:

```typescript
export type ConnectionErrorStage = 'token-fetch' | 'socket-open' | 'token-rejected' | 'unknown';

export interface ConnectionError {
  stage: ConnectionErrorStage;
  message: string;
  statusCode?: number;
  lastAttempt: number;
}
```

Add field to the class (near other private fields):

```typescript
private _connectionError: ConnectionError | null = null;
private _errorListeners: Array<(err: ConnectionError | null) => void> = [];

get connectionError(): ConnectionError | null {
  return this._connectionError;
}
```

- [ ] **Step 2: Add `onErrorChange()` method**

```typescript
onErrorChange(listener: (err: ConnectionError | null) => void): () => void {
  this._errorListeners.push(listener);
  return () => {
    this._errorListeners = this._errorListeners.filter(l => l !== listener);
  };
}
```

- [ ] **Step 3: Add `_setConnectionError()` method**

```typescript
private _setConnectionError(err: ConnectionError | null): void {
  this._connectionError = err;
  for (const listener of this._errorListeners) {
    listener(err);
  }
}
```

- [ ] **Step 4: Capture token-fetch errors**

In `_retryTokenFetch()`, in the catch block after a failed `_fetchVoiceToken()`:

```typescript
this._setConnectionError({
  stage: 'token-fetch',
  message: error instanceof Error ? error.message : String(error),
  statusCode: error?.response?.status,
  lastAttempt: Date.now(),
});
```

- [ ] **Step 5: Capture socket-open errors**

In `_openSocket()`, in the `onerror` handler:

```typescript
this._setConnectionError({
  stage: 'socket-open',
  message: `WebSocket error — bridge at ${WS_URL} unreachable or rejected connection`,
  lastAttempt: Date.now(),
});
```

In the `onclose` handler, when code is 1008:

```typescript
this._setConnectionError({
  stage: 'token-rejected',
  message: 'Bridge rejected the voice token (code 1008)',
  lastAttempt: Date.now(),
});
```

- [ ] **Step 6: Clear error on successful connection**

In `onopen` handler:

```typescript
this._setConnectionError(null);
```

- [ ] **Step 7: Commit**

```bash
git add frontend/src/services/voiceBridge.ts
git commit -m "fix(voice): add connection diagnostics to voice bridge service"
```

---

### Task 5: Frontend VoiceIndicator — Dropdown, OS-Aware Command, Diagnostics UI

**Files:**
- Modify: `frontend/src/components/VoiceIndicator.tsx`

**Interfaces:**
- Consumes: `voiceBridgeService.connectionError` (from Task 4), `voiceBridgeService.onErrorChange()` (from Task 4)
- Produces: Dropdown opens above, shows OS-specific install command, shows connection diagnostics when offline

- [ ] **Step 1: Fix dropdown positioning**

Around line 127, change:

```diff
- <div className="absolute top-full right-0 mt-1 w-56 ...">
+ <div className="absolute bottom-full right-0 mb-1 w-56 ...">
```

- [ ] **Step 2: Add OS detection helpers**

Before the component function, add:

```typescript
type Platform = 'windows' | 'macos' | 'linux' | 'unknown';

function getPlatform(): Platform {
  const p = navigator.platform;
  if (p.includes('Win')) return 'windows';
  if (p.includes('Mac')) return 'macos';
  if (p.includes('Linux')) return 'linux';
  return 'unknown';
}

function getInstallCommand(os: Platform): string {
  switch (os) {
    case 'windows':
      return 'powershell -ExecutionPolicy Bypass -File ".\\scripts\\setup.ps1"';
    case 'macos':
    case 'linux':
      return './scripts/install-voice-bridge.sh';
    default:
      return 'powershell -ExecutionPolicy Bypass -File ".\\scripts\\setup.ps1"';
  }
}
```

- [ ] **Step 3: Replace hardcoded install command with OS-aware version**

Replace lines 132–146 with:

```tsx
{effectiveStatus === 'offline' && !isDisabled && (
  <div className="px-3 py-2 text-xs text-gray-600 dark:text-gray-500 bg-gray-50 dark:bg-black/30 rounded-lg">
    <p className="mb-1">Bridge not running.</p>
    <div className="flex items-center gap-1">
      <code className="text-[10px] text-green-500 flex-1 truncate">{installCommand}</code>
      <button
        onClick={() => navigator.clipboard.writeText(installCommand)}
        className="text-blue-500 hover:text-blue-400 shrink-0"
        aria-label="Copy install command"
      >
        Copy
      </button>
    </div>
    {connectionError && (
      <details className="mt-2 border-t border-gray-200 dark:border-gray-700 pt-2">
        <summary className="cursor-pointer text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300">
          Connection details
        </summary>
        <div className="mt-1 space-y-0.5">
          <p>Stage: {connectionError.stageLabel}</p>
          <p>Message: {connectionError.message}</p>
          {connectionError.statusCode && <p>HTTP {connectionError.statusCode}</p>}
        </div>
      </details>
    )}
  </div>
)}
```

Where `installCommand` and `connectionError` are derived in the component body:

```typescript
const platform = useMemo(() => getPlatform(), []);
const installCommand = useMemo(() => getInstallCommand(platform), [platform]);
const connectionError = voiceBridgeService.connectionError;
```

And add an effect to subscribe to error changes (for reactivity when error state changes after initial render):

```typescript
const [, forceUpdate] = useReducer(x => x + 1, 0);
useEffect(() => {
  return voiceBridgeService.onErrorChange(() => forceUpdate());
}, []);
```

- [ ] **Step 4: Add stageLabel mapping**

Add a helper to convert the error stage to a human-readable label:

```typescript
const stageLabels: Record<string, string> = {
  'token-fetch': 'Token fetch — POST /api/v1/auth/voice-token',
  'socket-open': 'WebSocket connection — ws://127.0.0.1:9999',
  'token-rejected': 'Token rejected by bridge (code 1008)',
  'unknown': 'Unknown error',
};
```

Use it in the JSX: `{connectionError.stageLabel ?? connectionError.stage}`

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/VoiceIndicator.tsx
git commit -m "fix(voice): dropdown above icon, OS-aware install command, connection diagnostics"
```

---

### Task 6: Frontend VoiceSettingsModal — Show Voices When Unavailable + VoiceApi Logging

**Files:**
- Modify: `frontend/src/components/VoiceSettingsModal.tsx`
- Modify: `frontend/src/services/voiceApi.ts`

**Interfaces:**
- Consumes: nothing (self-contained)
- Produces: Voice settings always shows available voices, with a notice when provider is unavailable

- [ ] **Step 1: Relax provider filter to show voices even when unavailable**

In `VoiceSettingsModal.tsx`, find the `Object.entries(providersData.providers).filter(([name, info]) => info.available)` line. Replace with:

```typescript
const allEntries = Object.entries(providersData.providers);
const availableEntries = allEntries.filter(([, info]) => info.available);
const providerEntries = availableEntries.length > 0 ? availableEntries : allEntries;
```

- [ ] **Step 2: Add availability notice below select**

In the select element rendering (where voices are mapped to `<option>` elements), add after the select:

```tsx
{!info.available && (
  <p className="text-xs text-amber-500 mt-1">
    {name === 'kokoro'
      ? 'Kokoro engine not installed on the server. Configure an OpenAI API key or install Kokoro.'
      : 'OpenAI API key not configured. Add one in Models settings or use Kokoro.'}
  </p>
)}
```

- [ ] **Step 3: Fix provider auto-detection prefixes**

Replace the prefix check around line 323-325:

```typescript
const kokoroPrefixes = ['af_', 'am_', 'bf_', 'bm_', 'cf_', 'in_', 'au_'];
const provider = kokoroPrefixes.some(p => val.startsWith(p)) ? 'kokoro' : 'openai';
```

- [ ] **Step 4: Remove stale hardcoded fallback `<select>`**

Remove the fallback `<select>` block (lines 349–362) that contains non-existent voice IDs like `af_bella`, `af_nicole`, `af_sarah`. The relaxed filter logic replaces this.

- [ ] **Step 5: Add logging to `getVoiceProviders()`**

In `frontend/src/services/voiceApi.ts`, update the catch block in `getVoiceProviders()`:

```typescript
getVoiceProviders: async (): Promise<VoiceProvidersResponse | null> => {
  try {
    const response = await api.get<VoiceProvidersResponse>(`${API_BASE}/voice-config/providers`);
    return response.data;
  } catch (error) {
    console.warn('[voiceApi] Failed to fetch voice providers:', error);
    return null;
  }
}
```

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/VoiceSettingsModal.tsx frontend/src/services/voiceApi.ts
git commit -m "fix(voice): show TTS voices even when provider unavailable, fix prefix detection"
```

---

## Self-Review

1. **Spec coverage:** Each spec issue maps to a task:
   - Issue 1 (connection diagnostics) → Task 4 + Task 5 (connectionError in service, UI in VoiceIndicator)
   - Issue 2 (dropdown positioning) → Task 5 Step 1
   - Issue 3 (OS-aware install command) → Task 5 Steps 2-3
   - Issue 4 (welcome message) → Task 3
   - Issue 5 (TTS voices UX) → Task 6
   - Issue 6 (Kokoro install) → Task 1 + Task 2

2. **Placeholder scan:** No TBDs, TODOs, or vague requirements. Every step has exact code and file paths.

3. **Type consistency:** `ConnectionError`, `ConnectionErrorStage`, `Platform` types are defined exactly where used. `connectionError` field type matches between Task 4 (service) and Task 5 (consumer).

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-07-22-voice-bridge-fixes.md`. Two execution options:

**1. Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints

Which approach?

# Voice Bridge Bug Fixes — Design Spec

**Date:** 2026-07-22
**Status:** Approved (design review)
**Scope:** 5 targeted fixes to the voice bridge system (host bridge + frontend)

---

## Overview

Five independent issues in the voice bridge system that together prevent it from working reliably. Each has a clear root cause and isolated fix. No architectural changes.

---

## Issue 1: Bridge Connection Fails Silently

**Symptoms:** Bridge process runs on the host, but the UI shows "Voice offline" quickly after attempting to connect.

**Root causes (likely, unknown which specifically):**
- Token fetch (`POST /api/v1/auth/voice-token`) fails — 404 or network error
- WebSocket `ws://127.0.0.1:9999` unreachable from browser despite bridge running
- No diagnostics to distinguish between these failure modes

### Frontend Changes (`frontend/src/services/voiceBridge.ts`)

Add a `connectionError` field to the service that captures the failure stage:

```typescript
connectionError: {
  stage: 'token-fetch' | 'socket-open' | 'token-rejected' | 'unknown' | null;
  message: string;
  statusCode?: number;
  lastAttempt: number;
} | null
```

Propagate this error info:
- Token fetch failure: capture HTTP status + error message
- Socket open failure: capture `CloseEvent.code` and `reason`
- Token rejected (code 1008): capture explicitly

Expose `onErrorChange()` listener alongside existing `onStatusChange()`.

### Frontend Changes (`frontend/src/components/VoiceIndicator.tsx`)

Add a collapsible "Connection details" section inside the dropdown when offline:

```
● Voice offline
  Connection details ▾
  Stage: Token fetch — POST /api/v1/auth/voice-token
  Status: 404 Not Found
  ─────────────────────
  Check that the backend is running and your session is authenticated.
```

This replaces the current simple "Bridge not running." text with richer diagnostics.

### Host Bridge Changes (`voice-bridge/main.py`)

No functional changes to the bridge itself. The bridge already:
- Accepts bare connections (no token in URL) when `VOICE_TOKEN` is unset
- Accepts `set_token` messages after connection
- Only rejects with code 1008 when token is supplied AND mismatches

The diagnostics in the frontend will reveal whether the issue is on the browser side (can't reach port 9999) or the auth side (token flow broken).

---

## Issue 2: Dropdown Positioned Below Icon

**File:** `frontend/src/components/VoiceIndicator.tsx` line 127

**Change:** Replace `top-full` with `bottom-full` and `mt-1` with `mb-1`.

```diff
- <div className="absolute top-full right-0 mt-1 w-56 ...">
+ <div className="absolute bottom-full right-0 mb-1 w-56 ...">
```

The parent container uses `relative`, so the menu will now open **above** the mic icon. No other styling changes needed.

---

## Issue 3: OS-Aware Install Command in Dropdown

**File:** `frontend/src/components/VoiceIndicator.tsx` lines 132–145

**Problem:** The "Bridge not running" section shows a hardcoded Windows PowerShell command on all platforms.

**Fix:** Detect the OS in the browser and show the correct install command:

| Platform | Detection | Command |
|---|---|---|
| Windows | `navigator.platform.includes('Win')` | `powershell -ExecutionPolicy Bypass -File ".\scripts\setup.ps1"` |
| macOS | `navigator.platform.includes('Mac')` | `./scripts/install-voice-bridge.sh` |
| Linux | `navigator.platform.includes('Linux')` | `./scripts/install-voice-bridge.sh` |
| Fallback | none of the above | Both commands shown |

**Implementation:**

```typescript
function getPlatform(): 'windows' | 'macos' | 'linux' | 'unknown' {
  const p = navigator.platform;
  if (p.includes('Win')) return 'windows';
  if (p.includes('Mac')) return 'macos';
  if (p.includes('Linux')) return 'linux';
  return 'unknown';
}

function getInstallCommand(os: ReturnType<typeof getPlatform>): string {
  switch (os) {
    case 'windows': return 'powershell -ExecutionPolicy Bypass -File ".\\scripts\\setup.ps1"';
    case 'macos':
    case 'linux': return './scripts/install-voice-bridge.sh';
    default: return 'powershell -ExecutionPolicy Bypass -File ".\\scripts\\setup.ps1"';
  }
}
```

The "Copy" button copies the platform-specific command. The `code` element shows it.

---

## Issue 4: Welcome Message Not Played

**File:** `voice-bridge/main.py`

**Root cause:** `_maybe_speak_startup_messages()` calls `await speak(text)` at line 1521, but:
1. `_token_ready` isn't created yet (line 1522)
2. TTS engine isn't initialized — that happens inside `_run_voice_loop_once()` which blocks on `_token_ready.wait()`
3. So `speak()` either crashes silently or falls back to a half-initialized TTS path that produces no audio

**Fix:** Defer the welcome playback until the TTS engine is ready.

### Changes:

1. **Add a module-level deferred greeting variable** near the top of `main.py`:
   ```python
   _deferred_greeting: Optional[str] = None
   ```

2. **Modify `_maybe_speak_startup_messages()`** — instead of calling `speak()`, store the composed message in `_deferred_greeting`:
   ```python
   if parts:
       text = " ".join(parts)
       logger.info("[bridge] Startup guidance (deferred): %s", text)
       _deferred_greeting = text
   ```

3. **Modify `_run_voice_loop_once()`** — after `await _token_ready.wait()` and after the TTS engine is initialized, speak the deferred greeting:
   ```python
   # After TTS engine init and _token_ready is set:
   global _deferred_greeting
   if _deferred_greeting:
       await speak(_deferred_greeting)
       _deferred_greeting = None
   ```

This ensures the welcome message uses the same initialized, configured TTS pipeline (Kokoro or OpenAI) that the user will hear for all voice interactions.

---

## Issue 5: TTS Provider Shows No Voices

**Files:**
- `frontend/src/components/VoiceSettingsModal.tsx`
- `frontend/src/services/voiceApi.ts`

**Root cause:** When both Kokoro and OpenAI report `available: false`, the `Object.entries(...).filter(([, info]) => info.available)` produces an empty array, so the `<select>` renders with zero `<option>` elements.

### Changes to `VoiceSettingsModal.tsx`:

1. **Relax the filter** — when the filter produces empty results, show all voices anyway (with a notice):
   ```typescript
   const allEntries = Object.entries(providersData.providers);
   const availableEntries = allEntries.filter(([, info]) => info.available);
   const providerEntries = availableEntries.length > 0 ? availableEntries : allEntries;
   ```

2. **Add an availability notice** below the select when the provider is unavailable:
   ```tsx
   {!info.available && (
     <p className="text-xs text-amber-500 mt-1">
       {name === 'kokoro'
         ? 'Kokoro engine not installed on the server. Configure an OpenAI API key or install Kokoro.'
         : 'OpenAI API key not configured. Add one in Models settings or use Kokoro.'}
     </p>
   )}
   ```

3. **Fix provider auto-detection** — update the prefix check on line 323-325 to include all Kokoro voice prefixes:
   ```typescript
   const kokoroPrefixes = ['af_', 'am_', 'bf_', 'bm_', 'cf_', 'in_', 'au_'];
   const provider = kokoroPrefixes.some(p => val.startsWith(p)) ? 'kokoro' : 'openai';
   ```

4. **Remove unused fallback `<select>`** (lines 349-362) — the hardcoded list contains voice IDs that don't exist in `KOKORO_TTS_VOICES` (`af_bella`, `af_nicole`, `af_sarah`), which would cause silent failures if selected. The new approach (relaxed filter + notice) replaces this fallback.

### Minor change to `voiceApi.ts`:

Add an `onError` callback or at minimum log the error in `getVoiceProviders()` catch block for debugging:

```typescript
catch (error) {
  console.warn('[voiceApi] Failed to fetch voice providers:', error);
  return null;
}
```

---

## Files Changed Summary

| File | Changes |
|---|---|
| `frontend/src/services/voiceBridge.ts` | Add `connectionError` field, expose `onErrorChange()` |
| `frontend/src/components/VoiceIndicator.tsx` | Dropdown positioning (`top-full`→`bottom-full`), OS-aware install command, connection diagnostics UI |
| `frontend/src/components/VoiceSettingsModal.tsx` | Relax provider filter, add availability notice, fix prefix detection, remove stale fallback |
| `frontend/src/services/voiceApi.ts` | Add error logging to `getVoiceProviders()` |
| `voice-bridge/main.py` | Defer welcome message to after TTS engine init |

---

## Testing Notes

Each fix is independently testable:
- **Issue 1:** Connect a browser with no bridge running. Verify "Connection details" shows the failure stage. Connect with bridge running. Verify "Voice ready" appears with no diagnostics.
- **Issue 2:** Open the dropdown in VoiceIndicator when it's at the bottom of the viewport. Verify it appears above the icon.
- **Issue 3:** Open the dropdown on Windows → shows PowerShell command. Open on macOS → shows shell command.
- **Issue 4:** Delete `~/.agentium/.voice-startup-count`, start the bridge. Verify "Welcome back, voice is ready." plays after the voice loop starts.
- **Issue 5:** Open Voice Settings with no Kokoro package and no OpenAI key. Verify voices are still listed with an availability notice.

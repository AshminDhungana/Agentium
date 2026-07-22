# Voice Bridge Desktop Overlay Animation — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the PySide6 desktop overlay (orb + speaking indicator) animate when the voice bridge says its welcome message, on Windows/macOS/Linux.

**Architecture:** Add a `_current_state` global to the bridge that tracks voice state; broadcast `voice_state` events around the deferred welcome message in `_run_voice_loop_once()`; sync current state to newly connected WebSocket clients so the Desktop UI catches up even if it connects late.

**Tech Stack:** Python 3.10+, asyncio, websockets, PySide6 6.5+, QML (QtQuick 2.15+)

## Global Constraints

- Bridge imports: `aiohttp`, `json`, `logging`, `asyncio`, `time`, `pathlib`
- WS messages use JSON with fields: `type` (str), `state` (str for voice_state), `role` (str for transcript), `text` (str for transcript), `ts` (float)
- Voice state strings: `"idle"`, `"listening"`, `"thinking"`, `"speaking"`, `"interrupted"`
- All new code must be compatible with Python 3.10+
- No additional dependencies — only use modules already imported in `main.py`

---

## File Structure

| File | Status | Responsibility |
|------|--------|----------------|
| `voice-bridge/main.py` | Modify | Add `_current_state` global; broadcast state during deferred greeting; sync state on WS connect; update `VoiceSession._broadcast_state()` |
| `voice-bridge/ui/overlay_manager.py` | Modify | Add `raise_()` after `show()` for Windows paint reliability |

---

### Task 1: Bridge State Tracking + Welcome Broadcast

**Files:**
- Modify: `voice-bridge/main.py` (globals section + `_run_voice_loop_once()`)

**Interfaces:**
- Consumes: existing `_deferred_greeting`, `_broadcast()`, `_connected_browsers`
- Produces: `_current_state` global (str), `_broadcast` calls with `voice_state` and `transcript` types

- [ ] **Step 1: Add `_current_state` global**

Add near the existing globals around line 198 in `voice-bridge/main.py`, right after `_deferred_greeting: Optional[str] = None`:

```python
_current_state: str = "idle"
```

- [ ] **Step 2: Add import for `Optional` if missing**

Check line 57: `from typing import Optional, Tuple`. If `Optional` is imported, skip this step. If not, add it:

```python
from typing import Optional, Tuple
```

- [ ] **Step 3: Update deferred greeting block to broadcast state**

Replace the deferred greeting block in `_run_voice_loop_once()` (lines 1428-1436) with:

```python
    global _deferred_greeting, _current_state
    if _deferred_greeting:
        _current_state = "speaking"
        await _broadcast({"type": "voice_state", "state": "speaking", "ts": time.time()})

        await _broadcast({"type": "transcript", "role": "agent",
                           "text": _deferred_greeting, "ts": time.time()})

        logger.info("[bridge] Speaking deferred startup message")
        try:
            audio = tts.synth(_deferred_greeting)
            if audio:
                tts.play(audio)
        except Exception as exc:
            logger.warning("[bridge] Could not speak deferred greeting: %s", exc)

        await asyncio.sleep(1.0)

        _current_state = "idle"
        await _broadcast({"type": "voice_state", "state": "idle", "ts": time.time()})
        _deferred_greeting = None
```

- [ ] **Step 4: Verify indentation is correct**

The block should be at the same indentation level as the existing `_deferred_greeting` block — inside `_run_voice_loop_once()`, after the TTS engine is initialized, before the wake-word loop starts. It should look like:

```python
    tts = _get_tts_engine()
    global _deferred_greeting, _current_state
    if _deferred_greeting:
        [block above]
    loop = asyncio.get_event_loop()
    [rest of function continues...]
```

- [ ] **Step 5: Commit**

```bash
git add voice-bridge/main.py
git commit -m "fix(voice): broadcast voice_state during welcome message for overlay animation"
```

---

### Task 2: VoiceSession Propagates State + Transcript Broadcast

**Files:**
- Modify: `voice-bridge/main.py` (VoiceSession._broadcast_state())

**Interfaces:**
- Consumes: `_current_state` global, `_broadcast()` function
- Produces: `_current_state` updated on every state change by VoiceSession

- [ ] **Step 1: Modify `VoiceSession._broadcast_state()` to update `_current_state`**

Find `VoiceSession._broadcast_state()` at line 1390-1391. Replace it with:

```python
    async def _broadcast_state(self, state: str):
        global _current_state
        _current_state = state
        await _broadcast({"type": "voice_state", "state": state, "ts": time.time()})
```

- [ ] **Step 2: Commit**

```bash
git add voice-bridge/main.py
git commit -m "fix(voice): VoiceSession propagates state to _current_state global"
```

---

### Task 3: State Sync on New WS Connection

**Files:**
- Modify: `voice-bridge/main.py` (`_ws_handler()`)

**Interfaces:**
- Consumes: `_current_state` global, `_connected_browsers` set
- Produces: WebSocket JSON message sent to each new client on connect

- [ ] **Step 1: Add state sync after client registration**

Find `_ws_handler()` at line 966. After `_connected_browsers.add(websocket)` (line 981) and the log line, add:

```python
    _connected_browsers.add(websocket)
    logger.info("[bridge][WS] Browser connected (%d total)", len(_connected_browsers))

    # Sync current state to newly connected client so it doesn't
    # miss events that happened before it connected.
    try:
        await websocket.send(json.dumps({
            "type": "voice_state",
            "state": _current_state,
            "ts": time.time(),
        }))
    except Exception:
        pass
```

The `try/except` ensures a failed sync (client disconnected between add and send) doesn't crash the handler. This is intentionally best-effort — the next state change will resync.

- [ ] **Step 2: Commit**

```bash
git add voice-bridge/main.py
git commit -m "fix(voice): sync current state to newly connected WS clients"
```

---

### Task 4: Desktop UI Overlay Paint Reliability

**Files:**
- Modify: `voice-bridge/ui/overlay_manager.py`

**Interfaces:**
- Consumes: `QQuickView`, `Qt.WindowType`
- Produces: `raise_()` call after `show()` on all three overlay views

- [ ] **Step 1: Add `raise_()` after `show()` calls**

Add `raise_()` calls after `show()` in three methods:

After `self._overlay_view.show()` in `show_overlay()` (line 91):

```python
    self._overlay_view.show()
    self._overlay_view.raise_()
```

After `self._indicator_view.show()` in `show_indicator()` (line 109):

```python
    self._indicator_view.show()
    self._indicator_view.raise_()
```

After `self._transcript_view.show()` in `show_transcript()` (line 168):

```python
    self._transcript_view.show()
    self._transcript_view.raise_()
```

`raise_()` forces the window to the top of the Z-order without stealing input focus (the windows already have `WindowTransparentForInput`). On Windows, this ensures the windowing system sends a paint event, which triggers the QML Canvas to render.

- [ ] **Step 2: Commit**

```bash
git add voice-bridge/ui/overlay_manager.py
git commit -m "fix(voice): add raise_() after overlay show() for Windows paint reliability"
```

---

### Task 5: Verify Changes

- [ ] **Step 1: Static check — verify main.py syntax**

```bash
python -c "import ast; ast.parse(open('voice-bridge/main.py').read()); print('OK')"
```

Expected output: `OK`

- [ ] **Step 2: Static check — verify overlay_manager.py syntax**

```bash
python -c "import ast; ast.parse(open('voice-bridge/ui/overlay_manager.py').read()); print('OK')"
```

Expected output: `OK`

- [ ] **Step 3: Verify task 1 — state broadcast in deferred greeting**

Check that `_current_state` appears exactly once before the greeting and once after:

```bash
python -c "
lines = open('voice-bridge/main.py').readlines()
state_assignments = [i+1 for i, l in enumerate(lines) if '_current_state =' in l]
print(f'_current_state assignments at lines: {state_assignments}')
print(f'voice_state broadcast lines: {[i+1 for i, l in enumerate(lines) if \"voice_state\" in l and \"_broadcast\" in l]}')
"
```

Expected: `_current_state` assigned at the right moments (speaking before greeting, idle after).

- [ ] **Step 4: Verify task 3 — WS sync message**

```bash
python -c "
lines = open('voice-bridge/main.py').readlines()
sync_lines = [i+1 for i, l in enumerate(lines) if 'voice_state' in l and 'current_state' in l and 'send' in l]
print(f'WS sync at lines: {sync_lines}')
"
```

Expected: at least one line found in `_ws_handler()`.

- [ ] **Step 5: Verify task 4 — raise_() calls**

```bash
python -c "
lines = open('voice-bridge/ui/overlay_manager.py').readlines()
raise_lines = [i+1 for i, l in enumerate(lines) if 'raise_()' in l]
print(f'raise_() calls at lines: {raise_lines}')
"
```

Expected: 3 lines (overlay_view, indicator_view, transcript_view).

- [ ] **Step 6: Test the bridge starts without errors**

Run the bridge (it will fail to connect to backend, but should not crash on import/syntax):

```bash
timeout 5 python voice-bridge/main.py 2>&1 || true
```

Expected: starts, logs "Agentium SecureVoiceBridge starting", may exit or hang — no `SyntaxError` or `ImportError`.

---

## Rollback Plan

Each task is independently revertible. If the overlay still doesn't show:
1. Check `voice-bridge.log` for the `[bridge] Speaking deferred startup message` log line
2. Check for `[bridge][WS] Browser connected` to confirm the Desktop UI connects
3. Check for `voice_state` messages in the WS sync flow
4. Test on a different platform to isolate platform-specific rendering issues

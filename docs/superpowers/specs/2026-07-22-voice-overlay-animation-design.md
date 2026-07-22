# Voice Bridge Desktop Overlay Animation — Design Spec

**Date:** 2026-07-22
**Status:** Approved
**Scope:** Fix the PySide6 desktop overlay animation to show when the bridge speaks the welcome message, on all platforms (Windows/macOS/Linux)

---

## Overview

The voice bridge speaks a "Welcome back, voice is ready." message on every 5th startup (and every startup when no API key is configured). The PySide6 desktop overlay (orb + speaking indicator + transcript window) should animate when this message plays — even when the browser/app is not opened. Currently the overlay shows nothing because the bridge never broadcasts state events during the welcome message, and the Desktop UI has no mechanism to auto-show on state.

The existing `2026-07-22-voice-bridge-fixes-design.md` deferred the welcome playback to `_run_voice_loop_once()` so it runs after TTS init. This spec builds on that: the overlay needs to animate during that deferred greeting.

### Core Flow

```
Bridge startup
  → _maybe_speak_startup_messages() stores deferred_greeting
  → WS server starts listening on :9999
  → Voice loop starts, waits for token
  → TTS engine initializes
  → ** Speak deferred greeting **
       → Broadcast voice_state="speaking" + transcript
       → tts.synth() + tts.play()
       → Broadcast voice_state="idle"
  → Enter wake-word detection loop

Desktop UI (anytime)
  → BridgeClient connects to ws://127.0.0.1:9999
  → Receives current voice_state sync → overlays auto-show if speaking
```

---

## Changes

### 1. Bridge State Tracking (`voice-bridge/main.py`)

Add a module-level current-state tracker:

```python
# Near existing globals (_deferred_greeting, _token_ready)
_current_state: str = "idle"
```

Update the deferred greeting block in `_run_voice_loop_once()` (around lines 1428-1436) to broadcast state:

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
    
    # Brief pause so the animation is visible during speech
    await asyncio.sleep(1.0)
    
    _current_state = "idle"
    await _broadcast({"type": "voice_state", "state": "idle", "ts": time.time()})
    _deferred_greeting = None
```

Also update `VoiceSession._broadcast_state()` to maintain `_current_state`:

```python
async def _broadcast_state(self, state: str):
    global _current_state
    _current_state = state
    await _broadcast({"type": "voice_state", "state": state, "ts": time.time()})
```

### 2. State Sync on New WS Connection (`voice-bridge/main.py`)

In `_ws_handler()`, after `_connected_browsers.add(websocket)` (line 981), push the current state to the new client immediately:

```python
_connected_browsers.add(websocket)
logger.info("[bridge][WS] Browser connected (%d total)", len(_connected_browsers))

# Sync current state to newly connected client
try:
    await websocket.send(json.dumps({
        "type": "voice_state",
        "state": _current_state,
        "ts": time.time(),
    }))
except Exception:
    pass
```

This ensures that if the Desktop UI connects **after** the welcome message already played, it still receives `voice_state: idle` — keeping its state machine consistent. If it connects **during** the welcome, it receives `voice_state: speaking` and the overlay shows the speaking indicator immediately.

### 3. Desktop UI Auto-Show (`voice-bridge/ui/overlay_manager.py`)

The `on_voice_state()` method already maps states to overlay actions. However, it requires a state **change** to trigger. When the BridgeClient first connects and receives a sync state, it emits `voice_state_changed` which triggers the method. The existing mapping already handles this correctly:

| Received State | Overlay Action |
|---|---|
| `idle` | Hides indicator and transcript; starts 1.5s auto-hide timer on orb if visible |
| `speaking` | Hides orb + transcript; shows indicator |
| `listening` | Shows orb + transcript; hides indicator |
| `thinking` | Updates indicator label only |

No changes needed to `on_voice_state()` — the existing state machine naturally handles the sync message.

However, the overlay windows use `opacity` property with `Behavior` animations. On first show, the timer (line 122-129 in `WaveformOverlay.qml`) has `running: opacity > 0`, which won't activate until `opacity` transitions above 0. This means:
- For `idle` sync: nothing shows (correct — bridge is idle)
- For `speaking` sync: indicator shows via `show_indicator()` → opacity goes to 1 → timer starts (correct)

One edge case: the **orb** overlay never shows on the `idle` sync. To make the overlay visible for the welcome message, the orb should show briefly when the bridge says "Welcome back" — but the current design hides the orb on `speaking` state and shows the indicator instead. This is intentional: the indicator is the "speaking" HUD, the orb is the "listening" HUD. The welcome message triggers the indicator, which draws attention to the system tray area.

If we want the orb to show as a more prominent visual for the welcome, we can add a `show_overlay()` call at the start of the greeting block. This is a visual preference — the indicator alone already provides feedback.

### 4. Cross-Platform Robustness (`voice-bridge/ui/overlay_manager.py` and QML files)

#### Windows

`_enable_acrylic()` uses `SetWindowCompositionAttribute` with `AccentState=4` (acrylic blur). This only works on Windows 11. On Windows 10, the call silently fails (wrapped in `try/except pass`). The window still renders with `color: "transparent"` — the QML Canvas paints on a transparent surface regardless of acrylic.

The real issue on Windows is that `setFlag(Qt.WindowType.WindowTransparentForInput, True)` combined with `setColor("transparent")` and a frameless window may not render the Canvas content if the GPU compositor path fails. Ensure `_overlay_view.show()` is called **before** `setColor("transparent")` on some Qt/Windows versions. Current code calls `show()` then `setColor("transparent")` — order is correct.

Call `raise()` after show() to ensure the window paints on first render:
```python
self._overlay_view.show()
self._overlay_view.raise_()
```

#### macOS

Transparent frameless windows on macOS require `Qt.WindowTransparentForInput` which is supported in Qt 6. However, macOS may not render Canvas content on a `META`-layer window. The `_enable_acrylic()` is no-op on non-Windows, which is correct. On macOS the window relies entirely on `setColor("transparent")` — ensure the `color` property is set before `show()`.

#### Linux

`MultiEffect` blur (used in `SpeakingIndicator.qml` and `TranscriptOverlay.qml`) requires a compositing window manager that supports the Qt Quick Effects API. On X11 without compositing, the blur layer silently fails — the window renders without blur, which is acceptable degradation.

### 5. PySide6 Installation on Linux

The bash install script (`install-voice-bridge.sh`) already handles `libgl1` / `libegl1` / `libxkbcommon0` system packages for PySide6 (lines 382-383). No changes needed.

### 6. Desktop UI Reliability on Restart

If the bridge restarts and the Desktop UI reconnects, the sync message brings the overlay state machine back into sync. The `BridgeClient` already has reconnection with exponential backoff (`_reconnect_delay`, `_max_backoff`). No changes needed.

---

## Files Changed

| File | Changes |
|---|---|
| `voice-bridge/main.py` | Add `_current_state` global; broadcast state around deferred greeting; sync state on WS connect; update `VoiceSession._broadcast_state()` |
| `voice-bridge/ui/overlay_manager.py` | Add `raise_()` after `show()` on overlay views for Windows paint reliability |

## Testing

1. **Windows test:** Start bridge, verify Desktop UI tray icon appears. Verify welcome message broadcasts state and the speaking indicator shows. Verify after welcome, overlay returns to idle state. Verify connecting UI after bridge already started (late connect) — receives idle sync, no glitch.

2. **macOS test:** Same as Windows, verify transparent windows render correctly.

3. **Linux test:** Same as Windows, verify no crash from missing compositor. Verify overlay renders (even without blur).

4. **Reconnect test:** Kill the bridge, wait for UI to show disconnected, restart bridge. Verify state sync on reconnect.

5. **Edge case — no token:** Bridge starts with no VOICE_TOKEN. Welcome message includes "Please add an API key." Should broadcast voice_state just like the normal welcome.

6. **Edge case — every-5th start:** Verify on startup count 1, 5, 10, etc. the welcome plays and overlay shows.

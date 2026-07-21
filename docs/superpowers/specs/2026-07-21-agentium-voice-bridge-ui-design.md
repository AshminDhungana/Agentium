# Agentium Voice Bridge UI — Desktop HUD Design

**Date:** 2026-07-21
**Status:** Approved
**Domain:** voice-bridge, ui

## Overview

A cinematic, cross-platform desktop HUD for the Agentium voice bridge. Written in Python (PySide6 + QML), it runs alongside the existing voice bridge process and connects to its local WebSocket (`ws://127.0.0.1:9999`) to listen for voice state events. The UI independently captures microphone audio levels via QtMultimedia for real-time waveform visualization — no changes are required to the existing voice bridge code.

## Design Principles

- **Invisible until needed** — lives in the system tray, never intrudes on screen space
- **Cinematic feedback** — smooth, Iron Man–style circular waveform for active speech
- **Minimal speaking indicator** — small pill in bottom-right during agent TTS
- **Cross-platform** — identical experience on Windows, macOS, and Linux
- **Agentium-native styling** — matches the project's dark navy + blue brand identity
- **Non-blocking overlay** — transparent areas pass mouse clicks through to underlying windows

## Visual Surfaces

### 1. Circular Waveform HUD (User Speaking)

**Trigger:** Voice bridge emits `voice_state = "listening"` (user is speaking)

**Appearance:**
- Circular overlay, ~280×280px, centered on screen where mouse cursor is (multi-monitor aware)
- 48 animated frequency bars arranged in a circle (like pipecat's CircularWaveform)
- Bar rendering via QML Canvas 2D with `requestAnimationFrame` for smooth 60fps
- Each bar scales radially based on mic audio level from `QAudioSource` input
- Native acrylic glassmorphism background using `pyside-native-glass` library (DWM Acrylic on Windows 11, NSVisualEffectView on macOS, QML MultiEffect blur fallback on Linux)
- Center: pulsing core circle (Agentium blue `#3b82f6`), surrounded by 2 subtle orbital rings
- Agentium blue `#3b82f6` bars with outer glow (`rgba(59, 130, 246, 0.15)` spread layer via `GaussianBlur`)
- Smooth opacity fade-in (~200ms `Behavior on opacity`), auto-hides 1.5s after state transitions to idle
- Click-through enabled (`Qt.WindowTransparentForInput`) while overlay is visible — no interaction blocking
- HiDPI-aware: uses `Qt.HighDpiScaleFactorRoundingPolicy.PassThrough` and scales canvas rendering by device pixel ratio

**State animations:**
| State | Visual |
|-------|--------|
| Listening | Bars animate with real mic input levels via `QAudioSource`, core pulses gently |
| Thinking (after user stops) | Bars sweep in a slow wave pattern via synthetic animation, no audio reactivity |
| Speaking (agent replies) | HUD fades out (`opacity: 0` over 200ms), speaking indicator takes over |

**Audio capture implementation:**
- `QAudioSource` captures from default microphone at 16kHz/16-bit mono
- Only reads RMS amplitude levels — raw audio is discarded, no recording or transcription
- `QTimer` at 30Hz feeds RMS values into the QML waveform Canvas
- Coexists with the voice bridge's PyAudio mic capture (both can access the mic on all platforms)

### 2. Speaking Indicator (Agent TTS)

**Trigger:** Voice bridge emits `voice_state = "speaking"`

**Appearance:**
- Small pill, ~120×36px, anchored 20px from bottom-right screen edge
- Glass background: native acrylic (same as HUD) with subtle blur
- Border: `rgba(59, 130, 246, 0.3)` hairline
- 3 vertical equalizer bars (Agentium blue) that animate with a synthetic waveform generator (pulsing at variable speed/height during speaking state — no real-time TTS audio capture needed)
- Smooth fade-in/out (~300ms `Behavior on opacity`), hidden during idle/listening
- Also click-through enabled

**Re-entry:** If user interrupts (barge-in → `voice_state = "listening"`), pill hides immediately (100ms fade), HUD reappears.

### 3. Overlay (Manual Toggle)

**Trigger:** System tray "Show Overlay" clicked, or left-click on tray icon

**Appearance:** Same circular waveform HUD but persists until user dismisses or clicks tray again. Shows a gentle idle animation (slowly rotating orbital ring).

## System Tray Integration

- **Icon:** Agentium blue circular microphone icon (SVG → multi-resolution PNG, 16×16 and 32×32, path relative to script via `os.path.dirname(__file__)`)
- **Dynamic state icons** (optional): icon changes based on voice state (idle = mic, listening = green mic, speaking = blue mic with waves)
- **Menu:**
  - `Show Overlay` — toggles the HUD visible (checkmarked when visible)
  - `Open Dashboard` — opens `http://localhost:3000` in default browser via `QDesktopServices.openUrl`
  - `---` (separator)
  - `Quit` — calls `QApplication.quit()` with proper cleanup (hides tray icon first, then quits)
- **Tooltip:** "Agentium Voice" — state-aware via `setToolTip()` updates on each voice_state event: "Listening...", "Speaking...", "Idle"
- **Click behavior:** Left-click (`Trigger`) toggles overlay; right-click (`Context`) opens menu (platform standard)
- **Cleanup:** `QApplication.setQuitOnLastWindowClosed(False)` so the app stays alive when windows are hidden

## Communication Flow

```
voice-bridge/main.py (existing)        Bridge UI (new)
  │                                       │
  │  WS :9999                             │  QSystemTrayIcon
  │  broadcasts:                          │    ├── Show Overlay (toggle)
  │  - {"type":"voice_state",             │    ├── Open Dashboard
  │     "state":"listening"}              │    └── Quit
  │  - {"type":"voice_state",             │
  │     "state":"speaking"}               │  QML Overlay (frameless, transparent)
  │  - {"type":"voice_state",             │    ├── CircularWaveform
  │     "state":"interrupted"}            │    │   └── bars from QAudioSource RMS
  │  - {"type":"voice_state",             │    └── SpeakingIndicator
  │     "state":"idle"}                   │        └── bars from synthetic anim
  │                                       │
  │                                       │  BridgeClient (QWebSocket)
  │                                       │    └── emits: voice_state_changed
  │                                       │    └── auto-reconnect with backoff
  │                                       │
  │                                       │  MicLevelCapture (QAudioSource)
  │                                       │    └── emits: mic_level(float)
  │                                       │    └── 16kHz/16-bit mono, RMS only
  └──── WebSocket ────────────────────────┘
```

The Bridge UI is a **passive observer** for state. The voice bridge's `_ws_handler` already broadcasts all voice state events to connected clients, so the UI works without any changes to the bridge. Audio level capture is independent.

## Project File Layout

```
voice-bridge/
├── ui/
│   ├── __init__.py
│   ├── main.py                  # QApplication entry point, tray setup
│   ├── bridge_client.py         # QWebSocket client with auto-reconnect
│   ├── overlay_manager.py       # Show/hide logic, auto-hide timer
│   ├── mic_level.py             # QAudioSource RMS capture, emits mic_level
│   ├── qml/
│   │   ├── WaveformOverlay.qml  # Main circular HUD component
│   │   └── SpeakingIndicator.qml # Bottom-right pill component
│   └── assets/
│       ├── tray_idle.png        # Agentium blue mic icon (idle)
│       ├── tray_listening.png   # Green mic icon (listening)
│       └── tray_speaking.png    # Blue mic with waves (speaking)
├── requirements-ui.txt          # PySide6, pyside-native-glass, etc.
└── README.md                    # New: voice bridge docs including UI
```

## Technology Stack

| Component | Technology | Why |
|-----------|------------|-----|
| GUI Framework | PySide6 (Qt 6) | Cross-platform, native look, QML support, LGPL license |
| UI Language | QML / Qt Quick | Hardware-accelerated animations, Canvas 2D for waveform |
| System Tray | QSystemTrayIcon | Native platform tray, built into Qt |
| WebSocket | QWebSocket | Qt-native async WS, no extra deps |
| Audio capture | QAudioSource (QtMultimedia) | Non-blocking RMS amplitude reading, coexists with PyAudio |
| Audio visualization | QML Canvas 2D | Custom circular bar rendering with requestAnimationFrame at 60fps |
| Glassmorphism | pyside-native-glass + QML MultiEffect fallback | Native DWM Acrylic on Win11, NSVisualEffectView on macOS, blur on Linux |

## Color Palette (Agentium Design Tokens)

| Token | Role | Value |
|-------|------|-------|
| `--c-canvas` | Overlay background | `rgba(15, 17, 23, 0.80)` |
| `--c-panel` | Glass panel bg | `rgba(22, 27, 39, 0.85)` |
| `--c-brand` | Bars, glow, accent | `#3b82f6` |
| `--c-brand-soft` | Subtle glow layer | `rgba(59, 130, 246, 0.12)` |
| `--c-hairline` | Pill border | `rgba(30, 37, 53, 0.5)` |
| — | Text primary | `#ffffff` |
| — | Text secondary | `#9ca3af` |

Font: Inter (system fallback: sans-serif)

## Platform-Specific Behavior

| Feature | Windows | macOS | Linux |
|---------|---------|-------|-------|
| Glassmorphism | DWM Acrylic via `SetWindowCompositionAttribute` | NSVisualEffectView via pyside-native-glass | QML MultiEffect GaussianBlur fallback |
| System tray | Native notification area | Menu bar icon | StatusNotifierItem / XEmbed |
| Left-click tray | Toggles overlay | Toggles overlay | Toggles overlay |
| Overlay click-through | `WA_TransparentForMouseEvents` | `WA_TransparentForMouseEvents` | `WA_TransparentForMouseEvents` |
| HiDPI | Automatic via `QT_ENABLE_HIGHDPI_SCALING` | Automatic via `NSHighResolutionCapable` | Automatic via `QT_SCREEN_SCALE_FACTORS` |

## Implementation Order

Will be detailed in the follow-up writing-plans step. High-level order:

1. Scaffold: `main.py`, `bridge_client.py`, `overlay_manager.py`, `mic_level.py`
2. QML: `WaveformOverlay.qml` — circular bar rendering on Canvas 2D, states, animations
3. QML: `SpeakingIndicator.qml` — bottom-right pill, synthetic equalizer bars
4. System tray: multi-resolution icon, context menu, left-click toggle, dynamic tooltip
5. mic_level.py: QAudioSource RMS capture, 30Hz feed into QML
6. Integration: wire BridgeClient voice_state events + MicLevelCapture → overlay show/hide
7. Glassmorphism: apply pyside-native-glass / DWM Acrylic / QML MultiEffect fallback
8. Click-through: `WA_TransparentForMouseEvents` on overlay windows
9. `requirements-ui.txt` and `README.md` update
10. Packaging: PyInstaller for single EXE distribution (Windows)

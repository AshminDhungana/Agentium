# Voice Bridge UI Redesign — Design Spec

**Date:** 2026-07-21
**Status:** Approved
**Approach:** C — Hybrid (Redesigned HUD + Polished Widgets + Voice Mode Panel)

## 1. Design System & Color Tokens

Cyberpunk-futuristic aesthetic built on Agentium's existing dashboard tokens.

### Core tokens (existing, unchanged)

| Token | Dark | Light |
|-------|------|-------|
| `--c-canvas` | `#0f1117` | `#f9fafb` |
| `--c-panel` | `#161b27` | `#ffffff` |
| `--c-panel-2` | `#1c2333` | `#f8fafc` |
| `--c-hairline` | `#1e2535` | `#e5e7eb` |
| `--c-brand` | `#3b82f6` | `#2563eb` |
| `--c-brand-soft` | `rgba(59,130,246,0.12)` | `#dbeafe` |

### Voice-specific tokens (new)

| Token | Dark | Light | Usage |
|-------|------|-------|-------|
| `--c-voice-listening` | `#3b82f6` | `#2563eb` | Mic glow, orb listening |
| `--c-voice-speaking` | `#10b981` | `#059669` | Orb speaking, indicator |
| `--c-voice-thinking` | `#8b5cf6` | `#7c3aed` | Orb processing state |
| `--c-voice-error` | `#ef4444` | `#dc2626` | Error glow, dot |
| `--c-voice-glow` | `rgba(59,130,246,0.3)` | `rgba(37,99,235,0.2)` | Outer halo |
| `--c-glass-bg` | `rgba(22,27,39,0.85)` | `rgba(255,255,255,0.85)` | Glass surfaces |
| `--c-glass-border` | `rgba(59,130,246,0.15)` | `rgba(37,99,235,0.12)` | Glass borders |

### State → color mapping

| Voice State | Orb Color | Badge Color |
|-------------|-----------|-------------|
| `idle` | `--c-brand` subtle pulse | `--c-hairline` |
| `listening` | `--c-voice-listening` animated | `--c-voice-listening` |
| `thinking` | `--c-voice-thinking` pulsing | `--c-voice-thinking` |
| `speaking` | `--c-voice-speaking` animated | `--c-voice-speaking` |
| `interrupted` | Crossfade speaking → listening (200ms) | — |
| `error` | `--c-voice-error` shake | `--c-voice-error` |

---

## 2. Desktop HUD (PySide6 + QML)

### 2.1 Voice Orb (replaces WaveformOverlay.qml)

**Size:** 320×320 (was 280×280)
**Window flags:** Frameless, always-on-top, transparent-for-input (unchanged)

**Visuals:**
- Organic blob shape rendered on Canvas using simplex noise deformation (replacing 48-bar circular waveform)
- Gradient fill changes per state:
  - idle: `--c-brand` (subtle, low amplitude)
  - listening: blue→purple gradient `#3b82f6` → `#8b5cf6`
  - thinking: purple pulsing `#8b5cf6`
  - speaking: purple→emerald gradient `#8b5cf6` → `#10b981`
- Outer glow halo: `--c-voice-glow`, animated radius (40→60px pulse)
- Center dot: 16px → 20px, white `#ffffff` with `opacity: 0.9`, inner 8px dot `opacity: 0.4`
- 2 orbital rings (keep existing concept): radius 200/220, rotation speed 15°/10° per frame, opacity 0.08
- State transition animations: `Behavior on opacity{ NumberAnimation 200ms OutCubic }`, scale transitions

**Responsiveness:**
- Blob deformation amplitude driven by `micLevel` property (0.0–1.0)
- Animation runs at ~60fps via 16ms Timer while visible

### 2.2 Speaking Indicator (replace SpeakingIndicator.qml)

**Size:** 160×44 (was 120×36)

**Visuals:**
- Pill-shaped glass background: `--c-glass-bg`, `border-radius: 22`, `border: 1px solid --c-glass-border`
- 5 animated bars (was 3), base height 10px, max height 24px, animated with `Math.sin`
- State label: `"Listening..."` / `"Thinking..."` / `"Speaking..."` in 11px semibold (system font)
- Capsule status dot: right-aligned, 10px, colored per state mapping

**Position:** Bottom-right, 20px inset from screen edges (unchanged)

### 2.3 Transcript Overlay (new)

**Size:** 400×70
**Position:** Centered below the orb, 20px below orb bottom edge

**Visuals:**
- Glass background (`--c-glass-bg`), rounded 12px, 1px `--c-glass-border`
- 2 lines of text:
  - **User STT**: `"You: {live transcript}"` in 12px, `--c-voice-listening`
  - **AI TTS**: `"Agentium: {last TTS text}"` in 12px, `--c-voice-speaking`
- Auto-hides after 3 seconds of no new text
- Fade in/out via `opacity` animation

### 2.4 System Tray Icons (new assets)

Replace single-color SVGs with multi-state icons:

- **idle:** `tray_idle.svg` — mic icon, `--c-brand` fill, subtle glow
- **listening:** `tray_listening.svg` — mic with sound wave arcs, `--c-voice-listening`
- **speaking:** `tray_speaking.svg` — mic with bars, `--c-voice-speaking`
- **error:** `tray_error.svg` — mic with exclamation, `--c-voice-error`

All icons: 24×24px, exported as optimized SVGs embedded in `voice-bridge/ui/assets/`.

### 2.5 Overlay Manager changes (overlay_manager.py)

- Add `transcript_view` QQuickView for the new transcript overlay window
- Wire `on_mic_level` to orb deformation property (already exists)
- Add `on_transcript(text, role)` slot that receives STT/TTS text from the bridge
- Auto-hide timer for transcript overlay (3s after last update)
- State transitions unchanged (show_overlay → hide_overlay → show_indicator flow)

---

## 3. Frontend — VoiceIndicator

### 3.1 Component redesign

**Current:** Simple mic icon with text label + top bar position.
**New:** Animated state ring button with hover-expand dropdown.

**Button states:**

| State | Visual | Tooltip |
|-------|--------|---------|
| `offline` | Subtle border, static `MicOff` icon | "Voice offline" |
| `connecting` | Rotating dashed ring, spinner | "Connecting…" |
| `connected` | Pulsing emerald ring (`--c-voice-speaking`), active glow | "Voice ready" |
| `listening` | Blue animated pulse ring (`--c-voice-listening`), wave arcs | "Listening…" |
| `speaking` | Emerald ring, bars | "Speaking…" |
| `error` | Red ring, shake animation, exclamation badge | "Voice error" |

**Size:** 36×36px button, ring is CSS `::before` pseudo-element with `border` + `animation`.

**Hover dropdown:**
- Connection status line with colored dot
- Quick toggle: Enable / Disable (styled toggle switch)
- "Open Voice Mode" button (opens Voice Mode Panel)
- Keyboard shortcut hint: `Ctrl+Shift+V`

### 3.2 Install Notification (redesigned)

**Current:** `createPortal` fixed bottom-left card.
**New:** Inline card inside the VoiceIndicator dropdown (not a portal).

- Appears as first item in dropdown when bridge is unreachable
- Shows OS name, single command with copy button
- Compact: command + copy icon only, no verbose captions
- "Dismiss" link at bottom of dropdown

---

## 4. Frontend — VoiceSettingsModal

### 4.1 Layout

**Size:** `max-w-2xl` (was `max-w-lg`), 3 vertical tabs in left sidebar + content area.

**Navigation:**
- Left sidebar: 3 tab buttons with lucide icons
  - Engine — `Settings2` icon
  - Speaker Profiles — `Mic` icon
  - Advanced — `SlidersHorizontal` icon
- Active tab: `--c-brand` left border indicator, subtle background
- Smooth slide transition between tabs (200ms, ease)

### 4.2 Engine Tab

- **Wake Word** — Toggle switch (styled), label "Require wake word ('Agentium')"
- **TTS Voice** — Dropdown with sample list + ▶ Play button next to each voice
- **Proactive Announcements** — Toggle switch with helper text
- **Speaker Identification** — Toggle switch with helper text
- **Save** button: primary styled, shows toast on success, "Undo" toast action for 5s

### 4.3 Speaker Profiles Tab

**Enrollment card:**
- Speaker name input (text field, pre-styled)
- Record button: circular with red recording dot animation, shows timer `00:00`
- Live waveform visualization during recording (canvas-based, same style as orb)
- Processing spinner during upload

**Enrolled list:**
- Avatar circle: 40px, colored background based on name hash, shows initials
- Speaker name + "Enrolled: {date}"
- Delete button (trash icon, red on hover)
- Empty state: dashed border card with "No speaker profiles enrolled yet."

### 4.4 Advanced Tab

- **Input Mode:** Push-to-talk vs Always-on (radio group)
- **STT Language:** Language selector dropdown
- **Mic Sensitivity:** Range slider 0–100, visual level indicator
- **Noise Suppression:** Toggle switch
- **Reduced Motion:** Toggle switch (disables orb/indicator animations)

---

## 5. Frontend — Voice Mode Panel (New)

### 5.1 Layout

Semi-modal overlay that covers the chat area (not the full browser viewport):

```
┌─────────────────────────────────────────┐
│  Chat Header (visible, dimmed behind)   │
│                                         │
│  ┌─────────────────────────────────┐    │
│  │     [✕ End Session]  [PTT/AON] │    │
│  │                                 │    │
│  │          ┌───────┐             │    │
│  │          │  Orb  │             │    │
│  │          │320×320│             │    │
│  │          └───────┘             │    │
│  │                                 │    │
│  │  "You: what's the weather..."  │    │ ← STT transcript
│  │  "Agentium: It's 72°F..."     │    │ ← TTS transcript
│  │                                 │    │
│  │     [🎙] [🔇] [End Session]   │    │ ← bottom controls
│  └─────────────────────────────────┘    │
│                                         │
│  Chat Messages (visible, dimmed)        │
└─────────────────────────────────────────┘
```

### 5.2 Orb (Browser-based)

- HTML5 Canvas rendering with simplex noise deformation (matching QML orb visual language)
- Same color mapping per state (section 1)
- State managed by `voiceBridgeService.onStateChange()` subscription
- Falls back to CSS-only animated circle when `prefers-reduced-motion` is set

### 5.3 Transcript Area

- 2 lines max per role (user + AI)
- Auto-scroll, latest on bottom
- Fade-in for new lines (200ms)
- Color-coded: user text in `--c-voice-listening`, AI text in `--c-voice-speaking`

### 5.4 Bottom Controls

- **Mic button:** Same animated ring as VoiceIndicator, 48×48px, centered
- **Mute toggle:** Icon button, crosses out mic icon, toggles local mic gating
- **End Session:** `✕` button, top-right corner, fades out panel + saves transcript to chat history
- **Mode toggle:** Push-to-talk / Always-on, top-right next to end button

### 5.5 States & Transitions

| Transition | Orb | Transcript | Duration |
|------------|-----|------------|----------|
| idle → listening | Blue gradient, amplitude reacts to mic | "Listening…" shown | instant |
| listening → thinking | Purple pulse, amplitude flat | Shows last STT text | 300ms |
| thinking → speaking | Emerald gradient, amplitude reacts to TTS audio | Shows TTS text streaming | 300ms |
| speaking → listening (barge-in) | Crossfade emerald → blue | Shows new STT text | 200ms |
| any → idle | Fade to subtle pulse | Clears after 3s | 400ms |
| panel close | Scale down + fade out | Transcript saved to history | 250ms |

### 5.6 Keyboard Shortcuts

- `Ctrl+Shift+V` — Toggle voice mode panel
- `Space` (hold) — Push-to-talk
- `Escape` — End session / close panel
- `Ctrl+M` — Mute toggle

---

## 6. Data Flow & Synchronization

### 6.1 Desktop HUD ← Bridge

- `bridge_client.py` already receives `voice_state` WS messages
- **New:** `transcript` message: `{"type": "transcript", "role": "user"|"agent", "text": "..."}`
- `voice_bridge/main.py` `_broadcast()` sends transcript updates alongside state
- OverlayManager receives transcript via new `on_transcript(text, role)` signal

### 6.2 Frontend ← Bridge

- `voiceBridgeService` already receives `voice_interaction` and `voice_state` events
- **New:** `voiceBridgeService` forwards `voice_state` to Voice Mode Panel via `onStateChange()`
- **New:** `voiceBridgeService` forwards transcript text via `onTranscript(text, role)` — new subscription API
- ChatPage still receives `voice_interaction` for chat history

### 6.3 Frontend → Bridge (Host Token)

- `voiceBridgeService._pushHostToken()` — already implemented, unchanged
- Voice Mode Panel also sends `set_token` if bridge reconnects while panel is open

---

## 7. Files Changed / Created

### Desktop HUD (voice-bridge/)

| File | Action | Notes |
|------|--------|-------|
| `ui/qml/WaveformOverlay.qml` | **Rewrite** | Replace bar waveform with organic orb |
| `ui/qml/SpeakingIndicator.qml` | **Rewrite** | Larger pill, 5 bars, state label |
| `ui/qml/TranscriptOverlay.qml` | **Create** | New window for live STT/TTS text |
| `ui/overlay_manager.py` | **Modify** | Add transcript view wiring, new signals |
| `ui/assets/tray_idle.svg` | **Replace** | Redesigned with brand color |
| `ui/assets/tray_listening.svg` | **Replace** | Blue mic + waves |
| `ui/assets/tray_speaking.svg` | **Replace** | Green mic + bars |
| `ui/assets/tray_error.svg` | **Create** | Red mic + exclamation |
| `ui/generate_icons.py` | **Modify** | Add new icon generation |
| `main.py` | **Modify** | Send `transcript` WS messages |

### Frontend (frontend/src/)

| File | Action | Notes |
|------|--------|-------|
| `components/VoiceIndicator.tsx` | **Rewrite** | Animated state ring, hover dropdown |
| `components/VoiceSettingsModal.tsx` | **Rewrite** | Tab layout, redesign all sections |
| `components/VoiceModePanel.tsx` | **Create** | New voice mode panel component |
| `components/VoiceOrb.tsx` | **Create** | Canvas-based organic orb component |
| `services/voiceBridge.ts` | **Modify** | Add `onTranscript()` subscription |
| `services/voiceApi.ts` | **Modify** | Add voice sample preview endpoint |
| `pages/ChatPage.tsx` | **Modify** | Integrate VoiceModePanel opening |

---

## 8. Out of Scope

- Redesigning the bridge backend (`main.py` voice session logic, STT/TTS pipeline) — purely visual/UX
- Adding new voice features (multi-language STT, custom wake words, voice cloning) — config only
- Mobile-responsive voice mode panel — desktop-first, mobile follows
- Linux compositor-specific blur effects — maintain current fallback behavior
- Unit/e2e tests for new components — covered in implementation plan

---

## 9. Future Considerations

- **Browser orb rendering:** Canvas2D is the initial target; WebGL path can be added if performance profiling shows dropped frames on integrated GPUs.
- **Mobile voice mode panel:** Full-screen bottom sheet with swipe-to-dismiss — deferred from this pass.
- **Transcript persistence:** Voice exchanges already write to chat history via `voice_interaction` events; transcript overlay is ephemeral by design.

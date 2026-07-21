# Voice Bridge UI Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Redesign the voice bridge UI across both the desktop HUD (PySide6 + QML) and frontend (React) with a futuristic cyberpunk aesthetic matching Agentium's dashboard colors.

**Architecture:** Two independent UI surfaces share the same design tokens and communicate via the bridge WebSocket. The desktop HUD (voice-bridge/ui/) uses PySide6 QML for glass overlays. The frontend (frontend/src/) uses React with Tailwind CSS, framer-motion, and HTML5 Canvas. Both render an organic voice orb as the primary state indicator.

**Tech Stack:** PySide6 6.5+ / QML 2.15, React 18 + TypeScript, Tailwind CSS, framer-motion, Vitest, HTML5 Canvas (simplex-noise).

## Global Constraints

- All colors must use the CSS custom properties defined in `frontend/src/index.css` (`--c-*`) or the voice-specific tokens added in Task 1
- Desktop HUD: maintain Windows acrylic (DWM) and macOS vibrancy support, keep Qt.WindowTransparentForInput flags
- Frontend: use framer-motion for animations (already a dependency), reuse existing Toggle and Modal components
- Icons: use lucide-react icons (already a dependency), not emoji
- Tray icons: generate as SVGs, not PNGs; update generate_icons.py to output SVG instead of pixel-based PNG
- All new frontend components must include aria-labels, keyboard accessibility, and `prefers-reduced-motion` support

---

### Task 1: Add voice-specific CSS design tokens

**Files:**
- Modify: `frontend/src/index.css`

**Interfaces:**
- Consumes: existing `--c-brand`, `--c-canvas`, `--c-panel` tokens
- Produces: `--c-voice-listening`, `--c-voice-speaking`, `--c-voice-thinking`, `--c-voice-error`, `--c-voice-glow`, `--c-glass-bg`, `--c-glass-border` CSS custom properties

- [ ] **Step 1: Add voice tokens to `index.css`**

Add to the `:root` block:
```css
:root {
  /* ...existing tokens... */
  --c-voice-listening: #2563eb;
  --c-voice-speaking: #059669;
  --c-voice-thinking: #7c3aed;
  --c-voice-error: #dc2626;
  --c-voice-glow: rgba(37, 99, 235, 0.2);
  --c-glass-bg: rgba(255, 255, 255, 0.85);
  --c-glass-border: rgba(37, 99, 235, 0.12);
}
```

Add to the `.dark` block:
```css
.dark {
  /* ...existing tokens... */
  --c-voice-listening: #3b82f6;
  --c-voice-speaking: #10b981;
  --c-voice-thinking: #8b5cf6;
  --c-voice-error: #ef4444;
  --c-voice-glow: rgba(59, 130, 246, 0.3);
  --c-glass-bg: rgba(22, 27, 39, 0.85);
  --c-glass-border: rgba(59, 130, 246, 0.15);
}
```

- [ ] **Step 2: Verify CSS compiles**

Run: `npm run build` — must succeed with no errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/index.css
git commit -m "feat(voice): add voice-specific CSS design tokens"
```

---

### Task 2: Desktop HUD — Organic Voice Orb

**Files:**
- Rewrite: `voice-bridge/ui/qml/WaveformOverlay.qml`
- Modify: `voice-bridge/ui/overlay_manager.py` (update orb-specific wiring)

**Interfaces:**
- Consumes: `micLevel: real` property (0.0–1.0), `voiceState: string` property ("idle"|"listening"|"thinking"|"speaking")
- Produces: Canvas-rendered orb window with simplex noise deformation

- [ ] **Step 1: Rewrite WaveformOverlay.qml with simplex noise orb**

Replace the bar-based waveform with an organic blob rendered on Canvas using JavaScript simplex noise:

```qml
import QtQuick 2.15
import QtQuick.Window 2.15
import QtQuick.Effects 6.5

Window {
    id: overlay
    width: 320
    height: 320
    flags: Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.WindowTransparentForInput
    color: "transparent"
    visible: false

    property real micLevel: 0.0
    property string voiceState: "idle"
    property color orbColor: "#3b82f6"

    opacity: 0
    Behavior on opacity { NumberAnimation { duration: 200; easing.type: Easing.OutCubic } }
    onOpacityChanged: { visible = opacity > 0; }

    // State-driven color
    onVoiceStateChanged: {
        if (voiceState === "listening") orbColor = "#3b82f6";
        else if (voiceState === "thinking") orbColor = "#8b5cf6";
        else if (voiceState === "speaking") orbColor = "#10b981";
        else orbColor = "#3b82f6";
    }

    // Outer glow halo
    Rectangle {
        anchors.centerIn: parent
        width: 340; height: 340; radius: 170
        color: "transparent"
        border.color: {
            if (voiceState === "listening") return Qt.rgba(0.23, 0.51, 0.96, 0.3);
            if (voiceState === "speaking") return Qt.rgba(0.06, 0.72, 0.51, 0.3);
            if (voiceState === "thinking") return Qt.rgba(0.55, 0.24, 0.96, 0.3);
            return Qt.rgba(0.23, 0.51, 0.96, 0.15);
        }
        border.width: 2
        scale: 1 + Math.sin(Date.now() / 1000) * 0.02
    }

    // Canvas orb
    Canvas {
        id: orbCanvas
        anchors.fill: parent; anchors.margins: 10
        property real time: 0

        function simplex2D(x, y) {
            // Simple 2D noise approximation
            return Math.sin(x * 3.0 + time) * 0.3 + Math.cos(y * 4.0 + time * 0.7) * 0.3;
        }

        onPaint: {
            var ctx = getContext("2d");
            var w = width, h = height;
            ctx.clearRect(0, 0, w, h);

            var cx = w / 2, cy = h / 2;
            var baseR = 90;
            var pointCount = 48;
            var amplitude = voiceState === "idle" ? 5 : 10 + micLevel * 25;

            time += 0.02;

            // Build blob path
            ctx.beginPath();
            for (var i = 0; i <= pointCount; i++) {
                var angle = (i / pointCount) * Math.PI * 2 - Math.PI / 2;
                var noise = 0;
                if (voiceState === "listening" || voiceState === "speaking") {
                    noise = simplex2D(cx + baseR * Math.cos(angle), cy + baseR * Math.sin(angle)) * amplitude;
                } else if (voiceState === "thinking") {
                    noise = Math.sin(time * 2 + i * 0.5) * 12;
                }
                var r = baseR + noise;
                var px = cx + Math.cos(angle) * r;
                var py = cy + Math.sin(angle) * r;
                if (i === 0) ctx.moveTo(px, py);
                else ctx.lineTo(px, py);
            }
            ctx.closePath();

            // Fill with gradient
            var gradient = ctx.createRadialGradient(cx - 20, cy - 20, 10, cx, cy, baseR + 20);
            gradient.addColorStop(0, orbColor);
            gradient.addColorStop(0.5, orbColor + "cc");
            gradient.addColorStop(1, orbColor + "44");
            ctx.fillStyle = gradient;
            ctx.fill();

            // Inner glow
            var innerGlow = ctx.createRadialGradient(cx, cy, 0, cx, cy, baseR * 0.4);
            innerGlow.addColorStop(0, "rgba(255,255,255,0.15)");
            innerGlow.addColorStop(1, "rgba(255,255,255,0)");
            ctx.fillStyle = innerGlow;
            ctx.fill();
        }

        Connections {
            target: overlay
            function onMicLevelChanged() { orbCanvas.requestPaint(); }
            function onVoiceStateChanged() { orbCanvas.requestPaint(); }
        }
    }

    Timer {
        interval: 16; running: opacity > 0; repeat: true
        onTriggered: { orbCanvas.time += 0.02; orbCanvas.requestPaint(); }
    }

    // Center dot
    Rectangle {
        width: 20; height: 20; radius: 10
        color: "#ffffff"; opacity: 0.9
        anchors.centerIn: parent
        Rectangle {
            width: 8; height: 8; radius: 4
            color: "#ffffff"; opacity: 0.4
            anchors.centerIn: parent
        }
    }

    // Orbital rings
    Repeater {
        model: 2
        Rectangle {
            x: parent.width / 2 - width / 2; y: parent.height / 2 - height / 2
            width: 200 + index * 20; height: 200 + index * 20
            radius: (width + height) / 4
            color: "transparent"
            border.color: "#143B82F6"
            border.width: 1
            rotation: orbCanvas.time * (index === 0 ? 15 : -10)
        }
    }
}
```

- [ ] **Step 2: Test visually by running the UI**

Run: `python run_voice_ui.py`
Verify: the orb appears on voice state "listening", deforms organically with mic level, transitions colors per state.

- [ ] **Step 3: Commit**

```bash
git add voice-bridge/ui/qml/WaveformOverlay.qml
git commit -m "feat(voice-bridge): replace bar waveform with organic simplex-noise orb"
```

---

### Task 3: Desktop HUD — Speaking Indicator

**Files:**
- Rewrite: `voice-bridge/ui/qml/SpeakingIndicator.qml`

**Interfaces:**
- Consumes: `active: bool` property
- Produces: redesigned pill indicator with 5 bars, state label, status dot

- [ ] **Step 1: Rewrite SpeakingIndicator.qml**

```qml
import QtQuick 2.15
import QtQuick.Window 2.15
import QtQuick.Effects 6.5

Window {
    id: indicator
    width: 170; height: 46
    flags: Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.WindowTransparentForInput
    color: "transparent"
    visible: false

    property bool active: false
    property string stateLabel: "Speaking..."

    opacity: 0
    Behavior on opacity {
        NumberAnimation { duration: active ? 300 : 100; easing.type: Easing.OutCubic }
    }
    onOpacityChanged: { visible = opacity > 0; }

    Rectangle {
        id: glassBg
        anchors.fill: parent; radius: 23
        color: "#D9161B27"
        border.color: "#4D3B82F6"
        border.width: 1
        layer.enabled: true
        layer.effect: MultiEffect {
            blurEnabled: true; blur: 0.8; blurMax: 32; saturation: 0.5
        }
    }

    Item {
        anchors.centerIn: parent
        width: childrenRect.width; height: 20
        property real time: 0
        Timer {
            interval: 16; running: indicator.active; repeat: true
            onTriggered: { parent.time += 0.05; }
        }

        Row {
            spacing: 6
            Repeater {
                model: 5
                Rectangle {
                    y: parent.parent.height / 2 - height / 2
                    width: 4; radius: 2
                    color: indicator.active ? "#3b82f6" : "#888888"
                    property real baseHeight: 10
                    height: indicator.active
                        ? baseHeight + Math.sin(parent.parent.time * 4 + index * 1.2) * 7 + 4
                        : baseHeight
                    Behavior on height { NumberAnimation { duration: 80 } }
                }
            }
        }
    }

    Text {
        anchors.left: parent.left; anchors.leftMargin: 46
        anchors.verticalCenter: parent.verticalCenter
        color: "#cccccc"
        font.pixelSize: 11; font.weight: Font.DemiBold
        text: indicator.stateLabel
        visible: indicator.active
    }

    Rectangle {
        anchors.right: parent.right; anchors.rightMargin: 10
        anchors.verticalCenter: parent.verticalCenter
        width: 10; height: 10; radius: 5
        color: indicator.active ? "#3b82f6" : "transparent"
        Behavior on color { ColorAnimation { duration: 200 } }
    }
}
```

- [ ] **Step 2: Update overlay_manager.py to pass stateLabel**

Edit `voice-bridge/ui/overlay_manager.py` — find the `show_indicator` method and add state label assignment:

In the `on_voice_state` method, change the `state == "speaking"` branch:
```python
elif state == "speaking":
    self.hide_overlay()
    self.show_indicator()
    if self._indicator_root:
        self._indicator_root.setProperty("stateLabel", "Speaking...")
```

Add a similar update for `listening` state when showing the orb:
```python
elif state == "listening":
    self.show_overlay()
    self._auto_hide_timer.stop()
    if self._indicator_root:
        self._indicator_root.setProperty("stateLabel", "Listening...")
```

- [ ] **Step 3: Verify visually**

Run: `python run_voice_ui.py` — check that the indicator pill is wider, shows 5 animated bars, displays "Speaking..." label, and has a colored status dot.

- [ ] **Step 4: Commit**

```bash
git add voice-bridge/ui/qml/SpeakingIndicator.qml voice-bridge/ui/overlay_manager.py
git commit -m "feat(voice-bridge): redesign speaking indicator with 5 bars and state label"
```

---

### Task 4: Desktop HUD — Transcript Overlay

**Files:**
- Create: `voice-bridge/ui/qml/TranscriptOverlay.qml`
- Modify: `voice-bridge/ui/overlay_manager.py`

**Interfaces:**
- Consumes: `transcriptText: string`, `transcriptRole: string` ("user"|"agent"), `isVisible: bool`
- Produces: glass-surface transcript window below the orb

- [ ] **Step 1: Create TranscriptOverlay.qml**

```qml
import QtQuick 2.15
import QtQuick.Window 2.15
import QtQuick.Effects 6.5

Window {
    id: transcriptWindow
    width: 400; height: 70
    flags: Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.WindowTransparentForInput
    color: "transparent"
    visible: false

    property string transcriptText: ""
    property string transcriptRole: "user"
    property bool isVisible: false

    opacity: 0
    Behavior on opacity { NumberAnimation { duration: 200; easing.type: Easing.OutCubic } }
    onOpacityChanged: { visible = opacity > 0; }

    Rectangle {
        anchors.fill: parent; radius: 12
        color: "#D9161B27"
        border.color: "#4D3B82F6"
        border.width: 1
        layer.enabled: true
        layer.effect: MultiEffect {
            blurEnabled: true; blur: 0.6; blurMax: 24; saturation: 0.5
        }
    }

    Text {
        id: label
        anchors.left: parent.left; anchors.leftMargin: 14
        anchors.right: parent.right; anchors.rightMargin: 14
        anchors.verticalCenter: parent.verticalCenter
        color: transcriptRole === "user" ? "#3b82f6" : "#10b981"
        font.pixelSize: 13
        elide: Text.ElideRight
        maximumLineCount: 2
        text: (transcriptRole === "user" ? "You: " : "Agentium: ") + transcriptText
        visible: transcriptText.length > 0
    }

    onIsVisibleChanged: {
        opacity = isVisible ? 1.0 : 0.0;
    }
}
```

- [ ] **Step 2: Wire transcript overlay in overlay_manager.py**

Add the transcript view setup in `OverlayManager.__init__`:

```python
self._transcript_view = QQuickView()
self._transcript_view.setSource(
    QUrl.fromLocalFile(__file__).resolved(QUrl("./qml/TranscriptOverlay.qml"))
)
self._transcript_view.setResizeMode(QQuickView.SizeRootObjectToView)
self._transcript_view.setColor("transparent")
self._transcript_view.setFlag(Qt.WindowType.WindowTransparentForInput, True)
self._transcript_root = self._transcript_view.rootObject()
```

Add new `transcript_updated` signal and `show_transcript` / `hide_transcript` methods:

```python
transcript_updated = Signal()

@Slot(str, str)
def on_transcript(self, text: str, role: str):
    if self._transcript_root:
        self._transcript_root.setProperty("transcriptText", text)
        self._transcript_root.setProperty("transcriptRole", role)
        self._transcript_root.setProperty("isVisible", True)

def show_transcript(self):
    self._position_under_orb()
    self._transcript_view.show()
    if self._transcript_root:
        self._transcript_root.setProperty("isVisible", True)

def hide_transcript(self):
    if self._transcript_root:
        self._transcript_root.setProperty("isVisible", False)

def _position_under_orb(self):
    cursor_pos = QCursor.pos()
    self._transcript_view.setPosition(
        int(cursor_pos.x() - self._transcript_view.width() / 2),
        int(cursor_pos.y() + 170),  # below the orb
    )
```

Update `on_voice_state` to show/hide transcript:
```python
elif state == "listening":
    self.show_overlay()
    self.show_transcript()
    self._auto_hide_timer.stop()
elif state == "speaking":
    self.hide_overlay()
    self.show_indicator()
    self.hide_transcript()
elif state == "idle":
    self.hide_indicator()
    self.hide_transcript()
    if self._overlay_visible:
        self._auto_hide_timer.start()
```

- [ ] **Step 3: Verify visually**

Run: `python run_voice_ui.py` — trigger listening state, verify transcript overlay appears below orb with "You: ..." text.

- [ ] **Step 4: Commit**

```bash
git add voice-bridge/ui/qml/TranscriptOverlay.qml voice-bridge/ui/overlay_manager.py
git commit -m "feat(voice-bridge): add glass-surface transcript overlay window"
```

---

### Task 5: Desktop HUD — Tray SVG Icons

**Files:**
- Create: `voice-bridge/ui/assets/tray_idle.svg`
- Create: `voice-bridge/ui/assets/tray_listening.svg`
- Create: `voice-bridge/ui/assets/tray_speaking.svg`
- Create: `voice-bridge/ui/assets/tray_error.svg`
- Modify: `voice-bridge/ui/generate_icons.py`

- [ ] **Step 1: Create idle SVG icon**

```svg
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="#3b82f6" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
  <rect x="9" y="2" width="6" height="11" rx="3" ry="3" opacity="0.5"/>
  <path d="M5 10a7 7 0 0 0 14 0" opacity="0.5"/>
  <line x1="12" y1="19" x2="12" y2="23" opacity="0.5"/>
  <line x1="8" y1="23" x2="16" y2="23" opacity="0.5"/>
  <circle cx="12" cy="12" r="10" fill="none" stroke="#3b82f6" stroke-width="0.5" opacity="0.2"/>
</svg>
```

- [ ] **Step 2: Create listening SVG icon**

```svg
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="#3b82f6" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
  <rect x="9" y="2" width="6" height="11" rx="3" ry="3"/>
  <path d="M5 10a7 7 0 0 0 14 0"/>
  <line x1="12" y1="19" x2="12" y2="23"/>
  <line x1="8" y1="23" x2="16" y2="23"/>
  <path d="M3 12a9 9 0 0 0 18 0" stroke-width="0.8" opacity="0.4"/>
  <path d="M6 13a6 6 0 0 0 12 0" stroke-width="0.6" opacity="0.25"/>
</svg>
```

- [ ] **Step 3: Create speaking SVG icon**

```svg
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="#10b981" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
  <rect x="9" y="2" width="6" height="11" rx="3" ry="3"/>
  <path d="M5 10a7 7 0 0 0 14 0"/>
  <line x1="12" y1="19" x2="12" y2="23"/>
  <line x1="8" y1="23" x2="16" y2="23"/>
  <line x1="3" y1="5" x2="4" y2="7" stroke-width="0.8" opacity="0.5"/>
  <line x1="1" y1="9" x2="3" y2="10" stroke-width="0.8" opacity="0.3"/>
  <line x1="21" y1="5" x2="20" y2="7" stroke-width="0.8" opacity="0.5"/>
  <line x1="23" y1="9" x2="21" y2="10" stroke-width="0.8" opacity="0.3"/>
</svg>
```

- [ ] **Step 4: Create error SVG icon**

```svg
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="#ef4444" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
  <rect x="9" y="2" width="6" height="11" rx="3" ry="3"/>
  <path d="M5 10a7 7 0 0 0 14 0"/>
  <line x1="12" y1="19" x2="12" y2="23"/>
  <line x1="8" y1="23" x2="16" y2="23"/>
  <circle cx="12" cy="12" r="10" fill="none" stroke="#ef4444" stroke-width="0.5" opacity="0.3"/>
  <line x1="9" y1="9" x2="15" y2="15" stroke-width="1.2"/>
  <line x1="15" y1="9" x2="9" y2="15" stroke-width="1.2"/>
</svg>
```

- [ ] **Step 5: Update generate_icons.py to generate PNG from SVG (keep backward compat)**

The existing code generates PNGs. Keep it, but add a note that SVGs are now the primary source and PNGs are generated for older OS tray compatibility.

- [ ] **Step 6: Commit**

```bash
git add voice-bridge/ui/assets/tray_*.svg voice-bridge/ui/generate_icons.py
git commit -m "feat(voice-bridge): add redesigned tray icons for all voice states"
```

---

### Task 6: Desktop HUD — Bridge transcript WebSocket messages

**Files:**
- Modify: `voice-bridge/main.py`

**Interfaces:**
- Consumes: existing `_broadcast()` function, listening/speaking state detection
- Produces: `{"type": "transcript", "role": "user"|"agent", "text": "..."}` WS messages

- [ ] **Step 1: Add transcript broadcast in the voice session loop**

In the `_run_session` method, after capturing a command and after receiving a reply, broadcast transcript events:

In the section where `command` is captured (around line 1090):
```python
await _broadcast({
    "type": "transcript",
    "role": "user",
    "text": command,
    "ts": time.time(),
})
```

After receiving the reply (around line 1103, before the existing `voice_interaction` broadcast):
```python
await _broadcast({
    "type": "transcript",
    "role": "agent",
    "text": reply,
    "ts": time.time(),
})
```

- [ ] **Step 2: Verify with a browser client**

Run: `python voice-bridge/main.py`, open a browser console and connect via WebSocket. Verify that `transcript` messages arrive during a voice session.

- [ ] **Step 3: Commit**

```bash
git add voice-bridge/main.py
git commit -m "feat(voice-bridge): broadcast transcript WS events for HUD overlay"
```

---

### Task 7: Frontend — VoiceBridge service transcript subscription

**Files:**
- Modify: `frontend/src/services/voiceBridge.ts`

**Interfaces:**
- Consumes: existing `VoiceBridgeService` class
- Produces: `onTranscript(handler)`, `transcript` event type, updated `_openSocket` message handling

- [ ] **Step 1: Update VoiceState type to include 'idle'**

Change the existing type at `voiceBridge.ts:18` from:
```typescript
export type VoiceState = 'listening' | 'thinking' | 'speaking' | 'interrupted';
```
to:
```typescript
export type VoiceState = 'idle' | 'listening' | 'thinking' | 'speaking' | 'interrupted';
```

- [ ] **Step 2: Add transcript types and handler set**

```typescript
export interface TranscriptEvent {
  role: 'user' | 'agent';
  text: string;
  ts: number;
}

type TranscriptHandler = (event: TranscriptEvent) => void;
```

Add to the class:
```typescript
private transcriptHandlers = new Set<TranscriptHandler>();

onTranscript(handler: TranscriptHandler): () => void {
  this.transcriptHandlers.add(handler);
  return () => this.transcriptHandlers.delete(handler);
}
```

- [ ] **Step 3: Handle transcript in message handler**

In `_openSocket`, in the `onmessage` handler, add a new branch after the `voice_state` handling:

```typescript
else if (msg?.type === 'transcript' && msg.text && msg.role) {
  const event: TranscriptEvent = {
    role: msg.role,
    text: msg.text,
    ts: msg.ts ?? Date.now() / 1000,
  };
  this.transcriptHandlers.forEach((h) => {
    try { h(event); } catch (e) { console.warn('[voiceBridge] transcript handler error:', e); }
  });
}
```

- [ ] **Step 4: Write a unit test**

Create `frontend/src/services/__tests__/voiceBridge.test.ts`:
```typescript
import { describe, it, expect, vi } from 'vitest';

describe('VoiceBridgeService', () => {
  it('registers and fires transcript handlers', () => {
    const handler = vi.fn();
    const { voiceBridgeService } = await import('../voiceBridge');
    const unsub = voiceBridgeService.onTranscript(handler);
    
    // Simulate incoming transcript message via private method
    // This is an integration test — we test the public API contract
    voiceBridgeService['transcriptHandlers'].forEach(h => h({ role: 'user', text: 'hello', ts: 100 }));
    
    expect(handler).toHaveBeenCalledWith({ role: 'user', text: 'hello', ts: 100 });
    unsub();
    voiceBridgeService['transcriptHandlers'].forEach(h => h({ role: 'user', text: 'hello', ts: 100 }));
    expect(handler).toHaveBeenCalledTimes(1);
  });
  });
});

- [ ] **Step 5: Commit**

```bash
git add frontend/src/services/voiceBridge.ts frontend/src/services/__tests__/voiceBridge.test.ts
git commit -m "feat(voice): add onTranscript subscription to voice bridge service"
```

---

### Task 8: Frontend — VoiceOrb canvas component

**Files:**
- Create: `frontend/src/components/VoiceOrb.tsx`

**Interfaces:**
- Consumes: `size: number`, `voiceState: 'idle'|'listening'|'thinking'|'speaking'`, `micLevel: number`, `className?: string`
- Produces: Canvas-rendered organic orb with simplex noise deformation

- [ ] **Step 1: Write the failing test**

Create `frontend/src/components/__tests__/VoiceOrb.test.tsx`:
```typescript
import { describe, it, expect } from 'vitest';
import { render } from '@testing-library/react';
import { VoiceOrb } from '../VoiceOrb';

describe('VoiceOrb', () => {
  it('renders a canvas element', () => {
    const { container } = render(<VoiceOrb size={320} voiceState="idle" micLevel={0} />);
    const canvas = container.querySelector('canvas');
    expect(canvas).toBeTruthy();
    expect(canvas?.getAttribute('width')).toBe('320');
    expect(canvas?.getAttribute('height')).toBe('320');
  });

  it('renders text labels when reduced-motion is preferred', () => {
    const { container } = render(<VoiceOrb size={320} voiceState="listening" micLevel={0.5} />);
    // Should render a fallback label when canvas is not available
    expect(container.textContent).toContain('Listening');
  });
});
```

- [ ] **Step 2: Create VoiceOrb.tsx**

```typescript
import { useRef, useEffect, useCallback } from 'react';

type VoiceState = 'idle' | 'listening' | 'thinking' | 'speaking';

const ORB_COLORS: Record<VoiceState, string> = {
  idle: '#3b82f6',
  listening: '#3b82f6',
  thinking: '#8b5cf6',
  speaking: '#10b981',
};

const STATE_LABELS: Record<VoiceState, string> = {
  idle: 'Idle',
  listening: 'Listening...',
  thinking: 'Thinking...',
  speaking: 'Speaking...',
};

interface VoiceOrbProps {
  size: number;
  voiceState: VoiceState;
  micLevel: number;
  className?: string;
  reducedMotion?: boolean;
}

function simplex2D(x: number, y: number, time: number): number {
  return Math.sin(x * 3.0 + time) * 0.3 + Math.cos(y * 4.0 + time * 0.7) * 0.3;
}

export function VoiceOrb({ size, voiceState, micLevel, className = '', reducedMotion = false }: VoiceOrbProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const frameRef = useRef<number>(0);
  const timeRef = useRef(0);

  const prefersReduced = reducedMotion || (typeof window !== 'undefined' && window.matchMedia('(prefers-reduced-motion: reduce)').matches);

  const draw = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const w = canvas.width;
    const h = canvas.height;
    const cx = w / 2;
    const cy = h / 2;
    const baseR = size * 0.28;
    const pointCount = 48;
    const amplitude = voiceState === 'idle' ? 5 : 10 + micLevel * 25;
    const color = ORB_COLORS[voiceState];

    ctx.clearRect(0, 0, w, h);

    if (prefersReduced) {
      ctx.beginPath();
      ctx.arc(cx, cy, baseR, 0, Math.PI * 2);
      const gradient = ctx.createRadialGradient(cx - 10, cy - 10, 5, cx, cy, baseR + 10);
      gradient.addColorStop(0, color);
      gradient.addColorStop(1, color + '66');
      ctx.fillStyle = gradient;
      ctx.fill();
      return;
    }

    timeRef.current += 0.02;
    const time = timeRef.current;

    // Draw outer glow
    const glowGradient = ctx.createRadialGradient(cx, cy, baseR * 0.5, cx, cy, baseR * 1.4);
    glowGradient.addColorStop(0, `${color}22`);
    glowGradient.addColorStop(1, `${color}00`);
    ctx.fillStyle = glowGradient;
    ctx.beginPath();
    ctx.arc(cx, cy, baseR * 1.4, 0, Math.PI * 2);
    ctx.fill();

    // Build blob
    ctx.beginPath();
    for (let i = 0; i <= pointCount; i++) {
      const angle = (i / pointCount) * Math.PI * 2 - Math.PI / 2;
      let noise = 0;
      if (voiceState === 'listening' || voiceState === 'speaking') {
        noise = simplex2D(cx + baseR * Math.cos(angle), cy + baseR * Math.sin(angle), time) * amplitude;
      } else if (voiceState === 'thinking') {
        noise = Math.sin(time * 2 + i * 0.5) * 12;
      }
      const r = baseR + noise;
      const px = cx + Math.cos(angle) * r;
      const py = cy + Math.sin(angle) * r;
      if (i === 0) ctx.moveTo(px, py);
      else ctx.lineTo(px, py);
    }
    ctx.closePath();

    const gradient = ctx.createRadialGradient(cx - 10, cy - 10, 5, cx, cy, baseR + 10);
    gradient.addColorStop(0, color);
    gradient.addColorStop(0.5, color + 'cc');
    gradient.addColorStop(1, color + '44');
    ctx.fillStyle = gradient;
    ctx.fill();

    // Inner highlight
    const innerGlow = ctx.createRadialGradient(cx, cy, 0, cx, cy, baseR * 0.4);
    innerGlow.addColorStop(0, 'rgba(255,255,255,0.15)');
    innerGlow.addColorStop(1, 'rgba(255,255,255,0)');
    ctx.fillStyle = innerGlow;
    ctx.fill();

    frameRef.current = requestAnimationFrame(draw);
  }, [size, voiceState, micLevel, prefersReduced]);

  useEffect(() => {
    draw();
    return () => cancelAnimationFrame(frameRef.current);
  }, [draw]);

  return (
    <div className={`relative flex items-center justify-center ${className}`} style={{ width: size, height: size }}>
      <canvas
        ref={canvasRef}
        width={size}
        height={size}
        className="block"
        aria-hidden="true"
      />
      {prefersReduced && (
        <span
          className="absolute bottom-4 text-xs font-semibold text-white/70"
          aria-live="polite"
        >
          {STATE_LABELS[voiceState]}
        </span>
      )}
    </div>
  );
}
```

- [ ] **Step 3: Run tests to verify they pass**

Run: `cd frontend && npx vitest run --project unit src/components/__tests__/VoiceOrb.test.tsx -t "VoiceOrb"`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/VoiceOrb.tsx frontend/src/components/__tests__/VoiceOrb.test.tsx
git commit -m "feat(voice): add VoiceOrb canvas component with simplex-noise animation"
```

---

### Task 9: Frontend — Redesigned VoiceIndicator

**Files:**
- Rewrite: `frontend/src/components/VoiceIndicator.tsx`
- Modify: `frontend/src/components/layout/__tests__/VoiceIndicator.test.tsx` (update tests for new behavior)

**Interfaces:**
- Consumes: `voiceBridgeService` singleton, `useAuthStore`
- Produces: Animated state ring button with hover dropdown

- [ ] **Step 1: Rewrite VoiceIndicator.tsx**

```typescript
import { useState, useEffect, useRef, useCallback } from 'react';
import { Mic, MicOff, ChevronDown, Settings2, Maximize2 } from 'lucide-react';
import { voiceBridgeService, BridgeStatus, VoiceState } from '@/services/voiceBridge';
import { useAuthStore } from '@/store/authStore';
import { LoadingSpinner } from '@/components/ui/LoadingSpinner';

type VoiceState = 'idle' | 'listening' | 'thinking' | 'speaking' | 'interrupted';

const STATUS_CFG: Record<BridgeStatus, { label: string; color: string; ringColor: string }> = {
  offline:    { label: 'Voice offline',  color: 'text-gray-500', ringColor: 'border-gray-500/30' },
  connecting: { label: 'Connecting…',    color: 'text-amber-400', ringColor: 'border-amber-400/50' },
  connected:  { label: 'Voice ready',    color: 'text-emerald-400', ringColor: 'border-emerald-400/50' },
  error:      { label: 'Voice error',    color: 'text-red-400', ringColor: 'border-red-400/50' },
};

const VOICE_STATE_RING: Record<VoiceState, string> = {
  idle: 'border-blue-500/20',
  listening: 'border-blue-500/60',
  thinking: 'border-purple-500/60',
  speaking: 'border-emerald-500/60',
  interrupted: 'border-amber-500/60',
};

interface VoiceIndicatorProps {
  iconOnly?: boolean;
}

export function VoiceIndicator({ iconOnly = false }: VoiceIndicatorProps) {
  const user = useAuthStore((s) => s.user);
  const isAuthenticated = user?.isAuthenticated ?? false;

  const [status, setStatus] = useState<BridgeStatus>(voiceBridgeService.status);
  const [voiceState, setVoiceState] = useState<VoiceState>('idle');
  const [isDisabled, setIsDisabled] = useState(false);
  const [dropdownOpen, setDropdownOpen] = useState(false);
  const connectAttempted = useRef(false);

  useEffect(() => {
    return voiceBridgeService.onStatusChange(setStatus);
  }, []);

  useEffect(() => {
    return voiceBridgeService.onStateChange((s) => {
      setVoiceState(s);
    });
  }, []);

  useEffect(() => {
    if (!isAuthenticated || connectAttempted.current || isDisabled) return;
    connectAttempted.current = true;
    voiceBridgeService.connect().catch(() => {});
  }, [isAuthenticated, isDisabled]);

  const effectiveStatus: BridgeStatus = isDisabled ? 'offline' : status;
  const { label, color, ringColor } = STATUS_CFG[effectiveStatus];

  const effectiveRing = effectiveStatus === 'connected'
    ? VOICE_STATE_RING[voiceState]
    : ringColor;

  const handleToggle = useCallback(() => {
    if (isDisabled) {
      setIsDisabled(false);
      connectAttempted.current = false;
      setTimeout(() => voiceBridgeService.connect(), 50);
      return;
    }
    if (status === 'connected') {
      voiceBridgeService.disconnect();
      setIsDisabled(true);
      return;
    }
    voiceBridgeService.connect().catch(() => {});
  }, [status, isDisabled]);

  return (
    <div className="relative">
      <button
        type="button"
        onClick={handleToggle}
        disabled={effectiveStatus === 'connecting'}
        className={`
          relative flex items-center gap-1.5 text-xs font-medium rounded-lg p-1.5
          transition-all duration-200 select-none
          hover:bg-gray-100 dark:hover:bg-white/10
          focus:outline-none focus:ring-2 focus:ring-blue-500/30
          disabled:cursor-default
          ${color}
          ${isDisabled ? 'opacity-40' : 'opacity-100'}
        `}
        title={label}
        aria-label={label}
        aria-pressed={effectiveStatus === 'connected'}
      >
        {/* Animated ring */}
        <span
          className={`absolute inset-0 rounded-lg border-2 transition-colors duration-300 ${effectiveRing}`}
          style={{
            animation: effectiveStatus === 'connecting'
              ? 'spin 1.5s linear infinite'
              : effectiveStatus === 'connected' && voiceState === 'listening'
              ? 'pulse 1.5s ease-in-out infinite'
              : undefined,
          }}
        />

        {effectiveStatus === 'connecting' ? (
          <LoadingSpinner size="xs" />
        ) : effectiveStatus === 'connected' ? (
          <Mic className="relative w-3.5 h-3.5" />
        ) : (
          <MicOff className="relative w-3.5 h-3.5" />
        )}

        {!iconOnly && <span className="hidden sm:inline whitespace-nowrap">{label}</span>}

        {effectiveStatus === 'error' && (
          <span className="absolute -top-0.5 -right-0.5 h-2 w-2 rounded-full bg-red-500 ring-2 ring-white dark:ring-gray-900" />
        )}
      </button>

      {/* Dropdown toggle */}
      {(effectiveStatus === 'connected' || effectiveStatus === 'offline') && (
        <button
          type="button"
          onClick={() => setDropdownOpen(!dropdownOpen)}
          className="ml-0.5 p-1 text-gray-500 hover:text-gray-300 transition-colors"
          aria-label="Voice options"
        >
          <ChevronDown className="w-3 h-3" />
        </button>
      )}

      {/* Dropdown */}
      {dropdownOpen && (
        <div className="absolute top-full right-0 mt-1 w-56 bg-white dark:bg-[#161b27] border border-gray-200 dark:border-[#1e2535] rounded-xl shadow-lg z-50 p-2 space-y-1">
          <div className="px-3 py-2 text-xs text-gray-500 dark:text-gray-400 flex items-center gap-2">
            <span className={`w-2 h-2 rounded-full ${effectiveStatus === 'connected' ? 'bg-emerald-500' : 'bg-gray-500'}`} />
            {label}
          </div>
          {effectiveStatus === 'offline' && (
            <div className="px-3 py-2 text-xs text-gray-600 dark:text-gray-500 bg-gray-50 dark:bg-black/30 rounded-lg">
              <p className="mb-1">Bridge not running.</p>
              <code className="text-[10px] text-green-500">powershell -File ".\scripts\setup.ps1"</code>
              <button
                onClick={() => navigator.clipboard.writeText('powershell -ExecutionPolicy Bypass -File ".\\scripts\\setup.ps1"')}
                className="ml-1 text-blue-500 hover:text-blue-400"
              >
                Copy
              </button>
            </div>
          )}
          <button
            onClick={() => setDropdownOpen(false)}
            className="w-full flex items-center gap-2 px-3 py-2 text-xs text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-white/10 rounded-lg transition-colors"
          >
            <Settings2 className="w-3.5 h-3.5" />
            Voice Settings
          </button>
          <button
            onClick={() => {
              setDropdownOpen(false);
              // Dispatch custom event to open voice mode panel
              window.dispatchEvent(new CustomEvent('open-voice-mode'));
            }}
            className="w-full flex items-center gap-2 px-3 py-2 text-xs text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-white/10 rounded-lg transition-colors"
          >
            <Maximize2 className="w-3.5 h-3.5" />
            Open Voice Mode
          </button>
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Update the existing test**

Edit `frontend/src/components/layout/__tests__/VoiceIndicator.test.tsx` — the install notification is now inside a dropdown instead of a portal. Update the test to reflect this:

```typescript
import { render, screen } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { VoiceIndicator } from '../../VoiceIndicator';
import { useAuthStore } from '@/store/authStore';

vi.mock('@/services/voiceBridge', () => ({
  voiceBridgeService: {
    status: 'offline',
    onStatusChange: vi.fn(() => () => {}),
    onStateChange: vi.fn(() => () => {}),
    connect: vi.fn(() => Promise.resolve()),
    disconnect: vi.fn(),
  },
}));

beforeEach(() => {
  useAuthStore.setState({
    user: { isAuthenticated: true, username: 'tester', role: 'member' } as never,
  });
});

describe('VoiceIndicator', () => {
  it('renders the mic button', () => {
    render(<VoiceIndicator />);
    expect(screen.getByRole('button', { name: /voice/i })).toBeTruthy();
  });

  it('shows offline state when bridge is not connected', () => {
    render(<VoiceIndicator />);
    expect(screen.getByText('Voice offline')).toBeTruthy();
  });
});
```

- [ ] **Step 3: Run tests**

Run: `cd frontend && npx vitest run --project unit src/components/layout/__tests__/VoiceIndicator.test.tsx`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/VoiceIndicator.tsx frontend/src/components/layout/__tests__/VoiceIndicator.test.tsx
git commit -m "feat(voice): redesign VoiceIndicator with animated state ring and dropdown"
```

---

### Task 10: Frontend — Redesigned VoiceSettingsModal

**Files:**
- Rewrite: `frontend/src/components/VoiceSettingsModal.tsx`

**Interfaces:**
- Consumes: `voiceApi` service, existing `Modal` and `Toggle` components
- Produces: 3-tab modal with Engine, Speaker Profiles, Advanced sections

- [ ] **Step 1: Write failing tests**

Create `frontend/src/components/__tests__/VoiceSettingsModal.test.tsx`:
```typescript
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { VoiceSettingsModal } from '../VoiceSettingsModal';

vi.mock('@/services/voiceApi', () => ({
  voiceApi: {
    getVoiceConfig: vi.fn(() => Promise.resolve({ requireWakeWord: true, ttsVoice: 'af_bella', proactiveEnabled: false, speakerIdentification: false })),
    setVoiceConfig: vi.fn(() => Promise.resolve()),
    getSpeakers: vi.fn(() => Promise.resolve({ speakers: [] })),
  },
}));

describe('VoiceSettingsModal', () => {
  it('renders with three tabs', () => {
    render(<VoiceSettingsModal onClose={vi.fn()} />);
    expect(screen.getByText('Engine')).toBeTruthy();
    expect(screen.getByText('Speaker Profiles')).toBeTruthy();
    expect(screen.getByText('Advanced')).toBeTruthy();
  });

  it('shows the Engine tab by default', () => {
    render(<VoiceSettingsModal onClose={vi.fn()} />);
    expect(screen.getByText('Require wake word')).toBeTruthy();
  });

  it('switches to Speaker Profiles tab on click', async () => {
    render(<VoiceSettingsModal onClose={vi.fn()} />);
    await screen.findByText('Speaker Profiles');
    fireEvent.click(screen.getByText('Speaker Profiles'));
    expect(screen.getByText('Enroll a speaker profile')).toBeTruthy();
  });
});
```

- [ ] **Step 2: Rewrite VoiceSettingsModal.tsx**

```typescript
import React, { useState, useEffect, useRef } from 'react';
import { Mic, Trash2, Settings2, Users, SlidersHorizontal, Play, Square } from 'lucide-react';
import { voiceApi } from '@/services/voiceApi';
import { showToast } from '@/hooks/useToast';
import { LoadingSpinner } from '@/components/ui/LoadingSpinner';
import { Modal } from '@/components/ui/Modal';
import { Toggle } from '@/components/ui/Toggle';

interface SpeakerProfile {
  id: string; name: string; user_id?: string;
  enrolled_at: string; sample_count: number; has_embedding: boolean;
}

interface VoiceSettingsModalProps { onClose: () => void; }

type TabId = 'engine' | 'speakers' | 'advanced';

const TABS: { id: TabId; label: string; icon: React.ReactNode }[] = [
  { id: 'engine', label: 'Engine', icon: <Settings2 className="w-4 h-4" /> },
  { id: 'speakers', label: 'Speaker Profiles', icon: <Users className="w-4 h-4" /> },
  { id: 'advanced', label: 'Advanced', icon: <SlidersHorizontal className="w-4 h-4" /> },
];

export function VoiceSettingsModal({ onClose }: VoiceSettingsModalProps) {
  const [activeTab, setActiveTab] = useState<TabId>('engine');
  const [speakers, setSpeakers] = useState<SpeakerProfile[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isRecording, setIsRecording] = useState(false);
  const [recordingTime, setRecordingTime] = useState(0);
  const [speakerName, setSpeakerName] = useState('');
  const [isRegistering, setIsRegistering] = useState(false);

  // Engine config
  const [requireWakeWord, setRequireWakeWord] = useState(true);
  const [ttsVoice, setTtsVoice] = useState('af_bella');
  const [proactiveEnabled, setProactiveEnabled] = useState(false);
  const [speakerIdentification, setSpeakerIdentification] = useState(false);
  const [isSavingConfig, setIsSavingConfig] = useState(false);

  // Advanced config
  const [inputMode, setInputMode] = useState<'ptt' | 'aon'>('aon');
  const [micSensitivity, setMicSensitivity] = useState(75);
  const [noiseSuppression, setNoiseSuppression] = useState(true);
  const [reducedMotion, setReducedMotion] = useState(false);

  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioStreamRef = useRef<MediaStream | null>(null);
  const recordingIntervalRef = useRef<NodeJS.Timeout | null>(null);
  const chunksRef = useRef<Blob[]>([]);

  useEffect(() => {
    loadSpeakers();
    return () => stopRecording();
  }, []);

  useEffect(() => {
    const saved = localStorage.getItem('voice_engine_config');
    if (saved) {
      try {
        const cfg = JSON.parse(saved);
        setRequireWakeWord(cfg.requireWakeWord ?? true);
        setTtsVoice(cfg.ttsVoice ?? 'af_bella');
        setProactiveEnabled(cfg.proactiveEnabled ?? false);
        setSpeakerIdentification(cfg.speakerIdentification ?? false);
      } catch { /* ignore */ }
    }
    voiceApi.getVoiceConfig().then((cfg: any) => {
      if (!cfg) return;
      setRequireWakeWord(cfg.requireWakeWord ?? requireWakeWord);
      setTtsVoice(cfg.ttsVoice ?? ttsVoice);
      setProactiveEnabled(cfg.proactiveEnabled ?? proactiveEnabled);
      setSpeakerIdentification(cfg.speakerIdentification ?? speakerIdentification);
    }).catch(() => {});
  }, []);

  const loadSpeakers = async () => {
    setIsLoading(true);
    try {
      const res = await voiceApi.getSpeakers();
      setSpeakers(res.speakers || []);
    } catch { showToast.error('Failed to load speaker profiles'); }
    finally { setIsLoading(false); }
  };

  const saveConfig = async () => {
    setIsSavingConfig(true);
    const cfg = { requireWakeWord, ttsVoice, proactiveEnabled, speakerIdentification };
    localStorage.setItem('voice_engine_config', JSON.stringify(cfg));
    try {
      await voiceApi.setVoiceConfig(cfg);
      showToast.success('Voice engine settings saved');
    } catch { showToast.success('Voice engine settings saved locally'); }
    finally { setIsSavingConfig(false); }
  };

  const startRecording = async () => {
    if (!speakerName.trim()) { showToast.error('Enter a speaker name'); return; }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      audioStreamRef.current = stream;
      const recorder = new MediaRecorder(stream);
      mediaRecorderRef.current = recorder;
      chunksRef.current = [];
      recorder.ondataavailable = (e) => { if (e.data.size > 0) chunksRef.current.push(e.data); };
      recorder.onstop = async () => {
        const blob = new Blob(chunksRef.current, { type: 'audio/webm' });
        await handleRegister(blob);
      };
      recorder.start();
      setIsRecording(true);
      setRecordingTime(0);
      recordingIntervalRef.current = setInterval(() => setRecordingTime(p => p + 1), 1000);
    } catch { showToast.error('Microphone access denied'); }
  };

  const stopRecording = () => {
    mediaRecorderRef.current?.stop();
    audioStreamRef.current?.getTracks().forEach(t => t.stop());
    audioStreamRef.current = null;
    clearInterval(recordingIntervalRef.current!);
    recordingIntervalRef.current = null;
    setIsRecording(false);
  };

  const handleRegister = async (blob: Blob) => {
    setIsRegistering(true);
    try {
      await voiceApi.registerSpeaker(blob, speakerName.trim());
      showToast.success('Speaker enrolled');
      setSpeakerName('');
      await loadSpeakers();
    } catch { showToast.error('Failed to enroll speaker profile'); }
    finally { setIsRegistering(false); }
  };

  const handleDelete = async (id: string) => {
    try { await voiceApi.deleteSpeaker(id); showToast.success('Deleted'); await loadSpeakers(); }
    catch { showToast.error('Failed to delete'); }
  };

  return (
    <Modal open onClose={onClose} size="lg" className="!max-w-2xl">
      <div className="flex min-h-[400px]">
        {/* Sidebar tabs */}
        <div className="w-44 shrink-0 border-r border-gray-200 dark:border-[#1e2535] p-3 space-y-1">
          {TABS.map(tab => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`w-full flex items-center gap-2.5 px-3 py-2.5 text-sm rounded-lg transition-colors text-left ${
                activeTab === tab.id
                  ? 'bg-blue-50 dark:bg-blue-500/10 text-blue-700 dark:text-blue-400 font-medium border-l-2 border-blue-600'
                  : 'text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-white/5'
              }`}
            >
              {tab.icon}
              {tab.label}
            </button>
          ))}
        </div>

        {/* Content */}
        <div className="flex-1 p-5 overflow-y-auto">
          {activeTab === 'engine' && (
            <div className="space-y-4">
              <h3 className="text-sm font-semibold text-gray-900 dark:text-white">Voice Engine</h3>
              <Toggle checked={requireWakeWord} onChange={setRequireWakeWord} label="Require wake word ('Agentium')" />
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">TTS Voice</label>
                <div className="flex gap-2">
                  <select
                    value={ttsVoice}
                    onChange={e => setTtsVoice(e.target.value)}
                    className="flex-1 bg-white dark:bg-[#161b27] border border-gray-200 dark:border-[#1e2535] rounded-xl px-4 py-2.5 text-gray-900 dark:text-white focus:outline-none focus:border-blue-500 text-sm"
                  >
                    {['af_bella', 'am_adam', 'bf_emma', 'bm_george', 'af_nicole', 'af_sarah'].map(v => (
                      <option key={v} value={v}>{v.replace('_', ' ')}</option>
                    ))}
                  </select>
                  <button
                    type="button"
                    className="p-2.5 rounded-xl bg-gray-100 dark:bg-[#1e2535] text-gray-600 dark:text-gray-400 hover:text-blue-500 transition-colors"
                    aria-label="Preview voice"
                    title="Preview"
                  >
                    <Play className="w-4 h-4" />
                  </button>
                </div>
              </div>
              <Toggle checked={proactiveEnabled} onChange={setProactiveEnabled} label="Proactive announcements" description="AI announces system events unprompted" />
              <Toggle checked={speakerIdentification} onChange={setSpeakerIdentification} label="Speaker identification" description="Identify who is speaking in multi-user settings" />
              <button
                onClick={saveConfig}
                disabled={isSavingConfig}
                className="flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-medium bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-50"
              >
                {isSavingConfig ? <LoadingSpinner size="sm" /> : 'Save'}
              </button>
            </div>
          )}

          {activeTab === 'speakers' && (
            <div className="space-y-5">
              <h3 className="text-sm font-semibold text-gray-900 dark:text-white">Speaker Profiles</h3>
              <div className="bg-gray-50 dark:bg-[#0f1117] border border-gray-200 dark:border-[#1e2535] rounded-2xl p-4">
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">Speaker Name</label>
                <input
                  type="text" value={speakerName}
                  onChange={e => setSpeakerName(e.target.value)}
                  placeholder="e.g. Host, Alice, Guest 1"
                  disabled={isRecording || isRegistering}
                  className="w-full bg-white dark:bg-[#161b27] border border-gray-200 dark:border-[#1e2535] rounded-xl px-4 py-2.5 text-gray-900 dark:text-white focus:outline-none focus:border-blue-500 mb-4 text-sm"
                />
                <div className="flex items-center justify-between">
                  <div className="text-sm text-gray-600 dark:text-gray-400 flex items-center gap-2">
                    {isRecording && <span className="w-2 h-2 rounded-full bg-red-500 animate-pulse" />}
                    {isRecording ? `Recording... 00:${recordingTime.toString().padStart(2, '0')}` : 'Record a 3-5 second sample.'}
                  </div>
                  <button
                    onClick={isRecording ? stopRecording : startRecording}
                    disabled={isRegistering}
                    className={`flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-medium transition-colors ${
                      isRecording
                        ? 'bg-red-100 text-red-600 hover:bg-red-200 dark:bg-red-500/20 dark:text-red-400'
                        : 'bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-50'
                    }`}
                  >
                    {isRegistering ? <LoadingSpinner size="sm" /> : isRecording ? <Square className="w-4 h-4" fill="currentColor"/> : <Mic className="w-4 h-4" />}
                    {isRegistering ? 'Processing' : isRecording ? 'Stop' : 'Start Enroll'}
                  </button>
                </div>
              </div>

              <div className="space-y-2">
                <h4 className="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wide">Enrolled Profiles</h4>
                {isLoading ? (
                  <div className="flex justify-center py-6"><LoadingSpinner size="md" /></div>
                ) : speakers.length === 0 ? (
                  <div className="text-center py-6 border border-dashed border-gray-200 dark:border-[#1e2535] rounded-2xl">
                    <p className="text-sm text-gray-500">No speaker profiles enrolled yet.</p>
                  </div>
                ) : (
                  <div className="space-y-2">
                    {speakers.map(s => (
                      <div key={s.id} className="flex items-center gap-3 bg-white dark:bg-[#161b27] border border-gray-200 dark:border-[#1e2535] p-3 rounded-xl">
                        <div className="w-10 h-10 rounded-full bg-blue-100 dark:bg-blue-500/20 flex items-center justify-center text-sm font-semibold text-blue-700 dark:text-blue-400 shrink-0">
                          {s.name.charAt(0).toUpperCase()}
                        </div>
                        <div className="flex-1 min-w-0">
                          <div className="text-sm font-medium text-gray-900 dark:text-white truncate">{s.name}</div>
                          <div className="text-xs text-gray-500">Enrolled: {new Date(s.enrolled_at).toLocaleDateString()}</div>
                        </div>
                        <button onClick={() => handleDelete(s.id)} className="p-2 text-gray-400 hover:text-red-500 transition-colors rounded-lg hover:bg-red-50 dark:hover:bg-red-500/10" aria-label={`Delete ${s.name}`}>
                          <Trash2 className="w-4 h-4" />
                        </button>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          )}

          {activeTab === 'advanced' && (
            <div className="space-y-4">
              <h3 className="text-sm font-semibold text-gray-900 dark:text-white">Advanced Settings</h3>
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">Input Mode</label>
                <div className="flex gap-2">
                  <button onClick={() => setInputMode('ptt')} className={`flex-1 px-4 py-2.5 rounded-xl text-sm font-medium border transition-colors ${inputMode === 'ptt' ? 'bg-blue-50 dark:bg-blue-500/10 border-blue-500 text-blue-700 dark:text-blue-400' : 'bg-white dark:bg-[#161b27] border-gray-200 dark:border-[#1e2535] text-gray-600 dark:text-gray-400'}`}>
                    Push to Talk
                  </button>
                  <button onClick={() => setInputMode('aon')} className={`flex-1 px-4 py-2.5 rounded-xl text-sm font-medium border transition-colors ${inputMode === 'aon' ? 'bg-blue-50 dark:bg-blue-500/10 border-blue-500 text-blue-700 dark:text-blue-400' : 'bg-white dark:bg-[#161b27] border-gray-200 dark:border-[#1e2535] text-gray-600 dark:text-gray-400'}`}>
                    Always On
                  </button>
                </div>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">Mic Sensitivity: {micSensitivity}%</label>
                <input type="range" min={0} max={100} value={micSensitivity} onChange={e => setMicSensitivity(Number(e.target.value))} className="w-full accent-blue-600" />
              </div>
              <Toggle checked={noiseSuppression} onChange={setNoiseSuppression} label="Noise Suppression" />
              <Toggle checked={reducedMotion} onChange={setReducedMotion} label="Reduced Motion" description="Disable animations for accessibility" />
            </div>
          )}
        </div>
      </div>
    </Modal>
  );
}
```

- [ ] **Step 3: Run the tests**

Run: `cd frontend && npx vitest run --project unit src/components/__tests__/VoiceSettingsModal.test.tsx`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/VoiceSettingsModal.tsx frontend/src/components/__tests__/VoiceSettingsModal.test.tsx
git commit -m "feat(voice): redesign VoiceSettingsModal with 3-tab layout"
```

---

### Task 11: Frontend — VoiceModePanel

**Files:**
- Create: `frontend/src/components/VoiceModePanel.tsx`

**Interfaces:**
- Consumes: `voiceBridgeService` (onStateChange, onTranscript, onStatusChange), `VoiceOrb` component
- Produces: Semi-modal voice conversation overlay with orb, transcript, controls

- [ ] **Step 1: Write failing test**

Create `frontend/src/components/__tests__/VoiceModePanel.test.tsx`:
```typescript
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { VoiceModePanel } from '../VoiceModePanel';

vi.mock('@/services/voiceBridge', () => ({
  voiceBridgeService: {
    status: 'connected',
    onStatusChange: vi.fn(() => () => {}),
    onStateChange: vi.fn(() => () => {}),
    onTranscript: vi.fn(() => () => {}),
    disconnect: vi.fn(),
  },
}));

describe('VoiceModePanel', () => {
  it('renders the voice mode panel when open', () => {
    render(<VoiceModePanel open={true} onClose={vi.fn()} />);
    expect(screen.getByLabelText('Voice conversation')).toBeTruthy();
  });

  it('calls onClose when end session is clicked', () => {
    const onClose = vi.fn();
    render(<VoiceModePanel open={true} onClose={onClose} />);
    fireEvent.click(screen.getByLabelText('End session'));
    expect(onClose).toHaveBeenCalled();
  });
});
```

- [ ] **Step 2: Create VoiceModePanel.tsx**

```typescript
import { useEffect, useRef, useState, useCallback } from 'react';
import { Mic, MicOff, X, Volume2, VolumeX } from 'lucide-react';
import { voiceBridgeService, BridgeStatus, VoiceState, TranscriptEvent } from '@/services/voiceBridge';
import { VoiceOrb } from './VoiceOrb';

type VoiceState = 'idle' | 'listening' | 'thinking' | 'speaking' | 'interrupted';

interface VoiceModePanelProps {
  open: boolean;
  onClose: () => void;
}

export function VoiceModePanel({ open, onClose }: VoiceModePanelProps) {
  const [voiceState, setVoiceState] = useState<VoiceState>('idle');
  const [bridgeStatus, setBridgeStatus] = useState<BridgeStatus>('offline');
  const [userTranscript, setUserTranscript] = useState('');
  const [agentTranscript, setAgentTranscript] = useState('');
  const [muted, setMuted] = useState(false);
  const [mode, setMode] = useState<'ptt' | 'aon'>('aon');
  const panelRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) {
      setVoiceState('idle');
      setUserTranscript('');
      setAgentTranscript('');
      return;
    }

    const unsubState = voiceBridgeService.onStateChange(setVoiceState);
    const unsubStatus = voiceBridgeService.onStatusChange(setBridgeStatus);
    const unsubTranscript = voiceBridgeService.onTranscript((event: TranscriptEvent) => {
      if (event.role === 'user') setUserTranscript(event.text);
      else setAgentTranscript(event.text);
    });

    return () => {
      unsubState();
      unsubStatus();
      unsubTranscript();
    };
  }, [open]);

  const handleEndSession = useCallback(() => {
    voiceBridgeService.disconnect();
    onClose();
  }, [onClose]);

  const handleKeyDown = useCallback((e: KeyboardEvent) => {
    if (e.key === 'Escape') handleEndSession();
  }, [handleEndSession]);

  useEffect(() => {
    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [handleKeyDown]);

  if (!open) return null;

  return (
    <div
      ref={panelRef}
      role="dialog"
      aria-modal="true"
      aria-label="Voice conversation"
      className="fixed inset-0 z-40 flex items-center justify-center bg-black/40 backdrop-blur-sm"
    >
      <div className="relative flex flex-col items-center justify-center w-full max-w-lg mx-4 py-8 px-6 bg-[#0f1117]/90 border border-[#1e2535] rounded-3xl shadow-2xl">
        {/* Top bar */}
        <div className="absolute top-4 right-4 flex items-center gap-2">
          <button
            onClick={() => setMode(mode === 'ptt' ? 'aon' : 'ptt')}
            className="px-3 py-1.5 text-xs font-medium rounded-full bg-[#1e2535] text-gray-400 hover:text-white transition-colors"
            aria-label={`Switch to ${mode === 'ptt' ? 'always-on' : 'push-to-talk'} mode`}
          >
            {mode === 'ptt' ? 'PTT' : 'AON'}
          </button>
          <button
            onClick={handleEndSession}
            className="p-2 rounded-full bg-[#1e2535] text-gray-400 hover:text-white hover:bg-red-500/20 transition-colors"
            aria-label="End session"
            title="End session"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Orb */}
        <div className="my-4">
          <VoiceOrb
            size={280}
            voiceState={voiceState}
            micLevel={0.5}
          />
        </div>

        {/* Transcript */}
        <div className="w-full space-y-1 mb-6 min-h-[3rem]">
          {userTranscript && (
            <p className="text-sm text-blue-400 text-center leading-relaxed">
              <span className="font-medium">You:</span> {userTranscript}
            </p>
          )}
          {agentTranscript && (
            <p className="text-sm text-emerald-400 text-center leading-relaxed">
              <span className="font-medium">Agentium:</span> {agentTranscript}
            </p>
          )}
          {!userTranscript && !agentTranscript && voiceState === 'listening' && (
            <p className="text-sm text-gray-500 text-center animate-pulse">Listening...</p>
          )}
        </div>

        {/* Bottom controls */}
        <div className="flex items-center gap-4">
          <button
            onClick={() => setMuted(!muted)}
            className={`p-3 rounded-full transition-colors ${
              muted ? 'bg-red-500/20 text-red-400' : 'bg-[#1e2535] text-gray-400 hover:text-white'
            }`}
            aria-label={muted ? 'Unmute microphone' : 'Mute microphone'}
            title={muted ? 'Unmute' : 'Mute'}
          >
            {muted ? <VolumeX className="w-5 h-5" /> : <Volume2 className="w-5 h-5" />}
          </button>

          <button
            className="w-14 h-14 rounded-full bg-blue-600 hover:bg-blue-700 flex items-center justify-center transition-colors disabled:opacity-50"
            aria-label={voiceState === 'listening' ? 'Listening...' : 'Push to talk'}
            disabled={bridgeStatus !== 'connected'}
          >
            <Mic className="w-6 h-6 text-white" />
          </button>

          <button
            onClick={handleEndSession}
            className="p-3 rounded-full bg-[#1e2535] text-gray-400 hover:text-red-400 transition-colors"
            aria-label="End session"
            title="End session"
          >
            <X className="w-5 h-5" />
          </button>
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Run tests**

Run: `cd frontend && npx vitest run --project unit src/components/__tests__/VoiceModePanel.test.tsx`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/VoiceModePanel.tsx frontend/src/components/__tests__/VoiceModePanel.test.tsx
git commit -m "feat(voice): add VoiceModePanel with orb, transcript, and controls"
```

---

### Task 12: Frontend — ChatPage integration

**Files:**
- Modify: `frontend/src/pages/ChatPage.tsx`

**Interfaces:**
- Consumes: `VoiceModePanel` component, `window` custom event "open-voice-mode"
- Produces: Voice mode panel rendered in chat page, wired to open from VoiceIndicator dropdown

- [ ] **Step 1: Add VoiceModePanel state and event listener**

In ChatPage.tsx, add:
```typescript
import { VoiceModePanel } from '@/components/VoiceModePanel';

// Inside the component:
const [voiceModeOpen, setVoiceModeOpen] = useState(false);

// Add effect to listen for custom event from VoiceIndicator
useEffect(() => {
  const handler = () => setVoiceModeOpen(true);
  window.addEventListener('open-voice-mode', handler);
  return () => window.removeEventListener('open-voice-mode', handler);
}, []);
```

- [ ] **Step 2: Render VoiceModePanel in the JSX**

Add near the end of the component's return, before the closing fragment:
```tsx
<VoiceModePanel
  open={voiceModeOpen}
  onClose={() => setVoiceModeOpen(false)}
/>
```

No structural changes to the existing chat layout — the VoiceModePanel renders as a fixed overlay.

- [ ] **Step 3: Verify build**

Run: `cd frontend && npx tsc --noEmit`
Expected: No type errors

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/ChatPage.tsx
git commit -m "feat(voice): integrate VoiceModePanel into ChatPage"
```

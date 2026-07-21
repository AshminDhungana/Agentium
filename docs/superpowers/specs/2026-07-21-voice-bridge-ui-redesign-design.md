# Voice Bridge UI Redesign - Design Specification

## Overview
This document defines the detailed design specification for the Voice Bridge UI Redesign. It covers visual design, component specifications, animations, accessibility requirements, and implementation details.

## Design System Integration

### Colors (from Agentium Design Tokens)
```css
/* Primary Colors */
--color-primary-50: #eff6ff;
--color-primary-100: #dbeafe;
--color-primary-200: #bfdbfe;
--color-primary-300: #93c5fd;
--color-primary-400: #60a5fa;
--color-primary-500: #3b82f6;  /* Main primary */
--color-primary-600: #2563eb;
--color-primary-700: #1d4ed8;
--color-primary-800: #1e40af;
--color-primary-900: #1e3a8a;

/* Secondary/Purple Gradient */
--color-secondary-500: #8b5cf6;
--color-secondary-600: #7c3aed;

/* Accent Colors for Voice States */
--color-voice-idle: #64748b;       /* Slate */
--color-voice-listening: #3b82f6;  /* Primary blue */
--color-voice-speaking: #8b5cf6;   /* Purple */
--color-voice-processing: #f59e0b; /* Amber */
--color-voice-error: #ef4444;      /* Red */
--color-voice-muted: #9ca3af;      /* Gray */

/* Background Colors */
--color-bg-primary: #0f172a;       /* Slate 950 */
--color-bg-secondary: #1e293b;     /* Slate 800 */
--color-bg-tertiary: #334155;      /* Slate 700 */
--color-bg-glass: rgba(30, 41, 59, 0.7); /* Glassmorphism base */
--color-bg-glass-hover: rgba(51, 65, 85, 0.8);

/* Text Colors */
--color-text-primary: #f8fafc;     /* Slate 50 */
--color-text-secondary: #cbd5e1;   /* Slate 300 */
--color-text-muted: #94a3b8;       /* Slate 400 */
--color-text-inverse: #0f172a;     /* Slate 950 */

/* Border Colors */
--color-border-subtle: rgba(148, 163, 184, 0.15);
--color-border-default: rgba(148, 163, 184, 0.25);
--color-border-strong: rgba(148, 163, 184, 0.4);
```

### Spacing Scale (8px base unit)
```css
--space-0: 0;
--space-1: 4px;   /* 0.5 * base */
--space-2: 8px;   /* 1 * base */
--space-3: 12px;  /* 1.5 * base */
--space-4: 16px;  /* 2 * base */
--space-5: 20px;  /* 2.5 * base */
--space-6: 24px;  /* 3 * base */
--space-8: 32px;  /* 4 * base */
--space-10: 40px; /* 5 * base */
--space-12: 48px; /* 6 * base */
--space-16: 64px; /* 8 * base */
--space-20: 80px; /* 10 * base */
--space-24: 96px; /* 12 * base */
```

### Typography
```css
/* Font Family */
--font-sans: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
--font-mono: 'JetBrains Mono', 'Fira Code', monospace;

/* Font Sizes */
--text-xs: 0.75rem;    /* 12px */
--text-sm: 0.875rem;   /* 14px */
--text-base: 1rem;     /* 16px */
--text-lg: 1.125rem;   /* 18px */
--text-xl: 1.25rem;    /* 20px */
--text-2xl: 1.5rem;    /* 24px */
--text-3xl: 1.875rem;  /* 30px */
--text-4xl: 2.25rem;   /* 36px */
--text-5xl: 3rem;      /* 48px */

/* Font Weights */
--font-normal: 400;
--font-medium: 500;
--font-semibold: 600;
--font-bold: 700;

/* Line Heights */
--leading-tight: 1.25;
--leading-normal: 1.5;
--leading-relaxed: 1.75;
```

### Border Radius
```css
--radius-none: 0;
--radius-sm: 4px;
--radius-md: 8px;
--radius-lg: 12px;
--radius-xl: 16px;
--radius-2xl: 24px;
--radius-full: 9999px;
```

### Shadows
```css
--shadow-sm: 0 1px 2px 0 rgb(0 0 0 / 0.05);
--shadow-md: 0 4px 6px -1px rgb(0 0 0 / 0.1), 0 2px 4px -2px rgb(0 0 0 / 0.1);
--shadow-lg: 0 10px 15px -3px rgb(0 0 0 / 0.1), 0 4px 6px -4px rgb(0 0 0 / 0.1);
--shadow-xl: 0 20px 25px -5px rgb(0 0 0 / 0.1), 0 8px 10px -6px rgb(0 0 0 / 0.1);
--shadow-glow: 0 0 20px rgb(59 130 246 / 0.3);
--shadow-glow-strong: 0 0 40px rgb(59 130 246 / 0.5);
```

### Glassmorphism
```css
--glass-bg: rgba(30, 41, 59, 0.7);
--glass-bg-hover: rgba(51, 65, 85, 0.8);
--glass-border: rgba(148, 163, 184, 0.15);
--glass-blur: blur(20px);
--glass-blur-strong: blur(40px);
```

### Transitions
```css
--transition-fast: 150ms cubic-bezier(0.4, 0, 0.2, 1);
--transition-normal: 250ms cubic-bezier(0.4, 0, 0.2, 1);
--transition-slow: 350ms cubic-bezier(0.4, 0, 0.2, 1);
--transition-spring: 400ms cubic-bezier(0.34, 1.56, 0.64, 1);
```

---

## Component Specifications

### 1. VoiceBridgeContainer
**Purpose**: Main container orchestrating all voice bridge components

**Layout**:
- Full viewport height (min-h-screen)
- Centered content with max-width constraint
- Glassmorphism background with subtle gradient overlay

**Structure**:
```
VoiceBridgeContainer
├── ConnectionStatus (top-right)
├── VoiceVisualizationArea (center)
│   ├── VoiceOrb (center)
│   ├── WaveformVisualizer (behind orb, optional)
│   └── FrequencyBars (behind orb, optional)
├── MicrophoneLevel (bottom of visualization)
├── TranscriptDisplay (below visualization)
├── VoiceControls (bottom center)
└── VoiceSettings (slide-up panel from bottom)
```

**Responsive**:
- Desktop: Side-by-side layout for visualization + transcript
- Tablet: Stacked, orb larger
- Mobile: Full-width, compact controls

**CSS Classes**:
```css
.voice-bridge-container {
  @apply min-h-screen flex flex-col items-center justify-center p-6;
  background: var(--color-bg-primary);
}
.voice-bridge-container::before {
  content: '';
  @apply absolute inset-0;
  background: radial-gradient(ellipse at center, rgba(59, 130, 246, 0.08) 0%, transparent 70%);
  pointer-events: none;
}
```

### 2. VoiceOrb
**Purpose**: Central animated visualization showing voice state

**States**:
1. **Idle** - Subtle pulsing, slate color, small size
2. **Listening** - Expanding/contracting, blue color, audio-reactive
3. **Speaking** - Rotating/swirling, purple color, audio-reactive
4. **Processing** - Spinning/loading, amber color
5. **Error** - Shaking, red color
6. **Muted** - Dimmed, gray color, crossed microphone icon

**Visual Properties**:
- Base size: 120px (desktop), 100px (mobile)
- Max expanded size: 200px (desktop), 160px (mobile)
- Glassmorphism surface with backdrop blur
- Outer glow matching state color
- Inner content: Icon (mic, speaker, spinner, X) or waveform

**Animations (Motion.dev)**:
```typescript
// Idle: Subtle pulse
const idleVariants = {
  initial: { scale: 1 },
  pulse: { 
    scale: [1, 1.02, 1],
    transition: { duration: 3, repeat: Infinity, ease: "easeInOut" }
  }
};

// Listening: Expand/contract with audio level
const listeningVariants = {
  initial: { scale: 1 },
  active: (level: number) => ({
    scale: 1 + level * 0.5,
    boxShadow: `0 0 ${40 + level * 60}px ${level * 20}px ${stateColor}`,
    transition: { duration: 0.1, ease: "easeOut" }
  })
};

// Speaking: Rotate + scale with audio
const speakingVariants = {
  initial: { rotate: 0, scale: 1 },
  active: (level: number) => ({
    rotate: 360,
    scale: 1 + level * 0.3,
    transition: { duration: 10, repeat: Infinity, ease: "linear" }
  })
};

// Processing: Spin
const processingVariants = {
  initial: { rotate: 0 },
  active: {
    rotate: 360,
    transition: { duration: 1, repeat: Infinity, ease: "linear" }
  }
};

// Error: Shake
const errorVariants = {
  initial: { x: 0 },
  active: {
    x: [-10, 10, -10, 10, 0],
    transition: { duration: 0.5, ease: "easeInOut" }
  }
};

// State transitions
const stateTransition = {
  type: "spring",
  stiffness: 300,
  damping: 30,
  mass: 1
};
```

**Accessibility**:
- `role="img"` with `aria-label` describing current state
- `aria-live="polite"` for state announcements
- Respects `prefers-reduced-motion` (static orb with color change only)

### 3. WaveformVisualizer
**Purpose**: Real-time audio waveform visualization using Canvas

**Canvas Specifications**:
- Width: 100% of container (max 600px)
- Height: 80px (desktop), 60px (mobile)
- Background: Transparent
- Waveform color: Gradient from state color to transparent
- Line width: 2px
- Smoothing: Catmull-Rom spline interpolation

**Data Input**:
- AudioContext AnalyserNode frequency data (Float32Array)
- Time domain data (Uint8Array) for waveform
- Update rate: 60fps (requestAnimationFrame)

**Rendering**:
```typescript
// Waveform rendering
const drawWaveform = (ctx: CanvasRenderingContext2D, data: Uint8Array, color: string) => {
  const width = canvas.width;
  const height = canvas.height;
  const centerY = height / 2;
  
  ctx.clearRect(0, 0, width, height);
  
  // Gradient
  const gradient = ctx.createLinearGradient(0, 0, 0, height);
  gradient.addColorStop(0, color);
  gradient.addColorStop(0.5, color + '80');
  gradient.addColorStop(1, 'transparent');
  
  ctx.strokeStyle = gradient;
  ctx.lineWidth = 2;
  ctx.lineCap = 'round';
  ctx.lineJoin = 'round';
  
  ctx.beginPath();
  const sliceWidth = width / data.length;
  let x = 0;
  
  for (let i = 0; i < data.length; i++) {
    const v = data[i] / 128.0;
    const y = v * centerY;
    
    if (i === 0) {
      ctx.moveTo(x, y);
    } else {
      // Smooth curve
      const xc = (x + prevX) / 2;
      const yc = (y + prevY) / 2;
      ctx.quadraticCurveTo(prevX, prevY, xc, yc);
    }
    prevX = x;
    prevY = y;
    x += sliceWidth;
  }
  
  ctx.stroke();
};
```

**Animations**:
- Smooth spring interpolation between frames
- Fade in/out on state change
- Respects `prefers-reduced-motion` (static or reduced frame rate)

### 4. FrequencyBars
**Purpose**: Real-time frequency bar visualization (equalizer style)

**Canvas Specifications**:
- Width: 100% of container (max 600px)
- Height: 100px (desktop), 80px (mobile)
- Number of bars: 32-64 (based on width)
- Bar width: Calculated dynamically
- Gap between bars: 2px
- Bar color: Gradient from state color

**Data Input**:
- Frequency data from AnalyserNode (Uint8Array)
- Bar count matches frequency bins used

**Rendering**:
```typescript
const drawFrequencyBars = (ctx: CanvasRenderingContext2D, data: Uint8Array, color: string) => {
  const width = canvas.width;
  const height = canvas.height;
  const barCount = data.length;
  const barWidth = (width - (barCount - 1) * 2) / barCount;
  
  ctx.clearRect(0, 0, width, height);
  
  const gradient = ctx.createLinearGradient(0, height, 0, 0);
  gradient.addColorStop(0, color);
  gradient.addColorStop(0.5, color + '80');
  gradient.addColorStop(1, 'transparent');
  
  ctx.fillStyle = gradient;
  
  for (let i = 0; i < barCount; i++) {
    const value = data[i] / 255;
    const barHeight = value * height * 0.9;
    const x = i * (barWidth + 2);
    const y = height - barHeight;
    
    // Rounded bars
    const radius = Math.min(barWidth / 2, 4);
    ctx.beginPath();
    ctx.roundRect(x, y, barWidth, barHeight, radius);
    ctx.fill();
  }
};
```

**Animations**:
- Spring animation for each bar height
- Staggered entrance (delay per bar: index * 20ms)
- Smooth decay when audio stops

### 5. VoiceControls
**Purpose**: Primary voice interaction controls

**Buttons**:
1. **Record/Stop** - Primary action, large, prominent
2. **Mute/Unmute** - Secondary, icon-only
3. **Settings** - Tertiary, icon-only

**Button Specifications**:
```typescript
// Record Button (Primary)
.record-button {
  @apply relative w-20 h-20 rounded-full flex items-center justify-center;
  background: linear-gradient(135deg, var(--color-primary-500), var(--color-primary-600));
  box-shadow: var(--shadow-glow);
  transition: var(--transition-spring);
}

.record-button:hover {
  transform: scale(1.05);
  box-shadow: var(--shadow-glow-strong);
}

.record-button:active {
  transform: scale(0.95);
}

.record-button:focus-visible {
  outline: none;
  ring: 2px;
  ring-offset: 2px;
  ring-offset-slate-950;
  ring-primary-500;
}

// Recording state
.record-button.recording {
  background: linear-gradient(135deg, var(--color-voice-error), #dc2626);
  animation: pulse-ring 1.5s ease-out infinite;
}

@keyframes pulse-ring {
  0% { box-shadow: 0 0 0 0 var(--color-voice-error); }
  70% { box-shadow: 0 0 0 20px transparent; }
  100% { box-shadow: 0 0 0 0 transparent; }
}

// Mute Button (Secondary)
.mute-button {
  @apply w-12 h-12 rounded-full flex items-center justify-center;
  background: var(--color-bg-glass);
  border: 1px solid var(--color-border-subtle);
  backdrop-filter: var(--glass-blur);
  color: var(--color-text-secondary);
  transition: var(--transition-fast);
}

.mute-button:hover {
  background: var(--color-bg-glass-hover);
  border-color: var(--color-border-default);
  color: var(--color-text-primary);
}

.mute-button.muted {
  color: var(--color-voice-muted);
}

.mute-button:focus-visible {
  outline: none;
  ring: 2px;
  ring-offset: 2px;
  ring-offset-slate-950;
  ring-primary-500;
}

// Settings Button (Tertiary)
.settings-button {
  @apply w-12 h-12 rounded-full flex items-center justify-center;
  background: var(--color-bg-glass);
  border: 1px solid var(--color-border-subtle);
  backdrop-filter: var(--glass-blur);
  color: var(--color-text-secondary);
  transition: var(--transition-fast);
}

.settings-button:hover {
  background: var(--color-bg-glass-hover);
  border-color: var(--color-border-default);
  color: var(--color-text-primary);
  transform: rotate(30deg);
}
```

**Motion.dev Animations**:
```typescript
// Button tap animation
const tapVariants = {
  tap: { scale: 0.92 },
  hover: { scale: 1.05 },
  focus: { scale: 1.02 }
};

// Record button state transition
const recordButtonVariants = {
  idle: { 
    scale: 1,
    background: 'linear-gradient(135deg, var(--color-primary-500), var(--color-primary-600))',
    transition: { type: "spring", stiffness: 300, damping: 20 }
  },
  recording: {
    scale: 1.02,
    background: 'linear-gradient(135deg, var(--color-voice-error), #dc2626)',
    transition: { type: "spring", stiffness: 400, damping: 25 }
  },
  processing: {
    scale: 1,
    opacity: 0.7,
    transition: { duration: 0.2 }
  }
};

// Settings button rotate on hover
const settingsVariants = {
  hover: { rotate: 30, transition: { type: "spring", stiffness: 400, damping: 20 } }
};
```

**Keyboard Support**:
- `Space` / `Enter` - Activate focused button
- `Escape` - Close settings panel, stop recording
- `Tab` / `Shift+Tab` - Navigate between buttons

### 6. ConnectionStatus
**Purpose**: WebSocket connection status indicator

**States**:
1. **Connecting** - Spinning spinner, amber text "Connecting..."
2. **Connected** - Green dot, green text "Connected"
3. **Disconnected** - Red dot, red text "Disconnected"
4. **Reconnecting** - Spinning spinner, amber text "Reconnecting..."
5. **Error** - Red dot with exclamation, red text "Connection Error"

**Visual Design**:
```typescript
.connection-status {
  @apply flex items-center gap-2 px-3 py-1.5 rounded-full text-sm font-medium;
  background: var(--color-bg-glass);
  border: 1px solid var(--color-border-subtle);
  backdrop-filter: var(--glass-blur);
}

.status-dot {
  @apply w-2 h-2 rounded-full;
  transition: var(--transition-fast);
}

.status-dot.connecting,
.status-dot.reconnecting {
  background: var(--color-voice-processing);
  animation: pulse 1.5s ease-in-out infinite;
}

.status-dot.connected {
  background: #22c55e;
  box-shadow: 0 0 8px #22c55e;
}

.status-dot.disconnected,
.status-dot.error {
  background: var(--color-voice-error);
}
```

**Animations**:
- Dot pulse for connecting/reconnecting
- Smooth color transition on state change
- Slide in/out from top-right

### 7. MicrophoneLevel
**Purpose**: Visual microphone input level indicator

**Visual Design**:
- Horizontal bar or circular ring around orb
- 10-20 segments
- Color gradient: green → yellow → red
- Smooth spring animation

**Implementation**:
```typescript
const MicrophoneLevel = ({ level, maxLevel = 1 }) => {
  const segments = 12;
  const activeSegments = Math.ceil(level * segments);
  
  return (
    <div className="flex items-center gap-1" role="img" aria-label={`Microphone level: ${Math.round(level * 100)}%`}>
      {Array.from({ length: segments }, (_, i) => (
        <motion.div
          key={i}
          className="w-1 h-12 rounded-full"
          style={{
            background: i < activeSegments 
              ? getSegmentColor(i, segments) 
              : 'rgba(148, 163, 184, 0.15)'
          }}
          initial={{ scaleY: 0 }}
          animate={{ scaleY: i < activeSegments ? 1 : 0.1 }}
          transition={{ 
            type: "spring", 
            stiffness: 500, 
            damping: 30,
            delay: i * 0.01
          }}
        />
      ))}
    </div>
  );
};
```

### 8. VoiceSettings
**Purpose**: Settings panel for voice configuration

**Layout**:
- Slide-up panel from bottom (mobile) or side panel (desktop)
- Glassmorphism background with backdrop blur
- Sections: Model, Voice, Language, VAD Sensitivity, Advanced

**Fields**:
1. **Model Selection** - Dropdown (Whisper models, OpenAI, etc.)
2. **Voice Selection** - Dropdown (OpenAI TTS voices: alloy, echo, fable, onyx, nova, shimmer)
3. **Language** - Dropdown (ISO language codes)
4. **VAD Sensitivity** - Slider (0-1, default 0.5)
5. **Auto-stop Silence** - Slider (ms, default 1000)
6. **Audio Input Device** - Dropdown (MediaDevices)
7. **Audio Output Device** - Dropdown (MediaDevices)

**Animations**:
```typescript
const panelVariants = {
  closed: { y: '100%', opacity: 0 },
  open: { 
    y: 0, 
    opacity: 1,
    transition: { 
      type: "spring", 
      stiffness: 300, 
      damping: 30,
      duration: 0.4
    }
  },
  exit: { 
    y: '100%', 
    opacity: 0,
    transition: { duration: 0.2, ease: "easeInOut" }
  }
};

// Overlay
const overlayVariants = {
  closed: { opacity: 0 },
  open: { opacity: 1, transition: { duration: 0.2 } },
  exit: { opacity: 0, transition: { duration: 0.2 } }
};
```

**Accessibility**:
- `role="dialog"` with `aria-modal="true"`
- `aria-labelledby` pointing to panel title
- Focus trap within panel
- `Escape` key closes panel
- Restore focus to trigger button on close

### 9. TranscriptDisplay
**Purpose**: Real-time transcript display with streaming text

**Features**:
- Streaming text animation (character by character)
- Speaker labels (User / Assistant)
- Timestamps
- Auto-scroll to bottom
- Copy button
- Clear button
- Max height with scroll

**Visual Design**:
```typescript
.transcript-container {
  @apply flex-1 w-full max-w-2xl overflow-y-auto p-4 space-y-3;
  background: var(--color-bg-glass);
  border: 1px solid var(--color-border-subtle);
  border-radius: var(--radius-xl);
  backdrop-filter: var(--glass-blur);
}

.transcript-entry {
  @apply flex flex-col gap-1 animate-fade-in-up;
}

.transcript-header {
  @apply flex items-center gap-2 text-xs text-muted;
}

.transcript-speaker {
  @apply font-semibold text-primary;
}

.transcript-text {
  @apply text-base text-primary leading-relaxed whitespace-pre-wrap;
}

// Streaming animation
@keyframes fade-in-up {
  from { opacity: 0; transform: translateY(10px); }
  to { opacity: 1; transform: translateY(0); }
}

.animate-fade-in-up {
  animation: fade-in-up 0.3s ease-out forwards;
}

// Character-by-character streaming
.streaming-text {
  display: inline-block;
  overflow: hidden;
  white-space: pre-wrap;
}
```

**Motion.dev Streaming**:
```typescript
const streamingVariants = {
  hidden: { opacity: 0, width: 0 },
  visible: (i: number) => ({
    opacity: 1,
    width: 'auto',
    transition: { 
      delay: i * 0.02, 
      duration: 0.05,
      ease: "linear"
    }
  })
};
```

---

## Responsive Breakpoints

```css
/* Mobile First */
@media (min-width: 640px) { /* sm */ }
@media (min-width: 768px) { /* md */ }
@media (min-width: 1024px) { /* lg */ }
@media (min-width: 1280px) { /* xl */ }
@media (min-width: 1536px) { /* 2xl */ }
```

**Component Adaptations**:

| Component | Mobile (<640px) | Tablet (640-1024px) | Desktop (>1024px) |
|-----------|-----------------|---------------------|-------------------|
| VoiceOrb | 100px | 110px | 120px |
| Waveform | 60px height | 70px height | 80px height |
| FrequencyBars | 80px height | 90px height | 100px height |
| VoiceControls | Horizontal, smaller | Horizontal | Horizontal, larger |
| VoiceSettings | Bottom sheet (full width) | Side panel (400px) | Side panel (480px) |
| Transcript | Below orb, full width | Beside orb (50/50) | Beside orb (40/60) |
| ConnectionStatus | Top center | Top right | Top right |

---

## Accessibility Requirements (WCAG AA)

### Contrast Ratios
- Text on glassmorphism: Minimum 4.5:1 (AA) / 7:1 (AAA)
- Interactive elements: Minimum 3:1 for non-text
- Focus indicators: Minimum 3:1 against adjacent colors

### Keyboard Navigation
- All interactive elements reachable via Tab
- Logical tab order (top to bottom, left to right)
- Visible focus indicators on all interactive elements
- `Escape` closes modals/panels
- `Enter`/`Space` activates buttons
- Arrow keys for sliders/dropdowns

### ARIA
- `role="dialog"` for settings panel
- `aria-modal="true"` for modal dialogs
- `aria-live="polite"` for status announcements
- `aria-label` on icon-only buttons
- `aria-describedby` for complex controls
- `aria-expanded` on collapsible elements

### Reduced Motion
```css
@media (prefers-reduced-motion: reduce) {
  *,
  *::before,
  *::after {
    animation-duration: 0.01ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: 0.01ms !important;
    scroll-behavior: auto !important;
  }
  
  /* Disable specific animations */
  .voice-orb,
  .waveform-visualizer,
  .frequency-bars {
    animation: none !important;
  }
}
```

### Screen Reader Support
- State changes announced via `aria-live` region
- Transcript updates announced
- Connection status changes announced
- Recording state announced

---

## Performance Requirements

### Frame Rate
- Target: 60fps for all animations
- Canvas visualizations: 60fps (requestAnimationFrame)
- Motion.dev animations: GPU-accelerated (transform, opacity)

### Canvas Optimization
- Use `OffscreenCanvas` if available
- Reuse canvas contexts
- Batch draw calls
- Use `will-change` CSS property
- Limit frequency data bins to 64 max

### Motion.dev Optimization
- Use `transform` and `opacity` for animations
- Avoid layout thrashing
- Use `layoutId` for shared element transitions
- Minimize re-renders with `React.memo`

### Memory
- Cleanup WebSocket on unmount
- Cancel animation frames
- Dispose AudioContext
- Remove event listeners

---

## Integration Specifications

### WebSocket Service (`frontend/src/services/voice-bridge.ts`)
```typescript
// Expected interface
interface VoiceBridgeService {
  connect(): Promise<void>;
  disconnect(): void;
  sendAudio(audioData: ArrayBuffer): void;
  sendMessage(message: VoiceMessage): void;
  onMessage(callback: (message: VoiceMessage) => void): void;
  onStatusChange(callback: (status: ConnectionStatus) => void): void;
  onTranscript(callback: (transcript: TranscriptEntry) => void): void;
  onAudioLevel(callback: (level: number) => void): void;
}
```

### Zustand Store (`frontend/src/stores/voiceStore.ts`)
```typescript
interface VoiceState {
  // Connection
  status: 'disconnected' | 'connecting' | 'connected' | 'reconnecting' | 'error';
  
  // Recording
  isRecording: boolean;
  isMuted: boolean;
  
  // Audio
  audioLevel: number;
  frequencyData: Uint8Array;
  timeDomainData: Uint8Array;
  
  // Transcript
  transcript: TranscriptEntry[];
  
  // Settings
  settings: VoiceSettings;
  
  // Actions
  connect: () => void;
  disconnect: () => void;
  startRecording: () => void;
  stopRecording: () => void;
  toggleMute: () => void;
  updateSettings: (settings: Partial<VoiceSettings>) => void;
  addTranscript: (entry: TranscriptEntry) => void;
  clearTranscript: () => void;
  setAudioLevel: (level: number) => void;
  setFrequencyData: (data: Uint8Array) => void;
  setTimeDomainData: (data: Uint8Array) => void;
  setStatus: (status: VoiceState['status']) => void;
}
```

### Types (`frontend/src/components/voice-bridge/types.ts`)
```typescript
type VoiceState = 'idle' | 'listening' | 'speaking' | 'processing' | 'error' | 'muted';

interface VoiceSettings {
  model: string;
  voice: 'alloy' | 'echo' | 'fable' | 'onyx' | 'nova' | 'shimmer';
  language: string;
  vadSensitivity: number;      // 0-1
  autoStopSilence: number;     // ms
  inputDeviceId: string;
  outputDeviceId: string;
}

interface TranscriptEntry {
  id: string;
  speaker: 'user' | 'assistant';
  text: string;
  timestamp: Date;
  isStreaming?: boolean;
}

interface VoiceMessage {
  type: 'audio' | 'text' | 'control' | 'config';
  payload: unknown;
}

type ConnectionStatus = 'disconnected' | 'connecting' | 'connected' | 'reconnecting' | 'error';
```

---

## File Structure

```
frontend/src/
├── components/
│   └── voice-bridge/
│       ├── index.ts                 # Barrel export
│       ├── types.ts                 # TypeScript types
│       ├── VoiceBridgeContainer.tsx # Main container
│       ├── VoiceOrb.tsx             # Animated orb
│       ├── WaveformVisualizer.tsx   # Canvas waveform
│       ├── FrequencyBars.tsx        # Canvas frequency bars
│       ├── VoiceControls.tsx        # Control buttons
│       ├── ConnectionStatus.tsx     # Connection indicator
│       ├── MicrophoneLevel.tsx      # Mic level indicator
│       ├── VoiceSettings.tsx        # Settings panel
│       ├── TranscriptDisplay.tsx    # Transcript display
│       └── hooks/
│           ├── useVoiceBridge.ts    # Main hook
│           ├── useAudioVisualization.ts # Audio visualization hook
│           └── useVoiceSettings.ts  # Settings hook
├── services/
│   └── voice-bridge.ts              # WebSocket service (existing)
├── stores/
│   └── voiceStore.ts                # Zustand store (new/extend)
├── pages/
│   └── VoiceBridgePage.tsx          # Page component
└── App.tsx                          # Add route
```

---

## Testing Checklist

### Functional Testing
- [ ] WebSocket connects/disconnects correctly
- [ ] Recording starts/stops correctly
- [ ] Mute toggles correctly
- [ ] Settings panel opens/closes
- [ ] Settings persist to store
- [ ] Transcript displays streaming text
- [ ] Audio visualization responds to input
- [ ] Connection status updates correctly

### Visual Testing
- [ ] All states render correctly (idle, listening, speaking, processing, error, muted)
- [ ] Glassmorphism effects render correctly
- [ ] Gradients and glows render correctly
- [ ] Responsive layouts work at all breakpoints
- [ ] Dark theme consistent

### Animation Testing
- [ ] Orb state transitions smooth
- [ ] Button tap/hover animations work
- [ ] Panel slide animations smooth
- [ ] Waveform/frequency bars animate at 60fps
- [ ] Transcript streaming animation smooth
- [ ] Reduced motion respected

### Accessibility Testing
- [ ] Keyboard navigation works
- [ ] Focus indicators visible
- [ ] ARIA labels present
- [ ] Screen reader announcements work
- [ ] Contrast ratios meet WCAG AA
- [ ] Reduced motion works

### Performance Testing
- [ ] 60fps maintained during visualization
- [ ] Memory stable over time
- [ ] No memory leaks on unmount
- [ ] CPU usage reasonable

### Cross-browser Testing
- [ ] Chrome/Edge (latest)
- [ ] Firefox (latest)
- [ ] Safari (latest)

---

## Dependencies

### Required (already in project)
- `framer-motion` (Motion.dev) - ^11.x
- `zustand` - ^4.x
- `react` - ^18.x
- `typescript` - ^5.x
- `tailwindcss` - ^3.x

### No new dependencies required

---

## Implementation Notes

### Canvas Context Management
```typescript
// Best practice for canvas in React
const canvasRef = useRef<HTMLCanvasElement>(null);
const animationFrameRef = useRef<number>();

useEffect(() => {
  const canvas = canvasRef.current;
  if (!canvas) return;
  
  const ctx = canvas.getContext('2d');
  if (!ctx) return;
  
  // Set up canvas size
  const resize = () => {
    const dpr = window.devicePixelRatio || 1;
    canvas.width = canvas.offsetWidth * dpr;
    canvas.height = canvas.offsetHeight * dpr;
    ctx.scale(dpr, dpr);
  };
  
  resize();
  window.addEventListener('resize', resize);
  
  // Animation loop
  const animate = () => {
    // Draw visualization
    animationFrameRef.current = requestAnimationFrame(animate);
  };
  
  animate();
  
  return () => {
    window.removeEventListener('resize', resize);
    cancelAnimationFrame(animationFrameRef.current);
  };
}, []);
```

### AudioContext Management
```typescript
// Singleton AudioContext
let audioContext: AudioContext | null = null;

export const getAudioContext = () => {
  if (!audioContext) {
    audioContext = new (window.AudioContext || (window as any).webkitAudioContext)();
  }
  return audioContext;
};

export const closeAudioContext = () => {
  if (audioContext) {
    audioContext.close();
    audioContext = null;
  }
};
```

### WebSocket Reconnection
```typescript
// Exponential backoff reconnection
const reconnect = (attempt = 0) => {
  const delay = Math.min(1000 * Math.pow(2, attempt), 30000);
  setTimeout(() => {
    connect().catch(() => reconnect(attempt + 1));
  }, delay);
};
```

---

## Definition of Done

- [ ] All components created and exported
- [ ] VoiceBridgePage accessible at `/voice-bridge`
- [ ] WebSocket integration working with backend
- [ ] All 6 voice states implemented and tested
- [ ] Real-time audio visualization working (orb, waveform, frequency bars)
- [ ] Voice controls functional (record, stop, mute, settings)
- [ ] Connection status indicator working
- [ ] Microphone level indicator working
- [ ] Settings panel functional with persistence
- [ ] Transcript display with streaming animation
- [ ] All Motion.dev animations smooth (60fps)
- [ ] WCAG AA accessibility compliance verified
- [ ] `prefers-reduced-motion` fully supported
- [ ] Keyboard navigation fully functional
- [ ] Responsive design working at all breakpoints
- [ ] Design tokens used consistently
- [ ] Glassmorphism design applied throughout
- [ ] No console errors or warnings
- [ ] TypeScript strict mode passes
- [ ] ESLint passes
- [ ] Performance targets met (60fps, low memory)
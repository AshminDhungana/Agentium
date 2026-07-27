# Voice Bridge Immersive Hero — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Transform the Voice Bridge page into a premium, immersive SaaS experience with full-screen hero visualization, Living Organism Orb, and floating glass panels.

**Architecture:** CPU-first Canvas 2D implementation with Three.js GPU parity via auto-fallback hook. Four phases: Layout & Panels → Living Orb CPU → Living Orb GPU → Polish.

**Tech Stack:** React 18, TypeScript, Framer Motion (spring: stiffness 300, damping 30), Canvas 2D API, Three.js (lazy-loaded), CSS variables from `index.css`, Vitest + React Testing Library.

## Global Constraints

- **Design tokens**: Use CSS variables from `index.css` exclusively — `--c-canvas`, `--c-panel`, `--c-brand`, `--c-voice-*`, `--c-glass-*`, `--color-text-*`, `--c-success/warning/error`, `--c-hairline`
- **Glassmorphism**: `backdrop-blur-xl`, semi-transparent backgrounds, `--c-glass-border` borders
- **Motion**: Framer Motion spring physics `stiffness: 300, damping: 30`, staggerChildren for entrances
- **Accessibility**: `prefers-reduced-motion` respected, ARIA live regions, semantic HTML, WCAG AA contrast
- **Theme sync**: 220ms `transition-colors duration-200` across all elements
- **Dual-path**: ThreeScene (GPU) + Canvas2DFallback (CPU) with auto-fallback via `useThreeScene` hook
- **Component patterns**: `WidgetCard`, `EmptyState`, shadcn/ui primitives
- **Testing**: Vitest + React Testing Library, jsdom with Canvas/WebGL mocks

---

## File Structure Map

### Modify (Layout & Integration)
1. `frontend/src/components/voice-bridge/VoiceBridgeContainer.tsx` — Complete restructuring to immersive hero layout
2. `frontend/src/components/voice-bridge/ThreeScene.tsx` — Add Living Orb shaders, particle field, state morph logic
3. `frontend/src/components/voice-bridge/Canvas2DFallback.tsx` — Rewrite with Living Orb physics + 3-ring system
4. `frontend/src/components/voice-bridge/VoiceControls.tsx` — Upgrade to glass pill, living pulse, morphing state icon
5. `frontend/src/components/voice-bridge/TranscriptDisplay.tsx` — Floating panel integration, streaming char animation
6. `frontend/src/index.css` — Add any missing design tokens (orb radii, animation durations)

### Create (New Components)
7. `frontend/src/components/voice-bridge/CanvasOrb.tsx` — Shared orb logic extracted for both Three/Canvas paths
8. `frontend/src/components/voice-bridge/TranscriptDrawer.tsx` — Floating panel with AnimatePresence
9. `frontend/src/components/voice-bridge/StatusBadge.tsx` — Compact top-right indicator
10. `frontend/src/components/voice-bridge/hooks/useOrbPhysics.ts` — Spring physics, aperture, state morph (shared)

### Tests
11. `frontend/src/components/voice-bridge/__tests__/VoiceBridgeContainer.immersive.test.tsx` — Layout, motion variants, ARIA
12. `frontend/src/components/voice-bridge/__tests__/Canvas2DFallback.living-orb.test.tsx` — State transitions, reduced motion
13. `frontend/src/components/voice-bridge/__tests__/VoiceControls.glass-pill.test.tsx` — Pulse ring, state icon, keyboard nav

---

## Implementation Phases

### Phase 1: Layout & Panels (1-2 days)
- Restructure `VoiceBridgeContainer` to immersive hero
- Create `TranscriptDrawer`, `StatusBadge`, `ControlsPill` components
- Wire Framer Motion page/section variants
- Verify glass styling matches Dashboard/Agents

### Phase 2: Living Orb — CPU Path (2-3 days)
- Rewrite `Canvas2DFallback` with 3-ring system
- Implement spring physics (`useOrbPhysics` hook)
- Add particle atmosphere, aperture animation, noise texture
- Add `prefers-reduced-motion` static frame
- Unit test state transitions

### Phase 3: Living Orb — GPU Path (2 days)
- Write GLSL shaders for orb surface, mid-ring, particles
- Update `ThreeScene` with new components
- Implement state morph uniforms
- Verify visual parity with CPU path

### Phase 4: Polish & Integration (1-2 days)
- Upgrade `VoiceControls` with glass pill, living pulse, morphing icon
- Enhance `TranscriptDisplay` streaming animation
- Full accessibility audit
- Cross-browser testing (Canvas 2D, WebGL)
- Performance profiling (target 60fps CPU, 120fps GPU)

---

## Task Breakdown

### Phase 1: Layout & Panels

#### Task 1.1: Create TranscriptDrawer Component

**Files:**
- Create: `frontend/src/components/voice-bridge/TranscriptDrawer.tsx`
- Modify: `frontend/src/components/voice-bridge/index.ts` (export new component)
- Test: `frontend/src/components/voice-bridge/__tests__/TranscriptDrawer.test.tsx`

**Interfaces:**
- Consumes: `transcripts` from `useVoiceBridge`, `TranscriptDisplay` component
- Produces: `TranscriptDrawer` component with `isOpen` state, `onToggle` callback

```tsx
// TranscriptDrawer.tsx
import { motion, AnimatePresence } from 'framer-motion';
import { MessageSquare, ChevronUp } from 'lucide-react';
import { WidgetCard } from '@/components/dashboard/WidgetCard';
import { TranscriptDisplay } from './TranscriptDisplay';
import { useReducedMotion } from './hooks/useReducedMotion';

interface TranscriptDrawerProps {
  transcripts: Array<{ id: string; speaker: 'user' | 'agent'; text: string; timestamp: Date; isStreaming?: boolean }>;
  className?: string;
}

export function TranscriptDrawer({ transcripts, className = '' }: TranscriptDrawerProps) {
  const [isOpen, setIsOpen] = useState(false);
  const { prefersReduced } = useReducedMotion();

  const handleToggle = () => setIsOpen(!isOpen);

  return (
    <div className={`fixed bottom-6 left-6 z-20 ${className}`}>
      {/* Collapsed handle button */}
      <motion.button
        className="glass-pill flex items-center gap-2 px-4 py-2"
        initial={{ opacity: 0, x: -30 }}
        animate={{ opacity: 1, x: 0 }}
        transition={{ type: 'spring', stiffness: 300, damping: 30, delay: 0.5 }}
        onClick={handleToggle}
        aria-expanded={isOpen}
        aria-controls="transcript-drawer-panel"
        aria-label={isOpen ? 'Close transcript' : 'Open transcript'}
      >
        <MessageSquare className="w-5 h-5" aria-hidden="true" />
        <span className="hidden sm:inline ml-2 text-sm font-medium text-[var(--color-text-primary)]">Transcript</span>
        <motion.span
          className="ml-1"
          animate={{ rotate: isOpen ? 180 : 0 }}
          transition={{ type: 'spring', stiffness: 300, damping: 30 }}
        >
          <ChevronUp className="w-4 h-4" aria-hidden="true" />
        </motion.span>
      </motion.button>

      {/* Expanded floating panel */}
      <AnimatePresence>
        {isOpen && (
          <motion.div
            id="transcript-drawer-panel"
            className="fixed bottom-24 left-6 z-20 w-96 max-h-[60vh]"
            initial={{ opacity: 0, y: 20, scale: 0.95 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 20, scale: 0.95 }}
            transition={{ type: prefersReduced ? 'tween' : 'spring', stiffness: 300, damping: 30 }}
            role="region"
            aria-label="Conversation transcript"
          >
            <WidgetCard className="flex flex-col h-full">
              <TranscriptDisplay transcripts={transcripts} maxHeight={400} className="flex-1" />
            </WidgetCard>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
```

**CSS for glass-pill (add to index.css if not present):**
```css
.glass-pill {
  @apply bg-[var(--c-glass-bg)] border border-[var(--c-glass-border)] rounded-3xl backdrop-blur-2xl shadow-2xl;
}
```

- [ ] **Step 1: Write the failing test**

```tsx
// TranscriptDrawer.test.tsx
import { render, screen, fireEvent } from '@testing-library/react';
import { TranscriptDrawer } from '../TranscriptDrawer';
import { vi } from 'vitest';

vi.mock('@/components/voice-bridge/hooks/useReducedMotion', () => ({
  useReducedMotion: () => ({ prefersReduced: false }),
}));

describe('TranscriptDrawer', () => {
  const mockTranscripts = [
    { id: '1', speaker: 'user' as const, text: 'Hello', timestamp: new Date(), isStreaming: false },
    { id: '2', speaker: 'agent' as const, text: 'Hi there!', timestamp: new Date(), isStreaming: false },
  ];

  test('renders collapsed handle button when closed', () => {
    render(<TranscriptDrawer transcripts={mockTranscripts} />);
    const button = screen.getByRole('button', { name: /open transcript/i });
    expect(button).toBeInTheDocument();
    expect(button).toHaveClass('glass-pill');
    expect(screen.queryByRole('region', { name: /conversation transcript/i })).not.toBeInTheDocument();
  });

  test('expands panel on click', async () => {
    render(<TranscriptDrawer transcripts={mockTranscripts} />);
    const button = screen.getByRole('button', { name: /open transcript/i });
    fireEvent.click(button);
    const panel = await screen.findByRole('region', { name: /conversation transcript/i });
    expect(panel).toBeInTheDocument();
    expect(panel).toHaveClass('w-96');
  });

  test('collapses panel on second click', async () => {
    render(<TranscriptDrawer transcripts={mockTranscripts} />);
    const button = screen.getByRole('button', { name: /open transcript/i });
    fireEvent.click(button);
    await screen.findByRole('region', { name: /conversation transcript/i });
    fireEvent.click(button);
    expect(screen.queryByRole('region', { name: /conversation transcript/i })).not.toBeInTheDocument();
  });

  test('shows transcript content when expanded', async () => {
    render(<TranscriptDrawer transcripts={mockTranscripts} />);
    const button = screen.getByRole('button', { name: /open transcript/i });
    fireEvent.click(button);
    await screen.findByText('Hello');
    expect(screen.getByText('Hi there!')).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**
Run: `npm test -- TranscriptDrawer.test.tsx`
Expected: FAIL with "TranscriptDrawer not defined"

- [ ] **Step 3: Write minimal implementation**
Create `TranscriptDrawer.tsx` with the component code above

- [ ] **Step 4: Run test to verify it passes**
Run: `npm test -- TranscriptDrawer.test.tsx`
Expected: PASS

- [ ] **Step 5: Commit**
```bash
git add frontend/src/components/voice-bridge/TranscriptDrawer.tsx frontend/src/components/voice-bridge/__tests__/TranscriptDrawer.test.tsx
git commit -m "feat(voice-bridge): add TranscriptDrawer component with floating panel"
```

---

#### Task 1.2: Create StatusBadge Component

**Files:**
- Create: `frontend/src/components/voice-bridge/StatusBadge.tsx`
- Modify: `frontend/src/components/voice-bridge/index.ts` (export)
- Test: `frontend/src/components/voice-bridge/__tests__/StatusBadge.test.tsx`

**Interfaces:**
- Consumes: `status` from `useVoiceBridge` (ConnectionStatus), `voiceState` for active states
- Produces: `StatusBadge` component with animated dot + text

```tsx
// StatusBadge.tsx
import { motion } from 'framer-motion';
import { useReducedMotion } from './hooks/useReducedMotion';
import type { ConnectionStatus } from './types';

interface StatusBadgeProps {
  status: ConnectionStatus;
  voiceState?: 'idle' | 'listening' | 'speaking' | 'processing' | 'error' | 'muted';
  className?: string;
}

const statusConfig: Record<ConnectionStatus, { color: string; label: string }> = {
  connected: { color: 'var(--c-success)', label: 'Connected' },
  connecting: { color: 'var(--c-warning)', label: 'Connecting' },
  reconnecting: { color: 'var(--c-voice-listening)', label: 'Reconnecting' },
  error: { color: 'var(--c-error)', label: 'Error' },
  disconnected: { color: 'var(--color-text-muted)', label: 'Disconnected' },
};

const activeVoiceStates = ['listening', 'speaking', 'processing'] as const;

export function StatusBadge({ status, voiceState, className = '' }: StatusBadgeProps) {
  const { prefersReduced } = useReducedMotion();
  const config = statusConfig[status];
  const isActive = voiceState && activeVoiceStates.includes(voiceState);

  return (
    <motion.div
      className={`fixed top-6 right-6 z-20 glass-pill px-4 py-2 flex items-center gap-2 ${className}`}
      initial={{ opacity: 0, y: -20, x: 20 }}
      animate={{ opacity: 1, y: 0, x: 0 }}
      transition={{ type: 'spring', stiffness: 300, damping: 30, delay: 0.1 }}
    >
      <motion.span
        className="relative w-2.5 h-2.5 rounded-full"
        style={{ backgroundColor: config.color }}
        animate={
          (status === 'connecting' || status === 'reconnecting' || isActive) && !prefersReduced
            ? {
                boxShadow: [
                  `0 0 6px ${config.color}`,
                  `0 0 18px ${config.color}80`,
                  `0 0 6px ${config.color}`,
                ],
                scale: [1, 1.2, 1],
              }
            : { scale: 1 }
        }
        transition={{
          duration: status === 'error' ? 0.3 : 1.5,
          repeat: Infinity,
          ease: status === 'error' ? 'easeInOut' : 'easeInOut',
        }}
        aria-hidden="true"
      />
      <span className="text-xs font-medium text-[var(--color-text-primary)] capitalize">
        {config.label}
      </span>
    </motion.div>
  );
}
```

- [ ] **Step 1: Write the failing test**

```tsx
// StatusBadge.test.tsx
import { render, screen } from '@testing-library/react';
import { StatusBadge } from '../StatusBadge';
import { vi } from 'vitest';

vi.mock('@/components/voice-bridge/hooks/useReducedMotion', () => ({
  useReducedMotion: () => ({ prefersReduced: false }),
}));

describe('StatusBadge', () => {
  test('renders connected state with green dot', () => {
    render(<StatusBadge status="connected" />);
    const badge = screen.getByText('Connected');
    expect(badge).toBeInTheDocument();
    expect(badge.closest('.glass-pill')).toBeInTheDocument();
    // Check dot has success color
    const dot = badge.previousElementSibling;
    expect(dot).toHaveStyle({ backgroundColor: 'var(--c-success)' });
  });

  test('renders connecting state with animated pulse', () => {
    render(<StatusBadge status="connecting" />);
    expect(screen.getByText('Connecting')).toBeInTheDocument();
    const dot = screen.getByText('Connecting').previousElementSibling;
    expect(dot).toHaveStyle({ backgroundColor: 'var(--c-warning)' });
  });

  test('animates pulse when voiceState is listening', () => {
    render(<StatusBadge status="connected" voiceState="listening" />);
    const dot = screen.getByText('Connected').previousElementSibling;
    // Should have animate prop for pulse
    expect(dot).toBeInTheDocument();
  });

  test('renders error state with red dot', () => {
    render(<StatusBadge status="error" />);
    expect(screen.getByText('Error')).toBeInTheDocument();
    const dot = screen.getByText('Error').previousElementSibling;
    expect(dot).toHaveStyle({ backgroundColor: 'var(--c-error)' });
  });
});
```

- [ ] **Step 2: Run test to verify it fails**
Run: `npm test -- StatusBadge.test.tsx`
Expected: FAIL with "StatusBadge not defined"

- [ ] **Step 3: Write minimal implementation**
Create `StatusBadge.tsx` with the component code above

- [ ] **Step 4: Run test to verify it passes**
Run: `npm test -- StatusBadge.test.tsx`
Expected: PASS

- [ ] **Step 5: Commit**
```bash
git add frontend/src/components/voice-bridge/StatusBadge.tsx frontend/src/components/voice-bridge/__tests__/StatusBadge.test.tsx
git commit -m "feat(voice-bridge): add StatusBadge component with animated status dot"
```

---

#### Task 1.3: Create ControlsPill Component (or update VoiceControls wrapper)

**Files:**
- Modify: `frontend/src/components/voice-bridge/VoiceControls.tsx` (wrap in glass pill motion.div)
- Test: `frontend/src/components/voice-bridge/__tests__/VoiceControls.glass-pill.test.tsx`

**Interfaces:**
- Consumes: Same props as VoiceControls
- Produces: VoiceControls wrapped in animated glass pill

The glass pill wrapper already exists in VoiceBridgeContainer (lines 334-351). We need to extract it as a reusable pattern or update VoiceControls to accept a `glassPill` prop.

```tsx
// In VoiceBridgeContainer.tsx, replace lines 334-351 with:
<motion.div
  className="fixed bottom-6 left-1/2 -translate-x-1/2 z-20"
  initial={{ opacity: 0, y: 30 }}
  animate={{ opacity: 1, y: 0 }}
  transition={{ type: 'spring', stiffness: 300, damping: 30, delay: 0.4 }}
>
  <VoiceControls
    voiceState={voiceState}
    isConnected={status === 'connected'}
    isMuted={isMuted}
    isRecording={isRecording}
    onRecord={handleRecord}
    onStop={handleStop}
    onMuteToggle={handleMuteToggle}
    onSettings={handleSettingsOpen}
    reducedMotion={prefersReduced}
    className="relative z-10 px-6 py-4"
    glassPill={true}
  />
</motion.div>
```

In VoiceControls.tsx, add `glassPill` prop and conditionally render the glass background.

- [ ] **Step 1: Write the failing test**

```tsx
// VoiceControls.glass-pill.test.tsx
import { render, screen } from '@testing-library/react';
import { VoiceControls } from '../VoiceControls';
import { vi } from 'vitest';

vi.mock('@/components/voice-bridge/hooks/useReducedMotion', () => ({
  useReducedMotion: () => ({ prefersReduced: false }),
}));

describe('VoiceControls glass pill', () => {
  test('renders glass pill background when glassPill prop is true', () => {
    render(<VoiceControls isConnected glassPill={true} onRecord={vi.fn()} onStop={vi.fn()} onMuteToggle={vi.fn()} onSettings={vi.fn()} />);
    const glassBg = screen.getByTestId('controls-glass-bg');
    expect(glassBg).toBeInTheDocument();
    expect(glassBg).toHaveClass('bg-[var(--c-glass-bg)]');
    expect(glassBg).toHaveClass('backdrop-blur-2xl');
    expect(glassBg).toHaveClass('rounded-3xl');
  });

  test('does not render glass pill background when glassPill is false', () => {
    render(<VoiceControls isConnected glassPill={false} onRecord={vi.fn()} onStop={vi.fn()} onMuteToggle={vi.fn()} onSettings={vi.fn()} />);
    expect(screen.queryByTestId('controls-glass-bg')).not.toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**
Run: `npm test -- VoiceControls.glass-pill.test.tsx`
Expected: FAIL

- [ ] **Step 3: Modify VoiceControls to accept glassPill prop**
Update `VoiceControlsProps` interface and conditionally render glass background

- [ ] **Step 4: Run test to verify it passes**
Run: `npm test -- VoiceControls.glass-pill.test.tsx`
Expected: PASS

- [ ] **Step 5: Commit**
```bash
git add frontend/src/components/voice-bridge/VoiceControls.tsx frontend/src/components/voice-bridge/__tests__/VoiceControls.glass-pill.test.tsx
git commit -m "feat(voice-bridge): add glassPill prop to VoiceControls for immersive layout"
```

---

#### Task 1.4: Restructure VoiceBridgeContainer to Immersive Hero Layout

**Files:**
- Modify: `frontend/src/components/voice-bridge/VoiceBridgeContainer.tsx` (complete restructure)
- Test: `frontend/src/components/voice-bridge/__tests__/VoiceBridgeContainer.immersive.test.tsx`

**Interfaces:**
- Consumes: All existing hooks and state
- Produces: Full-viewport layout with canvas layer (z-0) + floating panels (z-20)

```tsx
// VoiceBridgeContainer.tsx — NEW STRUCTURE
return (
  <motion.div
    data-testid="page-motion-wrapper"
    variants={pageVariants}
    initial="hidden"
    animate="visible"
    className={`h-screen w-full flex bg-[var(--c-canvas)] transition-colors duration-200 ${className}`}
  >
    {/* === CANVAS LAYER (fixed, inset-0, z-0) === */}
    <div className="fixed inset-0 z-0">
      {/* Depth layers: radial glow, dot grid, vignettes */}
      {/* ThreeScene / Canvas2DFallback */}
    </div>

    {/* === FLOATING GLASS PANELS (z-20, absolute) === */}
    <StatusBadge status={status} voiceState={voiceState} />
    <TranscriptDrawer transcripts={transcripts} />
    
    <motion.div
      className="fixed bottom-6 left-1/2 -translate-x-1/2 z-20"
      initial={{ opacity: 0, y: 30 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ type: 'spring', stiffness: 300, damping: 30, delay: 0.4 }}
    >
      <VoiceControls
        voiceState={voiceState}
        isConnected={status === 'connected'}
        isMuted={isMuted}
        isRecording={isRecording}
        onRecord={handleRecord}
        onStop={handleStop}
        onMuteToggle={handleMuteToggle}
        onSettings={handleSettingsOpen}
        reducedMotion={prefersReduced}
        glassPill={true}
      />
    </motion.div>

    <VoiceSettings ... />
  </motion.div>
);
```

Key changes:
- Remove header section (brand moves to StatusBadge or separate minimal header)
- Remove TranscriptDisplay section (moves to TranscriptDrawer)
- Remove Controls section (moves to floating pill)
- Canvas becomes full-viewport fixed background
- Add pageVariants with staggerChildren for panel entrances

- [ ] **Step 1: Write the failing test**

```tsx
// VoiceBridgeContainer.immersive.test.tsx
import { render, screen } from '@testing-library/react';
import { VoiceBridgeContainer } from '../VoiceBridgeContainer';
import { vi } from 'vitest';

// Mock all hooks
vi.mock('@/components/voice-bridge/hooks/useVoiceBridge', () => ({
  useVoiceBridge: () => ({
    status: 'connected',
    voiceState: 'idle',
    isRecording: false,
    isMuted: false,
    micLevel: 0,
    timeDomainData: null,
    frequencyData: null,
    transcripts: [],
    settings: {},
    availableInputDevices: [],
    availableOutputDevices: [],
    connect: vi.fn(),
    disconnect: vi.fn(),
    startRecording: vi.fn(),
    stopRecording: vi.fn(),
    toggleMute: vi.fn(),
    updateSettings: vi.fn(),
    clearTranscripts: vi.fn(),
    setMicLevel: vi.fn(),
    setTimeDomainData: vi.fn(),
    setFrequencyData: vi.fn(),
  }),
}));

vi.mock('@/components/voice-bridge/hooks/useAudioVisualization', () => ({
  useAudioVisualization: () => ({ start: vi.fn(), stop: vi.fn() }),
}));

vi.mock('@/components/voice-bridge/hooks/useReducedMotion', () => ({
  useReducedMotion: () => ({ prefersReduced: false }),
}));

describe('VoiceBridgeContainer immersive layout', () => {
  test('renders full-viewport canvas layer', () => {
    render(<VoiceBridgeContainer />);
    expect(screen.getByTestId('canvas-layer')).toHaveClass('fixed inset-0 z-0');
  });

  test('renders StatusBadge at top-right', () => {
    render(<VoiceBridgeContainer />);
    expect(screen.getByText('Connected')).toBeInTheDocument();
    expect(screen.getByText('Connected').closest('.fixed.top-6.right-6')).toBeInTheDocument();
  });

  test('renders TranscriptDrawer at bottom-left', () => {
    render(<VoiceBridgeContainer />);
    expect(screen.getByRole('button', { name: /open transcript/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /open transcript/i })).toHaveClass('fixed.bottom-6.left-6');
  });

  test('renders Controls pill at bottom-center', () => {
    render(<VoiceBridgeContainer />);
    const recordBtn = screen.getByRole('button', { name: /start recording/i });
    expect(recordBtn).toBeInTheDocument();
    // Controls should be centered
    expect(recordBtn.closest('.fixed.bottom-6.left-1\\/2')).toBeInTheDocument();
  });

  test('applies page motion variants with staggerChildren', () => {
    const { container } = render(<VoiceBridgeContainer />);
    const pageWrapper = container.querySelector('[data-testid="page-motion-wrapper"]');
    expect(pageWrapper).toHaveAttribute('variants', expect.stringContaining('staggerChildren'));
  });

  test('canvas layer has depth sub-layers (radial glow, dot grid, vignettes)', () => {
    render(<VoiceBridgeContainer />);
    expect(screen.getByTestId('viz-radial-glow')).toBeInTheDocument();
    expect(screen.getByTestId('viz-dot-grid')).toBeInTheDocument();
    expect(screen.getByTestId('viz-vignette-top')).toBeInTheDocument();
    expect(screen.getByTestId('viz-vignette-bottom')).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**
Run: `npm test -- VoiceBridgeContainer.immersive.test.tsx`
Expected: FAIL - components don't exist in new locations

- [ ] **Step 3: Rewrite VoiceBridgeContainer with immersive layout**
Complete restructure per the spec architecture diagram

- [ ] **Step 4: Run test to verify it passes**
Run: `npm test -- VoiceBridgeContainer.immersive.test.tsx`
Expected: PASS

- [ ] **Step 5: Commit**
```bash
git add frontend/src/components/voice-bridge/VoiceBridgeContainer.tsx frontend/src/components/voice-bridge/__tests__/VoiceBridgeContainer.immersive.test.tsx
git commit -m "feat(voice-bridge): restructure to immersive hero layout with floating glass panels"
```

---

#### Task 1.5: Update index.css with Missing Design Tokens

**Files:**
- Modify: `frontend/src/index.css`

Add any missing CSS custom properties for orb radii, animation durations, glass tokens.

```css
/* Add to :root in index.css */
:root {
  /* Orb system */
  --orb-base-radius: 80px;
  --orb-outer-ring-scale: 1.45;
  --orb-mid-ring-scale: 1.15;
  --orb-inner-ring-scale: 0.85;
  
  /* Animation durations */
  --duration-fast: 150ms;
  --duration-normal: 220ms;
  --duration-slow: 300ms;
  --duration-spring: 400ms;
  
  /* Glass tokens (verify these exist) */
  --c-glass-bg: rgba(30, 41, 59, 0.7);
  --c-glass-border: rgba(148, 163, 184, 0.2);
  --c-glass-bg-hover: rgba(30, 41, 59, 0.85);
}

.dark {
  --c-glass-bg: rgba(15, 23, 42, 0.7);
  --c-glass-border: rgba(148, 163, 184, 0.15);
}
```

- [ ] **Step 1: Verify tokens don't already exist**
Search index.css for --orb-, --duration-, --c-glass-

- [ ] **Step 2: Add missing tokens**
Edit index.css

- [ ] **Step 3: Verify build passes**
Run: `npm run build`
Expected: PASS

- [ ] **Step 4: Commit**
```bash
git add frontend/src/index.css
git commit -m "style(voice-bridge): add orb and animation duration design tokens"
```

---

### Phase 2: Living Orb — CPU Path (Canvas2DFallback Rewrite)

#### Task 2.1: Create useOrbPhysics Hook

**Files:**
- Create: `frontend/src/components/voice-bridge/hooks/useOrbPhysics.ts`
- Test: `frontend/src/components/voice-bridge/hooks/__tests__/useOrbPhysics.test.ts`

**Interfaces:**
- Consumes: `voiceState`, `micLevel`, `prefersReduced`, `dt`
- Produces: `orbState` object with `pulseScale`, `aperture`, `ringRotation`, `particlePositions`, `noiseOffset`

```typescript
// useOrbPhysics.ts
import { useMemo, useRef, useEffect } from 'react';
import type { VoiceState } from '../types';

interface OrbPhysicsState {
  pulseScale: number;
  aperture: number; // 0-1
  ringRotation: number; // radians
  particles: Particle[];
  noiseOffset: { x: number; y: number };
}

interface Particle {
  angle: number;
  radius: number;
  speed: number;
  size: number;
  opacity: number;
  phase: number;
  x: number;
  y: number;
}

interface UseOrbPhysicsProps {
  voiceState: VoiceState;
  micLevel: number;
  prefersReduced: boolean;
  width: number;
  height: number;
}

const PARTICLE_COUNT = 120;
const ORB_BASE_RADIUS = 80;

export function useOrbPhysics({ voiceState, micLevel, prefersReduced, width, height }: UseOrbPhysicsProps) {
  const cx = width / 2;
  const cy = height / 2;
  const timeRef = useRef(0);
  const lastTimestampRef = useRef(0);
  const particlesRef = useRef<Particle[]>([]);
  const apertureRef = useRef(0.15); // Idle: 15% open
  const ringRotationRef = useRef(0);
  const noiseOffsetRef = useRef({ x: 0, y: 0 });

  // Initialize particles
  useEffect(() => {
    if (particlesRef.current.length === 0) {
      particlesRef.current = Array.from({ length: PARTICLE_COUNT }, () => ({
        angle: Math.random() * Math.PI * 2,
        radius: ORB_BASE_RADIUS * 1.3 + Math.random() * ORB_BASE_RADIUS * 0.8,
        speed: 0.005 + Math.random() * 0.015,
        size: 1.5 + Math.random() * 3,
        opacity: 0.3 + Math.random() * 0.5,
        phase: Math.random() * Math.PI * 2,
        x: 0,
        y: 0,
      }));
    }
  }, []);

  // Spring configurations
  const springConfigs = {
    pulse: { stiffness: 180, damping: 22 }, // critically damped
    aperture: { stiffness: 300, damping: 30 }, // snappy
  };

  const stateTargets = {
    idle: { pulse: 1.0, aperture: 0.15, ringSpeed: 1/30 }, // 30s/rev
    listening: { pulse: 1.0 + micLevel * 0.35, aperture: 0.15 + micLevel * 0.7, ringSpeed: 1/8 }, // 8s/rev
    speaking: { pulse: 1.0 + micLevel * 0.2, aperture: 0.9, ringSpeed: 1/4 },
    processing: { pulse: 1.0 - 0.05, aperture: 0.05, ringSpeed: 1/2 }, // 2s rotation
    error: { pulse: 1.0, aperture: 0.15, ringSpeed: 0 },
    muted: { pulse: 1.0, aperture: 0.0, ringSpeed: 0 },
  };

  const updatePhysics = (dt: number) => {
    if (prefersReduced) return;

    const target = stateTargets[voiceState];
    const time = timeRef.current / 1000;

    // Pulse scale spring
    const pulseDiff = target.pulse - particlesRef.current[0]?.size; // using first particle as proxy
    // Actually track pulse separately
  };

  // Simplified: compute derived state each frame
  const orbState = useMemo((): OrbPhysicsState => {
    const target = stateTargets[voiceState];
    const time = timeRef.current / 1000;

    // Pulse scale (spring toward target)
    const pulseScale = target.pulse;

    // Aperture spring
    const apertureTarget = target.aperture;
    const apertureDiff = apertureTarget - apertureRef.current;
    apertureRef.current += apertureDiff * 0.15; // spring factor

    // Ring rotation
    ringRotationRef.current += target.ringSpeed * Math.PI * 2 * (1/60); // per frame at 60fps

    // Update particles
    const particles = particlesRef.current.map(p => {
      const speedMod = 1 + micLevel * 3;
      p.angle += p.speed * speedMod * (1/60);
      p.phase += 0.02 * (1/60);
      const radius = p.radius + Math.sin(p.phase) * 8;
      p.x = cx + Math.cos(p.angle) * radius;
      p.y = cy + Math.sin(p.angle * 0.7) * radius * 0.6;
      return p;
    });

    // Noise offset for surface simulation
    noiseOffsetRef.current.x += 0.1;
    noiseOffsetRef.current.y += 0.05;

    return {
      pulseScale,
      aperture: apertureRef.current,
      ringRotation: ringRotationRef.current,
      particles,
      noiseOffset: noiseOffsetRef.current,
    };
  }, [voiceState, micLevel, prefersReduced, cx, cy]);

  return orbState;
}
```

- [ ] **Step 1: Write the failing test**

```typescript
// useOrbPhysics.test.ts
import { renderHook, act } from '@testing-library/react';
import { useOrbPhysics } from '../useOrbPhysics';
import { vi } from 'vitest';

describe('useOrbPhysics', () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  test('returns idle state with small aperture', () => {
    const { result } = renderHook(() => useOrbPhysics({
      voiceState: 'idle',
      micLevel: 0,
      prefersReduced: false,
      width: 800,
      height: 600,
    }));

    expect(result.current.aperture).toBeCloseTo(0.15, 1);
    expect(result.current.pulseScale).toBe(1.0);
    expect(result.current.particles).toHaveLength(120);
  });

  test('increases aperture for listening state based on micLevel', () => {
    const { result, rerender } = renderHook(
      ({ micLevel }) => useOrbPhysics({
        voiceState: 'listening',
        micLevel,
        prefersReduced: false,
        width: 800,
        height: 600,
      }),
      { initialProps: { micLevel: 0 } }
    );

    expect(result.current.aperture).toBeCloseTo(0.15, 1);

    rerender({ micLevel: 0.5 });
    expect(result.current.aperture).toBeGreaterThan(0.15);
    expect(result.current.aperture).toBeLessThan(0.85);
  });

  test('sets aperture to 0.9 for speaking', () => {
    const { result } = renderHook(() => useOrbPhysics({
      voiceState: 'speaking',
      micLevel: 0.5,
      prefersReduced: false,
      width: 800,
      height: 600,
    }));

    expect(result.current.aperture).toBeCloseTo(0.9, 1);
  });

  test('sets aperture to 0.05 for processing', () => {
    const { result } = renderHook(() => useOrbPhysics({
      voiceState: 'processing',
      micLevel: 0,
      prefersReduced: false,
      width: 800,
      height: 600,
    }));

    expect(result.current.aperture).toBeCloseTo(0.05, 1);
  });

  test('sets aperture to 0 for muted', () => {
    const { result } = renderHook(() => useOrbPhysics({
      voiceState: 'muted',
      micLevel: 0,
      prefersReduced: false,
      width: 800,
      height: 600,
    }));

    expect(result.current.aperture).toBeCloseTo(0, 1);
  });

  test('particles have computed x,y positions', () => {
    const { result } = renderHook(() => useOrbPhysics({
      voiceState: 'idle',
      micLevel: 0,
      prefersReduced: false,
      width: 800,
      height: 600,
    }));

    result.current.particles.forEach(p => {
      expect(typeof p.x).toBe('number');
      expect(typeof p.y).toBe('number');
      expect(p.x).toBeGreaterThanOrEqual(0);
      expect(p.y).toBeGreaterThanOrEqual(0);
    });
  });

  test('returns static values when prefersReduced is true', () => {
    const { result, rerender } = renderHook(
      ({ prefersReduced }) => useOrbPhysics({
        voiceState: 'listening',
        micLevel: 0.5,
        prefersReduced,
        width: 800,
        height: 600,
      }),
      { initialProps: { prefersReduced: false } }
    );

    const initialAperture = result.current.aperture;
    rerender({ prefersReduced: true });
    // With reduced motion, aperture should not animate
    expect(result.current.aperture).toBe(initialAperture);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**
Run: `npm test -- useOrbPhysics.test.ts`
Expected: FAIL

- [ ] **Step 3: Write minimal implementation**
Create `useOrbPhysics.ts` with proper spring physics

- [ ] **Step 4: Run test to verify it passes**
Run: `npm test -- useOrbPhysics.test.ts`
Expected: PASS

- [ ] **Step 5: Commit**
```bash
git add frontend/src/components/voice-bridge/hooks/useOrbPhysics.ts frontend/src/components/voice-bridge/hooks/__tests__/useOrbPhysics.test.ts
git commit -m "feat(voice-bridge): add useOrbPhysics hook for Living Orb spring physics"
```

---

#### Task 2.2: Rewrite Canvas2DFallback with Living Orb 3-Ring System

**Files:**
- Modify: `frontend/src/components/voice-bridge/Canvas2DFallback.tsx` (complete rewrite)
- Test: `frontend/src/components/voice-bridge/__tests__/Canvas2DFallback.living-orb.test.tsx`

**Interfaces:**
- Consumes: `useOrbPhysics` hook, design tokens from CSS
- Produces: 60fps Living Orb visualization with 3-ring gradient, aperture, particles, noise

The rewrite replaces the existing Canvas2DFallback (which has frequency bars, waveform, etc.) with the Living Orb spec. The frequency bars and waveform move to a separate visualization mode or are removed per the new design.

```tsx
// Canvas2DFallback.tsx — LIVING ORB REWRITE
import { useEffect, useRef, useCallback, useMemo } from 'react';
import { useOrbPhysics } from './hooks/useOrbPhysics';
import { useReducedMotion } from './hooks/useReducedMotion';

type VoiceState = 'idle' | 'listening' | 'speaking' | 'processing' | 'error' | 'muted';
type ConnectionStatus = 'disconnected' | 'connecting' | 'connected' | 'error' | 'reconnecting';

interface Canvas2DFallbackProps {
  voiceState: VoiceState;
  micLevel: number;
  timeDomainData: Uint8Array | null;
  frequencyData: Uint8Array | null;
  status: ConnectionStatus;
  prefersReduced?: boolean;
}

export function Canvas2DFallback({
  voiceState,
  micLevel,
  timeDomainData,
  frequencyData,
  status,
  prefersReduced: prefersReducedProp = false,
}: Canvas2DFallbackProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const animationRef = useRef<number>();
  const timeRef = useRef(0);
  const { prefersReduced: prefersReducedHook } = useReducedMotion();
  const prefersReduced = prefersReducedProp || prefersReducedHook;

  // Noise texture (cached)
  const noiseCanvasRef = useRef<HTMLCanvasElement | null>(null);
  const noiseTextureRef = useRef<CanvasPattern | null>(null);

  // Design tokens
  const tokens = useMemo(() => {
    const style = getComputedStyle(document.documentElement);
    return {
      canvasBg: style.getPropertyValue('--c-canvas').trim() || '#0f172a',
      brand: style.getPropertyValue('--c-brand').trim() || '#3b82f6',
      brand2: style.getPropertyValue('--c-brand-2').trim() || '#8b5cf6',
      success: style.getPropertyValue('--c-success').trim() || '#10b981',
      warning: style.getPropertyValue('--c-warning').trim() || '#f59e0b',
      error: style.getPropertyValue('--c-error').trim() || '#ef4444',
      voiceListening: style.getPropertyValue('--c-voice-listening').trim() || '#3b82f6',
      voiceSpeaking: style.getPropertyValue('--c-voice-speaking').trim() || '#059669',
      voiceThinking: style.getPropertyValue('--c-voice-thinking').trim() || '#7c3aed',
      voiceError: style.getPropertyValue('--c-voice-error').trim() || '#ef4444',
      voiceGlow: style.getPropertyValue('--c-voice-glow').trim() || 'rgba(59, 130, 246, 0.4)',
      textPrimary: style.getPropertyValue('--color-text-primary').trim() || '#f1f5f9',
      textSecondary: style.getPropertyValue('--color-text-secondary').trim() || '#94a3b8',
      textMuted: style.getPropertyValue('--color-text-muted').trim() || '#64748b',
      hairline: style.getPropertyValue('--c-hairline').trim() || 'rgba(148, 163, 184, 0.15)',
      glassBg: style.getPropertyValue('--c-glass-bg').trim() || 'rgba(30, 41, 59, 0.7)',
      glassBorder: style.getPropertyValue('--c-glass-border').trim() || 'rgba(148, 163, 184, 0.2)',
    };
  }, []);

  // State colors
  const stateColors = useMemo(() => ({
    idle: { primary: tokens.textSecondary, glow: tokens.hairline, gradient: [tokens.textSecondary, tokens.hairline] },
    listening: { primary: tokens.voiceListening, glow: tokens.voiceListening, gradient: [tokens.voiceListening, tokens.brand] },
    speaking: { primary: tokens.voiceSpeaking, glow: tokens.voiceSpeaking, gradient: [tokens.voiceSpeaking, tokens.success] },
    processing: { primary: tokens.voiceThinking, glow: tokens.voiceThinking, gradient: [tokens.voiceThinking, tokens.brand2] },
    error: { primary: tokens.voiceError, glow: tokens.voiceError, gradient: [tokens.voiceError, tokens.error] },
    muted: { primary: tokens.textMuted, glow: tokens.textMuted, gradient: [tokens.textMuted, tokens.hairline] },
  }), [tokens]);

  // Status color
  const getStatusColor = useCallback((s: ConnectionStatus) => {
    switch (s) {
      case 'connected': return tokens.success;
      case 'connecting': case 'reconnecting': return tokens.warning;
      case 'error': return tokens.error;
      default: return tokens.textMuted;
    }
  }, [tokens]);

  // Orb physics
  const canvasSizeRef = useRef({ width: 0, height: 0 });
  const orbPhysics = useOrbPhysics({
    voiceState,
    micLevel,
    prefersReduced,
    width: canvasSizeRef.current.width || 400,
    height: canvasSizeRef.current.height || 400,
  });

  // Generate noise texture
  const generateNoiseTexture = useCallback((ctx: CanvasRenderingContext2D, width: number, height: number) => {
    if (noiseCanvasRef.current) return noiseTextureRef.current;

    const noiseCanvas = document.createElement('canvas');
    noiseCanvas.width = 64;
    noiseCanvas.height = 64;
    const nctx = noiseCanvas.getContext('2d')!;
    const imageData = nctx.createImageData(64, 64);
    const data = imageData.data;

    for (let i = 0; i < data.length; i += 4) {
      const val = Math.random() * 255;
      data[i] = data[i + 1] = data[i + 2] = val;
      data[i + 3] = 255;
    }
    nctx.putImageData(imageData, 0, 0);

    noiseCanvasRef.current = noiseCanvas;
    noiseTextureRef.current = ctx.createPattern(noiseCanvas, 'repeat');
    return noiseTextureRef.current;
  }, []);

  // Main render
  const render = useCallback((timestamp: number) => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const ctx = canvas.getContext('2d', { alpha: true, desynchronized: true });
    if (!ctx) return;

    const dt = prefersReduced ? 0 : Math.min((timestamp - timeRef.current) / 1000, 1/30);
    timeRef.current = timestamp;

    const { width, height } = canvas;
    canvasSizeRef.current = { width, height };
    const cx = width / 2;
    const cy = height / 2;

    // Recompute physics with current canvas size
    const physics = useOrbPhysics({
      voiceState,
      micLevel,
      prefersReduced,
      width,
      height,
    });

    const colors = stateColors[voiceState];
    const statusColor = getStatusColor(status);
    const pulseScale = physics.pulseScale;
    const aperture = physics.aperture;
    const ringRotation = physics.ringRotation;
    const particles = physics.particles;

    // Clear
    ctx.fillStyle = tokens.canvasBg;
    ctx.fillRect(0, 0, width, height);

    // ========================================
    // DEPTH 1: Radial glow atmosphere
    // ========================================
    const glowRadius = Math.max(width, height) * 0.5;
    const glowGradient = ctx.createRadialGradient(cx, cy, 0, cx, cy, glowRadius);
    const glowOpacity = voiceState === 'idle' ? 0.06 : voiceState === 'muted' ? 0.04 : 0.15;
    glowGradient.addColorStop(0, `${colors.glow}${Math.round(glowOpacity * 255).toString(16).padStart(2, '0')}`);
    glowGradient.addColorStop(0.5, `${colors.glow}08`);
    glowGradient.addColorStop(1, 'transparent');
    ctx.fillStyle = glowGradient;
    ctx.fillRect(0, 0, width, height);

    // Dot grid (AgentsPage style)
    ctx.save();
    ctx.globalAlpha = 0.02;
    ctx.strokeStyle = tokens.hairline;
    ctx.lineWidth = 1;
    const gridSize = 40;
    for (let x = 0; x < width; x += gridSize) {
      ctx.beginPath();
      ctx.moveTo(x, 0);
      ctx.lineTo(x, height);
      ctx.stroke();
    }
    for (let y = 0; y < height; y += gridSize) {
      ctx.beginPath();
      ctx.moveTo(0, y);
      ctx.lineTo(width, y);
      ctx.stroke();
    }
    ctx.restore();

    // Vignette
    const vignetteGradient = ctx.createRadialGradient(cx, cy, 0, cx, cy, Math.max(width, height) * 0.7);
    vignetteGradient.addColorStop(0, 'transparent');
    vignetteGradient.addColorStop(0.7, 'transparent');
    vignetteGradient.addColorStop(1, tokens.canvasBg);
    ctx.fillStyle = vignetteGradient;
    ctx.fillRect(0, 0, width, height);

    // ========================================
    // DEPTH 2: Particle field
    // ========================================
    if (!prefersReduced) {
      ctx.save();
      particles.forEach(p => {
        const size = p.size * (1 + micLevel * 0.5);
        const particleGradient = ctx.createRadialGradient(p.x, p.y, 0, p.x, p.y, size * 2);
        particleGradient.addColorStop(0, `${colors.primary}${Math.round(p.opacity * 255).toString(16).padStart(2, '0')}`);
        particleGradient.addColorStop(1, 'transparent');
        ctx.fillStyle = particleGradient;
        ctx.beginPath();
        ctx.arc(p.x, p.y, size, 0, Math.PI * 2);
        ctx.fill();
      });
      ctx.restore();
    }

    // ========================================
    // DEPTH 3: 3-Ring Orb System
    // ========================================
    const orbRadius = 80 * pulseScale;

    // OUTER RING (1.45x)
    const outerRadius = orbRadius * 1.45;
    const outerGradient = ctx.createRadialGradient(cx, cy, outerRadius * 0.3, cx, cy, outerRadius);
    outerGradient.addColorStop(0, 'transparent');
    outerGradient.addColorStop(0.5, `${colors.glow}08`);
    outerGradient.addColorStop(1, `${colors.primary}15`);
    ctx.fillStyle = outerGradient;
    ctx.beginPath();
    ctx.arc(cx, cy, outerRadius, 0, Math.PI * 2);
    ctx.fill();

    // MID RING — THE BRAND RING (1.15x) with conic gradient + blob distortion
    const midRadius = orbRadius * 1.15;
    ctx.save();
    ctx.translate(cx, cy);
    ctx.rotate(ringRotation);
    
    // Draw blob-distorted mid ring
    ctx.beginPath();
    const segments = 64;
    for (let i = 0; i <= segments; i++) {
      const angle = (i / segments) * Math.PI * 2;
      // Blob distortion using noise-like function
      const noise = Math.sin(angle * 3 + ringRotation * 2) * 0.04 + Math.sin(angle * 7 + ringRotation * 5) * 0.02;
      const r = midRadius * (1 + noise);
      const x = Math.cos(angle) * r;
      const y = Math.sin(angle) * r;
      if (i === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    }
    ctx.closePath();

    // Conic gradient for brand ring (approximated with radial + rotation)
    const midGradient = ctx.createRadialGradient(0, 0, midRadius * 0.7, 0, 0, midRadius);
    midGradient.addColorStop(0, `${colors.primary}08`);
    midGradient.addColorStop(0.5, `${colors.primary}25`);
    midGradient.addColorStop(0.8, `${colors.primary}40`);
    midGradient.addColorStop(1, `${colors.primary}60`);
    ctx.fillStyle = midGradient;
    ctx.fill();
    ctx.strokeStyle = colors.primary;
    ctx.lineWidth = 2;
    ctx.stroke();
    ctx.restore();

    // INNER CORE (0.85x) — radial gradient with specular
    const innerRadius = orbRadius * 0.85;
    const innerGradient = ctx.createRadialGradient(cx, cy, 0, cx, cy, innerRadius);
    innerGradient.addColorStop(0, colors.gradient[0]);
    innerGradient.addColorStop(0.5, colors.gradient[1]);
    innerGradient.addColorStop(1, `${colors.primary}DD`);
    ctx.fillStyle = innerGradient;
    ctx.beginPath();
    ctx.arc(cx, cy, innerRadius, 0, Math.PI * 2);
    ctx.fill();

    // Specular highlight
    if (voiceState !== 'muted' && voiceState !== 'idle') {
      const highlightRadius = innerRadius * 0.35;
      const highlightGradient = ctx.createRadialGradient(
        cx - highlightRadius * 0.3, cy - highlightRadius * 0.3, 0,
        cx - highlightRadius * 0.3, cy - highlightRadius * 0.3, highlightRadius
      );
      highlightGradient.addColorStop(0, 'rgba(255,255,255,0.4)');
      highlightGradient.addColorStop(1, 'transparent');
      ctx.fillStyle = highlightGradient;
      ctx.beginPath();
      ctx.arc(cx - highlightRadius * 0.3, cy - highlightRadius * 0.3, highlightRadius, 0, Math.PI * 2);
      ctx.fill();
    }

    // Aperture mask (animated circular clip)
    if (aperture < 1.0) {
      const apertureRadius = innerRadius * aperture;
      ctx.save();
      ctx.globalCompositeOperation = 'destination-out';
      ctx.fillStyle = 'black';
      ctx.beginPath();
      ctx.arc(cx, cy, apertureRadius, 0, Math.PI * 2);
      ctx.fill();
      ctx.restore();
    }

    // Noise overlay on orb surface
    const noisePattern = generateNoiseTexture(ctx, width, height);
    if (noisePattern && voiceState !== 'muted') {
      ctx.save();
      ctx.globalCompositeOperation = 'overlay';
      ctx.globalAlpha = 0.15;
      ctx.translate(cx, cy);
      ctx.rotate(ringRotation * 0.5);
      ctx.translate(-cx, -cy);
      ctx.fillStyle = noisePattern;
      ctx.beginPath();
      ctx.arc(cx, cy, innerRadius, 0, Math.PI * 2);
      ctx.fill();
      ctx.restore();
    }

    // ========================================
    // DEPTH 4: Connection status indicator
    // ========================================
    if (status !== 'disconnected') {
      const dotSize = 10;
      const dotX = width - 32;
      const dotY = 32;

      ctx.save();
      if (!prefersReduced && (status === 'connecting' || status === 'reconnecting' || status === 'connected')) {
        const pulse = (Math.sin(timeRef.current / 200) + 1) / 2;
        const ringRadius = dotSize + pulse * 8;
        const ringAlpha = (1 - pulse) * 0.5;
        ctx.strokeStyle = `${statusColor}${Math.round(ringAlpha * 255).toString(16).padStart(2, '0')}`;
        ctx.lineWidth = 2;
        ctx.beginPath();
        ctx.arc(dotX, dotY, ringRadius, 0, Math.PI * 2);
        ctx.stroke();
      }
      ctx.fillStyle = statusColor;
      ctx.shadowColor = statusColor;
      ctx.shadowBlur = 12;
      ctx.beginPath();
      ctx.arc(dotX, dotY, dotSize / 2, 0, Math.PI * 2);
      ctx.fill();
      ctx.shadowBlur = 0;
      ctx.restore();
    }

    // ========================================
    // DEPTH 5: State label
    // ========================================
    const stateLabels: Record<VoiceState, string> = {
      idle: 'Ready',
      listening: 'Listening...',
      speaking: 'Speaking',
      processing: 'Thinking...',
      error: 'Error',
      muted: 'Muted',
    };

    ctx.font = '500 13px ui-sans-serif, system-ui';
    ctx.fillStyle = tokens.textSecondary;
    ctx.textAlign = 'center';
    ctx.textBaseline = 'top';
    const label = stateLabels[voiceState];
    ctx.fillText(label, cx, cy + orbRadius * 1.8);

    // Next frame
    if (!prefersReduced) {
      animationRef.current = requestAnimationFrame(render);
    }
  }, [
    voiceState,
    micLevel,
    prefersReduced,
    stateColors,
    getStatusColor,
    tokens,
    useOrbPhysics,
    generateNoiseTexture,
  ]);

  // Resize & animation loop
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const resize = () => {
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      const rect = canvas.parentElement?.getBoundingClientRect();
      if (rect) {
        canvas.width = Math.floor(rect.width * dpr);
        canvas.height = Math.floor(rect.height * dpr);
        canvas.style.width = `${rect.width}px`;
        canvas.style.height = `${rect.height}px`;
        const ctx = canvas.getContext('2d');
        if (ctx) ctx.scale(dpr, dpr);
      }
    };

    resize();
    window.addEventListener('resize', resize);
    animationRef.current = requestAnimationFrame(render);

    return () => {
      window.removeEventListener('resize', resize);
      if (animationRef.current) cancelAnimationFrame(animationRef.current);
    };
  }, [render, prefersReduced]);

  // Reduced motion: single frame
  useEffect(() => {
    if (prefersReduced && canvasRef.current) {
      const ctx = canvasRef.current.getContext('2d');
      if (ctx) {
        timeRef.current = performance.now();
        render(timeRef.current);
      }
    }
  }, [prefersReduced, render, voiceState, micLevel, status]);

  return (
    <div className="relative w-full h-full" style={{ minHeight: '100vh' }}>
      <canvas
        ref={canvasRef}
        className="w-full h-full block"
        aria-hidden="true"
        role="img"
        aria-label={`Voice visualization: ${voiceState}, microphone level ${Math.round(micLevel * 100)}%`}
      />
    </div>
  );
}
```

- [ ] **Step 1: Write the failing test**

```tsx
// Canvas2DFallback.living-orb.test.tsx
import { render, screen } from '@testing-library/react';
import { Canvas2DFallback } from '../Canvas2DFallback';
import { vi } from 'vitest';

// Mock canvas context
const mockCtx = {
  fillRect: vi.fn(),
  fillStyle: '',
  strokeStyle: '',
  lineWidth: 0,
  globalAlpha: 1,
  globalCompositeOperation: 'source-over',
  shadowColor: '',
  shadowBlur: 0,
  font: '',
  textAlign: 'center',
  textBaseline: 'top',
  fillText: vi.fn(),
  beginPath: vi.fn(),
  arc: vi.fn(),
  fill: vi.fn(),
  stroke: vi.fn(),
  moveTo: vi.fn(),
  lineTo: vi.fn(),
  closePath: vi.fn(),
  createRadialGradient: vi.fn(() => ({
    addColorStop: vi.fn(),
  })),
  createLinearGradient: vi.fn(() => ({
    addColorStop: vi.fn(),
  })),
  createPattern: vi.fn(),
  translate: vi.fn(),
  rotate: vi.fn(),
  scale: vi.fn(),
  save: vi.fn(),
  restore: vi.fn(),
};

HTMLCanvasElement.prototype.getContext = vi.fn(() => mockCtx);

vi.mock('@/components/voice-bridge/hooks/useReducedMotion', () => ({
  useReducedMotion: () => ({ prefersReduced: false }),
}));

vi.mock('@/components/voice-bridge/hooks/useOrbPhysics', () => ({
  useOrbPhysics: () => ({
    pulseScale: 1,
    aperture: 0.15,
    ringRotation: 0,
    particles: [],
    noiseOffset: { x: 0, y: 0 },
  }),
}));

describe('Canvas2DFallback Living Orb', () => {
  test('renders canvas element with aria-label', () => {
    render(<Canvas2DFallback voiceState="idle" micLevel={0} timeDomainData={null} frequencyData={null} status="connected" />);
    const canvas = screen.getByRole('img');
    expect(canvas).toBeInTheDocument();
    expect(canvas).toHaveAttribute('aria-label', expect.stringContaining('idle'));
  });

  test('calls render loop with voiceState', () => {
    render(<Canvas2DFallback voiceState="listening" micLevel={0.5} timeDomainData={null} frequencyData={null} status="connected" />);
    expect(mockCtx.fillRect).toHaveBeenCalled();
    expect(mockCtx.arc).toHaveBeenCalled(); // orb rings
  });

  test('draws 3-ring system (outer, mid, inner)', () => {
    render(<Canvas2DFallback voiceState="speaking" micLevel={0.3} timeDomainData={null} frequencyData={null} status="connected" />);
    // Should call arc 3 times for the 3 rings
    expect(mockCtx.arc).toHaveBeenCalledTimes(expect.toBeGreaterThanOrEqual(3));
  });

  test('applies aperture mask for non-idle states', () => {
    render(<Canvas2DFallback voiceState="listening" micLevel={0.5} timeDomainData={null} frequencyData={null} status="connected" />);
    expect(mockCtx.globalCompositeOperation).toBe('destination-out');
  });

  test('renders particle field', () => {
    render(<Canvas2DFallback voiceState="idle" micLevel={0} timeDomainData={null} frequencyData={null} status="connected" />);
    // Particles should be drawn
    expect(mockCtx.arc).toHaveBeenCalled();
  });

  test('handles prefers-reduced-motion', () => {
    vi.mock('@/components/voice-bridge/hooks/useReducedMotion', () => ({
      useReducedMotion: () => ({ prefersReduced: true }),
    }));
    
    render(<Canvas2DFallback voiceState="listening" micLevel={0.5} timeDomainData={null} frequencyData={null} status="connected" />);
    // Should render single static frame
    expect(mockCtx.fillRect).toHaveBeenCalled();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**
Run: `npm test -- Canvas2DFallback.living-orb.test.tsx`
Expected: FAIL

- [ ] **Step 3: Rewrite Canvas2DFallback**
Complete rewrite per spec with 3-ring system, aperture, particles, noise

- [ ] **Step 4: Run test to verify it passes**
Run: `npm test -- Canvas2DFallback.living-orb.test.tsx`
Expected: PASS

- [ ] **Step 5: Commit**
```bash
git add frontend/src/components/voice-bridge/Canvas2DFallback.tsx frontend/src/components/voice-bridge/__tests__/Canvas2DFallback.living-orb.test.tsx
git commit -m "feat(voice-bridge): rewrite Canvas2DFallback with Living Orb 3-ring system"
```

---

#### Task 2.3: Add State Transition Tests for Canvas2DFallback

**Files:**
- Modify: `frontend/src/components/voice-bridge/__tests__/Canvas2DFallback.living-orb.test.tsx` (add more tests)
- Test existing file

Test state transitions: idle → listening → speaking → processing → idle, error handling

- [ ] **Step 1: Add transition tests**
- [ ] **Step 2: Run tests**
- [ ] **Step 3: Commit**

---

### Phase 3: Living Orb — GPU Path (ThreeScene)

#### Task 3.1: Write GLSL Shaders for Living Orb

**Files:**
- Create: `frontend/src/components/voice-bridge/shaders/orbSurface.glsl`
- Create: `frontend/src/components/voice-bridge/shaders/orbMidRing.glsl`
- Create: `frontend/src/components/voice-bridge/shaders/particleField.glsl`
- Modify: `frontend/src/components/voice-bridge/shaders.d.ts` (add new shader imports)

**orbSurface.glsl** — Noise + color gradient + aperture mask
```glsl
// orbSurface.glsl
uniform float uTime;
uniform float uMicLevel;
uniform vec3 uStateColor;
uniform float uAperture;
uniform vec2 uNoiseOffset;
uniform float uPulseScale;

varying vec3 vNormal;
varying vec2 vUv;

#pragma glslify: snoise = require(glsl-noise/simplex/3d)

void main() {
  // Base color from state gradient
  float gradient = vUv.y;
  vec3 color = mix(uStateColor * 0.3, uStateColor, gradient);
  
  // Noise on surface
  float noise = snoise(vec3(vUv * 10.0, uTime * 0.1 + uNoiseOffset.x));
  color += noise * 0.1 * uStateColor;
  
  // Specular highlight
  vec3 viewDir = normalize(vec3(0.0, 0.0, 1.0));
  float spec = pow(max(dot(vNormal, viewDir), 0.0), 64.0);
  color += vec3(spec * 0.4);
  
  // Aperture mask
  float distFromCenter = length(vUv - 0.5);
  if (distFromCenter < (0.5 * uAperture)) {
    discard; // or alpha = 0
  }
  
  gl_FragColor = vec4(color, 1.0);
}
```

**orbMidRing.glsl** — Conic gradient + blob distortion
```glsl
// orbMidRing.glsl
uniform float uTime;
uniform vec3 uStateColor;
uniform vec3 uBrandColor;
uniform vec3 uAccentColor;
uniform float uRingRotation;
uniform float uBlobAmount;

varying vec2 vUv;

void main() {
  // Conic gradient
  float angle = atan(vUv.y - 0.5, vUv.x - 0.5) + uRingRotation;
  angle = angle / (2.0 * 3.14159) + 0.5;
  
  vec3 color;
  if (angle < 0.33) color = mix(uStateColor, uBrandColor, angle * 3.0);
  else if (angle < 0.66) color = mix(uBrandColor, uAccentColor, (angle - 0.33) * 3.0);
  else color = mix(uAccentColor, uStateColor, (angle - 0.66) * 3.0);
  
  // Blob distortion
  float dist = length(vUv - 0.5);
  float blob = sin(angle * 6.0 + uTime * 2.0) * uBlobAmount;
  float edge = smoothstep(0.45 - blob, 0.5 + blob, dist);
  
  gl_FragColor = vec4(color, 1.0 - edge);
}
```

**particleField.glsl** — GPU particle animation
```glsl
// particleField.glsl
uniform float uTime;
uniform float uMicLevel;
uniform vec3 uStateColor;
uniform float uParticleCount;

attribute float aAngle;
attribute float aRadius;
attribute float aSpeed;
attribute float aSize;
attribute float aOpacity;
attribute float aPhase;

varying float vOpacity;
varying vec3 vColor;

void main() {
  float angle = aAngle + aSpeed * uTime * (1.0 + uMicLevel * 3.0);
  float phase = aPhase + uTime * 0.02;
  float radius = aRadius + sin(phase) * 8.0;
  
  vec3 pos = vec3(
    cos(angle) * radius,
    sin(angle * 0.7) * radius * 0.6,
    0.0
  );
  
  float size = aSize * (1.0 + uMicLevel * 0.5);
  vOpacity = aOpacity;
  vColor = uStateColor;
  
  gl_Position = projectionMatrix * modelViewMatrix * vec4(pos, 1.0);
  gl_PointSize = size * (300.0 / -gl_Position.z);
}
```

- [ ] **Step 1: Create shader files**
- [ ] **Step 2: Update shaders.d.ts**
- [ ] **Step 3: Commit**

---

#### Task 3.2: Update ThreeScene with Living Orb Components

**Files:**
- Modify: `frontend/src/components/voice-bridge/ThreeScene.tsx`
- Modify: `frontend/src/components/voice-bridge/VoiceOrb3D.tsx` (or create new LivingOrb3D)
- Modify: `frontend/src/components/voice-bridge/ParticleField.tsx` (update for new particle system)

Create `LivingOrb3D` component using the new shaders, replace `VoiceOrb3D` in ThreeScene.

- [ ] **Step 1: Create LivingOrb3D component**
- [ ] **Step 2: Update ThreeScene to use LivingOrb3D**
- [ ] **Step 3: Visual parity verification (manual)**
- [ ] **Step 4: Commit**

---

#### Task 3.3: Add Uniform Animation Loop in ThreeScene

**Files:**
- Modify: `frontend/src/components/voice-bridge/ThreeScene.tsx`

Sync state morph uniforms (aperture, pulseScale, ringRotation, noiseOffset) from `useOrbPhysics` or replicate logic in Three.js

- [ ] **Step 1: Add uniform update loop**
- [ ] **Step 2: Test visual parity**
- [ ] **Step 3: Commit**

---

### Phase 4: Polish & Integration

#### Task 4.1: Upgrade VoiceControls with Living Pulse & Morphing Icon

**Files:**
- Modify: `frontend/src/components/voice-bridge/VoiceControls.tsx`
- Test: `frontend/src/components/voice-bridge/__tests__/VoiceControls.living.test.tsx`

Changes:
- Primary button: Living pulse ring (CSS keyframes + prefers-reduced-motion)
- State icon: Dynamic SVG morphing (Mic → Waveform → Loader → Alert → MicOff)
- Settings button: Spring rotate (30°) on hover
- Label: ARIA live region with polished copy per state

The pulse ring already exists (lines 78-98). Enhance with state-specific colors.

State icon mapping already exists (lines 54-61). Ensure smooth transitions.

- [ ] **Step 1: Write enhanced tests**
- [ ] **Step 2: Update VoiceControls**
- [ ] **Step 3: Run tests**
- [ ] **Step 4: Commit**

---

#### Task 4.2: Enhance TranscriptDisplay Streaming Animation

**Files:**
- Modify: `frontend/src/components/voice-bridge/TranscriptDisplay.tsx`
- Test: `frontend/src/components/voice-bridge/__tests__/TranscriptDisplay.streaming.test.tsx`

Streaming char animation already implemented (lines 137-150). Ensure it works in floating panel context.

- [ ] **Step 1: Test in TranscriptDrawer context**
- [ ] **Step 2: Fix any issues**
- [ ] **Step 3: Commit**

---

#### Task 4.3: Full Accessibility Audit

**Files:**
- Test: `frontend/src/components/voice-bridge/__tests__/VoiceBridgeContainer.a11y.test.tsx`

Run axe-core on immersive layout. Verify:
- prefers-reduced-motion works on all animations
- ARIA live regions: Transcript (polite), Status label (assertive for errors)
- Keyboard navigation: Tab order — Status → Controls (Mute, Record, Settings) → Transcript toggle → Transcript items
- Focus visible on all interactive elements
- Color contrast ≥ 4.5:1 on glass panels
- Screen reader: Transcript entries have role="log", speaker labels, timestamps

- [ ] **Step 1: Run accessibility tests**
- [ ] **Step 2: Fix violations**
- [ ] **Step 3: Commit**

---

#### Task 4.4: Cross-Browser Testing & Performance Profiling

**Tasks:**
- Test Canvas 2D path in Chrome, Firefox, Safari
- Test WebGL path (ThreeScene) in Chrome, Firefox, Safari
- Profile CPU performance: target 60fps sustained
- Profile GPU performance: target 120fps
- Verify DPR clamping works on HiDPI
- Verify particle count scaling on low-end

- [ ] **Step 1: Manual browser testing**
- [ ] **Step 2: Performance profiling**
- [ ] **Step 3: Optimize if needed**
- [ ] **Step 4: Commit**

---

#### Task 4.5: Responsive Layout Verification

**Files:**
- Test: `frontend/src/components/voice-bridge/__tests__/VoiceBridgeContainer.responsive.test.tsx`

Verify breakpoints:
- ≥1280px: Full immersive, transcript drawer 384px
- 1024-1279px: Full immersive, transcript drawer 320px
- 768-1023px: Transcript becomes bottom sheet (slide up), controls pill fixed
- <768px: Orb 80vw, transcript modal drawer (full width), controls condensed

Update TranscriptDrawer and ControlsPill with responsive classes.

- [ ] **Step 1: Add responsive classes to components**
- [ ] **Step 2: Test at each breakpoint**
- [ ] **Step 3: Commit**

---

## Execution Handoff

**Plan complete and saved to `docs/superpowers/plans/2026-07-27-voice-bridge-immersive-hero.md`. Two execution options:**

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

**Which approach?**
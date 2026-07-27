# VoiceBridge Page Layout Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Elevate the VoiceBridge page to "extraordinary" professional SaaS quality while preserving the exact current layout structure, with dual-path parity for CPU (Canvas2DFallback) and GPU (ThreeScene) visualizations.

**Architecture:** Incremental enhancement of existing VoiceBridgeContainer.tsx and its child components. Each section (Header, Visualization, Transcript, Controls) is upgraded independently using the existing design system (CSS variables from index.css), Framer Motion for orchestrated spring animations, and Canvas 2D / Three.js for visualization. No layout restructuring.

**Tech Stack:** React 18, TypeScript, Vite, Framer Motion, Three.js r182, Canvas 2D API, Tailwind CSS (via CSS variables), shadcn/ui components (WidgetCard, StatCard, EmptyState)

---

## Global Constraints

- **CSS Variables:** All colors, spacing, borders MUST use exact variables from `frontend/src/index.css` — zero deviations
- **Design System:** Match Dashboard.tsx and AgentsPage.tsx visual quality exactly
- **Dual-Path Parity:** CPU (Canvas2DFallback) and GPU (ThreeScene) must have equivalent visual quality
- **Accessibility:** WCAG AA contrast, ARIA live regions, keyboard navigation, prefers-reduced-motion
- **Theme Transition:** All themed properties animate 220ms ease via `html.theme-transition`
- **Bundle Size:** Three.js chunk < 150KB gzipped (dynamic import via React.lazy)
- **Performance:** 60fps desktop, 30fps mobile; transform/opacity only for animations
- **Testing:** Each task ends with independently testable deliverable; manual verification checklist per section

---

## File Structure Map

| File | Responsibility |
|------|----------------|
| `frontend/src/components/voice-bridge/VoiceBridgeContainer.tsx` | Main container — motion orchestration, glassmorphism wrappers, section composition |
| `frontend/src/components/voice-bridge/Canvas2DFallback.tsx` | **Complete visual overhaul** — premium 2D canvas visualization (orb, waveform, bars, particles) |
| `frontend/src/components/voice-bridge/TranscriptDisplay.tsx` | WidgetCard wrapper, EmptyState, scroll shadows, copy tooltip |
| `frontend/src/components/voice-bridge/VoiceControls.tsx` | Expanding pulse ring, haptic press, settings rotate spring, richer status text |
| `frontend/src/components/voice-bridge/ThreeScene.tsx` | Color sync verification, subtle parallax (reduced-motion aware) |
| `frontend/src/components/voice-bridge/VoiceOrb3D.tsx` | Ensure CSS variable color sync via useThreeColors |
| `frontend/src/components/voice-bridge/index.ts` | Export any new sub-components |
| `frontend/src/components/dashboard/WidgetCard.tsx` | Reused for transcript panel wrapper |
| `frontend/src/components/ui/EmptyState.tsx` | Reused for transcript empty state |

---

## Task Decomposition

### Task 1: Header — Premium Brand & Connection Status

**Files:**
- Modify: `frontend/src/components/voice-bridge/VoiceBridgeContainer.tsx:114-149` (header section)

**Interfaces:**
- Consumes: `status`, `isBusy`, `handleConnect` from useVoiceBridge hook
- Produces: Elevated header with motion variants

- [ ] **Step 1: Write failing test for header motion variants**

```tsx
// frontend/src/components/voice-bridge/__tests__/VoiceBridgeContainer.header.test.tsx
import { render, screen } from '@testing-library/react';
import { VoiceBridgeContainer } from '../VoiceBridgeContainer';
import { motion } from 'framer-motion';

describe('VoiceBridgeContainer Header', () => {
  it('renders brand with gradient orb icon', () => {
    render(<VoiceBridgeContainer />);
    const orb = screen.getByTestId('voice-bridge-brand-orb');
    expect(orb).toHaveStyle({
      background: expect.stringMatching(/linear-gradient/),
      boxShadow: expect.stringMatching(/var\(--c-voice-glow\)/),
    });
  });

  it('renders connection status dot with correct color for connected state', () => {
    render(<VoiceBridgeContainer />);
    const dot = screen.getByTestId('connection-status-dot');
    expect(dot).toHaveStyle({
      backgroundColor: 'rgb(16, 185, 129)', // --c-success light
    });
  });

  it('applies motion initial/animate variants to header elements', () => {
    render(<VoiceBridgeContainer />);
    const header = screen.getByTestId('voice-bridge-header');
    expect(header).toHaveAttribute('data-framer-motion-initial', '{"opacity":0,"x":20}');
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm test -- --testPathPattern="VoiceBridgeContainer.header" --run`
Expected: FAIL — elements don't exist yet

- [ ] **Step 3: Implement premium header**

```tsx
// In VoiceBridgeContainer.tsx, replace header section (lines 114-149):

{/* ── Header ── */}
<motion.header
  data-testid="voice-bridge-header"
  initial={{ opacity: 0, y: -20 }}
  animate={{ opacity: 1, y: 0 }}
  transition={{ type: 'spring', stiffness: 300, damping: 30 }}
  className="flex-shrink-0 bg-[var(--c-glass-bg)] border-b border-[var(--c-glass-border)] backdrop-blur-xl sticky top-0 z-10"
>
  <div className="max-w-2xl mx-auto px-6 py-4 flex items-center justify-between gap-4">
    {/* Brand with gradient orb */}
    <motion.div
      data-testid="voice-bridge-brand-orb"
      initial={{ opacity: 0, scale: 0.8, rotate: -15 }}
      animate={{ opacity: 1, scale: 1, rotate: 0 }}
      transition={{ type: 'spring', stiffness: 300, damping: 30 }}
      className="w-10 h-10 rounded-xl flex items-center justify-center flex-shrink-0"
      style={{
        background: 'linear-gradient(135deg, var(--c-voice-listening), var(--c-voice-speaking))',
        boxShadow: '0 4px 20px var(--c-voice-glow)',
      }}
    >
      <Mic className="w-5 h-5 text-white" aria-hidden="true" />
    </motion.div>
    <motion.div
      initial={{ opacity: 0, x: -20 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ type: 'spring', stiffness: 300, damping: 30, delay: 0.05 }}
      className="min-w-0"
    >
      <h1 className="text-base font-semibold text-[var(--color-text-primary)] leading-tight">Voice Bridge</h1>
      <p className="text-xs text-[var(--color-text-muted)] truncate">Talk to Agentium in real time</p>
    </motion.div>

    {/* Connection status + connect button */}
    <motion.div
      initial={{ opacity: 0, x: 20 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ type: 'spring', stiffness: 300, damping: 30, delay: 0.1 }}
      className="flex items-center gap-3 flex-shrink-0"
    >
      {/* 3D-style status dot (pure CSS) */}
      <div className="flex items-center gap-2">
        <motion.span
          data-testid="connection-status-dot"
          className="relative w-3 h-3 rounded-full"
          style={{
            backgroundColor: statusColor,
            boxShadow: `0 0 8px ${statusColor}, 0 0 16px ${statusColor}40`,
          }}
          animate={isConnecting || isError ? { 
            boxShadow: [`0 0 8px ${statusColor}`, `0 0 16px ${statusColor}80`, `0 0 8px ${statusColor}`],
            transition: { duration: 1.5, repeat: Infinity }
          } : {}}
          aria-hidden="true"
        />
        <span className="text-xs font-medium text-[var(--color-text-secondary)] capitalize">
          {status === 'reconnecting' ? 'Reconnecting' : status}
        </span>
      </div>

      <motion.button
        onClick={handleConnect}
        disabled={isBusy}
        className={cn(
          'inline-flex items-center justify-center gap-2 px-4 py-2 text-sm font-medium rounded-lg transition-colors duration-150',
          status === 'connected'
            ? 'bg-[var(--c-subtle)] hover:bg-[var(--c-hairline)] dark:bg-[var(--c-panel-2)] dark:hover:bg-[var(--c-hairline)] text-[var(--color-text-secondary)] dark:text-[var(--color-text-muted)]'
            : 'bg-[var(--c-brand)] hover:bg-[var(--c-brand-hover)] text-white shadow-sm dark:shadow-[0_4px_14px_var(--c-brand)/30]'
        )}
        whileHover={{ scale: 1.02 }}
        whileTap={{ scale: 0.98 }}
        style={{ transition: prefersReduced ? 'none' : undefined }}
      >
        {isBusy && <Loader2 className="w-4 h-4 animate-spin" aria-hidden="true" />}
        {status === 'connected' ? 'Disconnect' : isBusy ? 'Connecting…' : 'Connect'}
      </motion.button>
    </motion.div>
  </div>
</motion.header>
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npm test -- --testPathPattern="VoiceBridgeContainer.header" --run`
Expected: PASS

- [ ] **Step 5: Manual verification**

- [ ] Open page in browser
- [ ] Verify brand orb has gradient background + glow shadow
- [ ] Verify connection dot shows correct color per status (connected=green, connecting=amber, error=red, disconnected=slate)
- [ ] Verify dot pulses when connecting/error
- [ ] Verify connect button has spring hover/tap
- [ ] Verify theme toggle (light/dark) updates all colors in 220ms
- [ ] Verify reduced motion disables animations

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/voice-bridge/VoiceBridgeContainer.tsx frontend/src/components/voice-bridge/__tests__/VoiceBridgeContainer.header.test.tsx
git commit -m "feat(voice-bridge): elevate header with gradient brand orb, animated status dot, spring motion"
```

---

### Task 2: Visualization Wrapper — Depth Layers & Glassmorphism

**Files:**
- Modify: `frontend/src/components/voice-bridge/VoiceBridgeContainer.tsx:151-167` (visualization section)

**Interfaces:**
- Consumes: `voiceState`, `prefersReduced` from hooks
- Produces: Shared wrapper for both ThreeScene and Canvas2DFallback

- [ ] **Step 1: Write failing test for visualization wrapper**

```tsx
// frontend/src/components/voice-bridge/__tests__/VoiceBridgeContainer.visualization.test.tsx
import { render, screen } from '@testing-library/react';
import { VoiceBridgeContainer } from '../VoiceBridgeContainer';

describe('VoiceBridgeContainer Visualization Wrapper', () => {
  it('renders radial glow layer matching voice state', () => {
    render(<VoiceBridgeContainer />);
    const glowLayer = screen.getByTestId('viz-radial-glow');
    expect(glowLayer).toHaveStyle({
      background: expect.stringMatching(/radial-gradient/),
    });
  });

  it('renders dot grid overlay matching AgentsPage', () => {
    render(<VoiceBridgeContainer />);
    const dotGrid = screen.getByTestId('viz-dot-grid');
    expect(dotGrid).toHaveStyle({
      backgroundImage: expect.stringMatching(/radial-gradient/),
      backgroundSize: '24px 24px',
    });
  });

  it('renders vignette fade layers', () => {
    render(<VoiceBridgeContainer />);
    const vignetteTop = screen.getByTestId('viz-vignette-top');
    const vignetteBottom = screen.getByTestId('viz-vignette-bottom');
    expect(vignetteTop).toHaveStyle({
      background: expect.stringMatching(/gradient-to-t/),
    });
    expect(vignetteBottom).toHaveStyle({
      background: expect.stringMatching(/gradient-to-b/),
    });
  });

  it('wraps ThreeScene in Suspense with LoadingFallback', () => {
    render(<VoiceBridgeContainer />);
    expect(screen.getByTestId('viz-loading-fallback')).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm test -- --testPathPattern="VoiceBridgeContainer.visualization" --run`
Expected: FAIL

- [ ] **Step 3: Implement visualization wrapper**

```tsx
// In VoiceBridgeContainer.tsx, replace visualization section (lines 151-167):

{/* ── Three.js Canvas ── */}
<motion.section
  initial={{ opacity: 0, y: 20 }}
  animate={{ opacity: 1, y: 0 }}
  transition={{ type: 'spring', stiffness: 300, damping: 30, delay: 0.15 }}
  className="relative flex-1 overflow-hidden"
>
  {/* Depth layer 1: Radial glow matching voice state */}
  <motion.div
    data-testid="viz-radial-glow"
    className="absolute inset-0 pointer-events-none"
    style={{
      background: `radial-gradient(ellipse at center, var(--c-voice-glow) 0%, transparent 70%)`,
      opacity: voiceState === 'listening' || voiceState === 'speaking' ? 1 : 0.3,
    }}
    animate={{ opacity: voiceState === 'listening' || voiceState === 'speaking' ? 1 : 0.3 }}
    transition={{ duration: 300, ease: 'easeOut' }}
  />
  
  {/* Depth layer 2: Dot grid (matches AgentsPage) */}
  <div
    data-testid="viz-dot-grid"
    className="absolute inset-0 pointer-events-none opacity-[0.06]"
    style={{
      backgroundImage: 'radial-gradient(circle, var(--c-hairline) 1px, transparent 1px)',
      backgroundSize: '24px 24px',
    }}
  />
  
  {/* Depth layer 3: Vignette fade top */}
  <div
    data-testid="viz-vignette-top"
    className="absolute inset-0 pointer-events-none bg-gradient-to-t from-[var(--c-canvas)]/60 via-transparent to-transparent"
  />
  
  {/* Depth layer 4: Vignette fade bottom */}
  <div
    data-testid="viz-vignette-bottom"
    className="absolute inset-0 pointer-events-none bg-gradient-to-b from-[var(--c-canvas)]/60 via-transparent to-transparent"
  />
  
  {/* The visualization */}
  <Suspense fallback={
    <div data-testid="viz-loading-fallback" className="absolute inset-0 flex items-center justify-center bg-[var(--c-canvas)]">
      <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-[var(--c-brand)]" aria-label="Loading 3D visualization" />
    </div>
  }>
    <ThreeScene
      voiceState={voiceState}
      micLevel={micLevel}
      timeDomainData={timeDomainData ?? null}
      frequencyData={frequencyData ?? null}
      status={status}
      prefersReduced={prefersReduced}
    />
  </Suspense>
</motion.section>
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npm test -- --testPathPattern="VoiceBridgeContainer.visualization" --run`
Expected: PASS

- [ ] **Step 5: Manual verification**

- [ ] Open page — verify radial glow appears when listening/speaking
- [ ] Verify dot grid visible (subtle, matches AgentsPage)
- [ ] Verify vignette fades at top/bottom
- [ ] Verify ThreeScene loads inside wrapper
- [ ] Verify theme toggle updates all layers
- [ ] Verify reduced motion doesn't break wrapper

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/voice-bridge/VoiceBridgeContainer.tsx frontend/src/components/voice-bridge/__tests__/VoiceBridgeContainer.visualization.test.tsx
git commit -m "feat(voice-bridge): add visualization wrapper with radial glow, dot grid, vignette layers"
```

---

### Task 3: Canvas2DFallback — Complete Visual Overhaul

**Files:**
- Modify: `frontend/src/components/voice-bridge/Canvas2DFallback.tsx` (entire file — complete rewrite)

**Interfaces:**
- Consumes: `voiceState`, `micLevel`, `timeDomainData`, `frequencyData`, `status`, `prefersReduced` (via props)
- Produces: Premium 2D canvas visualization matching GPU quality

- [ ] **Step 1: Write failing tests for Canvas2DFallback drawing functions**

```tsx
// frontend/src/components/voice-bridge/__tests__/Canvas2DFallback.test.tsx
import { render, screen, act } from '@testing-library/react';
import { Canvas2DFallback } from '../Canvas2DFallback';
import { vi, describe, it, expect, beforeEach } from 'vitest';

// Mock canvas context
const mockContext = {
  fillRect: vi.fn(),
  clearRect: vi.fn(),
  beginPath: vi.fn(),
  arc: vi.fn(),
  fill: vi.fn(),
  stroke: vi.fn(),
  moveTo: vi.fn(),
  lineTo: vi.fn(),
  closePath: vi.fn(),
  createRadialGradient: vi.fn(() => ({ addColorStop: vi.fn() })),
  createLinearGradient: vi.fn(() => ({ addColorStop: vi.fn() })),
  save: vi.fn(),
  restore: vi.fn(),
  translate: vi.fn(),
  scale: vi.fn(),
  fillStyle: '',
  strokeStyle: '',
  lineWidth: 1,
  globalAlpha: 1,
};

const mockCanvas = {
  getContext: vi.fn(() => mockContext),
  width: 600,
  height: 400,
  clientWidth: 600,
  clientHeight: 400,
};

vi.spyOn(document, 'createElement').mockImplementation((tag) => {
  if (tag === 'canvas') return mockCanvas;
  return document.createElement(tag);
});

describe('Canvas2DFallback', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders canvas with correct dimensions', () => {
    render(<Canvas2DFallback voiceState="idle" micLevel={0} timeDomainData={null} frequencyData={null} status="connected" />);
    const canvas = screen.getByRole('img');
    expect(canvas).toBeInTheDocument();
  });

  it('calls drawOrb with gradient glow rings when voiceState is listening', () => {
    const timeDomainData = new Uint8Array(256).fill(128);
    const frequencyData = new Uint8Array(48).map((_, i) => i * 5);
    
    render(<Canvas2DFallback 
      voiceState="listening" 
      micLevel={0.5} 
      timeDomainData={timeDomainData} 
      frequencyData={frequencyData} 
      status="connected" 
    />);
    
    // Verify radial gradient called for orb glow
    expect(mockContext.createRadialGradient).toHaveBeenCalled();
  });

  it('calls drawFrequencyBars with spring-damped scale', () => {
    const frequencyData = new Uint8Array(48).fill(200);
    
    render(<Canvas2DFallback 
      voiceState="speaking" 
      micLevel={0.8} 
      timeDomainData={null} 
      frequencyData={frequencyData} 
      status="connected" 
    />);
    
    // Verify bars drawn with gradient fills
    expect(mockContext.createLinearGradient).toHaveBeenCalled();
  });

  it('renders orbital particles for idle/listening states', () => {
    render(<Canvas2DFallback 
      voiceState="idle" 
      micLevel={0} 
      timeDomainData={null} 
      frequencyData={null} 
      status="connected" 
    />);
    
    // Verify arc called for particles
    expect(mockContext.arc).toHaveBeenCalled();
  });

  it('respects prefersReduced for orbital particles', () => {
    render(<Canvas2DFallback 
      voiceState="idle" 
      micLevel={0} 
      timeDomainData={null} 
      frequencyData={null} 
      status="connected" 
      prefersReduced={true}
    />);
    
    // Particles should not animate (but may still draw static)
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm test -- --testPathPattern="Canvas2DFallback" --run`
Expected: FAIL — drawing functions don't exist yet

- [ ] **Step 3: Implement complete Canvas2DFallback rewrite**

```tsx
// frontend/src/components/voice-bridge/Canvas2DFallback.tsx — COMPLETE REPLACEMENT
import { useEffect, useRef, useCallback, useMemo } from 'react';
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

const BAR_COUNT = 48;
const PARTICLE_COUNT = 12;
const ORB_BASE_RADIUS = 80;

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
  const barHeightsRef = useRef<number[]>(Array(BAR_COUNT).fill(0));
  const { prefersReduced: prefersReducedHook } = useReducedMotion();
  const prefersReduced = prefersReducedProp || prefersReducedHook;

  // Get status color using CSS variables via computed style
  const getStatusColor = useCallback((status: ConnectionStatus): string => {
    const style = getComputedStyle(document.documentElement);
    switch (status) {
      case 'connected': return style.getPropertyValue('--c-success').trim() || '#10b981';
      case 'connecting': return style.getPropertyValue('--c-warning').trim() || '#f59e0b';
      case 'reconnecting': return style.getPropertyValue('--c-voice-listening').trim() || '#3b82f6';
      case 'error': return style.getPropertyValue('--c-error').trim() || '#ef4444';
      default: return style.getPropertyValue('--color-text-muted').trim() || '#64748b';
    }
  }, []);

  const statusColor = getStatusColor(status);
  const isConnected = status === 'connected';
  const isConnecting = status === 'connecting' || status === 'reconnecting';
  const isError = status === 'error';

  // Get state colors from CSS variables
  const getStateColors = useCallback((state: VoiceState) => {
    const style = getComputedStyle(document.documentElement);
    const colors = {
      listening: { primary: '#3b82f6', glow: '#3b82f6', bg: '#dbeafe' },
      speaking: { primary: '#059669', glow: '#059669', bg: '#d1fae5' },
      processing: { primary: '#7c3aed', glow: '#7c3aed', bg: '#ede9fe' },
      error: { primary: '#ef4444', glow: '#ef4444', bg: '#fee2e2' },
      muted: { primary: '#9ca3af', glow: '#9ca3af', bg: '#f3f4f6' },
      idle: { primary: '#64748b', glow: '#64748b', bg: '#f1f5f9' },
    };
    
    // Override with CSS variables if available
    const listeningVar = style.getPropertyValue('--c-voice-listening').trim();
    const speakingVar = style.getPropertyValue('--c-voice-speaking').trim();
    const thinkingVar = style.getPropertyValue('--c-voice-thinking').trim();
    const errorVar = style.getPropertyValue('--c-voice-error').trim();
    
    if (listeningVar) colors.listening = { primary: listeningVar, glow: listeningVar, bg: `${listeningVar}20` };
    if (speakingVar) colors.speaking = { primary: speakingVar, glow: speakingVar, bg: `${speakingVar}20` };
    if (thinkingVar) colors.processing = { primary: thinkingVar, glow: thinkingVar, bg: `${thinkingVar}20` };
    if (errorVar) colors.error = { primary: errorVar, glow: errorVar, bg: `${errorVar}20` };
    
    return colors[state];
  }, []);

  // Orb pulse scale calculation
  const getOrbPulseScale = useCallback((state: VoiceState, micLevel: number, time: number): number => {
    if (prefersReduced) return 1;
    const basePulse = Math.sin(time * 3) * 0.04;
    const micInfluence = micLevel * 0.5 + 0.5;
    if (state === 'listening' || state === 'speaking') {
      return 1 + basePulse * micInfluence;
    }
    if (state === 'processing') {
      return 1 + Math.sin(time * 2) * 0.03;
    }
    if (state === 'error') {
      return 1 + Math.sin(time * 10) * 0.08;
    }
    return 1 + Math.sin(time * 1.5) * 0.02;
  }, [prefersReduced]);

  // Initialize canvas
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const resize = () => {
      const container = canvas.parentElement;
      if (!container) return;
      const width = container.clientWidth;
      const height = container.clientHeight;
      if (width === 0 || height === 0) return;
      
      const dpr = Math.min(window.devicePixelRatio, 2);
      canvas.width = width * dpr;
      canvas.height = height * dpr;
      canvas.style.width = `${width}px`;
      canvas.style.height = `${height}px`;
      ctx.scale(dpr, dpr);
    };

    resize();
    window.addEventListener('resize', resize);

    // Animation loop
    const animate = () => {
      if (!canvasRef.current) return;
      animationRef.current = requestAnimationFrame(animate);
      timeRef.current += 1/60;
      
      const canvas = canvasRef.current;
      const ctx = canvas.getContext('2d');
      if (!ctx) return;
      
      const width = canvas.width / (Math.min(window.devicePixelRatio, 2));
      const height = canvas.height / (Math.min(window.devicePixelRatio, 2));
      const cx = width / 2;
      const cy = height / 2 - 20; // Slightly above center
      
      // Clear
      ctx.clearRect(0, 0, width, height);
      
      // Draw background (handled by wrapper, but ensure transparent)
      ctx.fillStyle = 'transparent';
      ctx.fillRect(0, 0, width, height);
      
      // 1. Draw orbital particles (idle/listening only)
      if ((voiceState === 'idle' || voiceState === 'listening') && !prefersReduced) {
        drawOrbitalParticles(ctx, cx, cy, ORB_BASE_RADIUS, voiceState, micLevel, timeRef.current);
      }
      
      // 2. Draw orb with gradient glow rings
      drawOrb(ctx, cx, cy, ORB_BASE_RADIUS, voiceState, micLevel, timeRef.current);
      
      // 3. Draw frequency bars (if data available)
      if (frequencyData && frequencyData.length > 0) {
        drawFrequencyBars(ctx, frequencyData, width, 120, cx, cy + ORB_BASE_RADIUS + 40, voiceState);
      }
      
      // 4. Draw waveform (if data available)
      if (timeDomainData && timeDomainData.length > 0) {
        drawWaveform(ctx, timeDomainData, width, 80, cx, cy + ORB_BASE_RADIUS + 180, voiceState);
      }
    };
    
    animate();
    
    return () => {
      window.removeEventListener('resize', resize);
      if (animationRef.current) cancelAnimationFrame(animationRef.current);
    };
  }, [voiceState, micLevel, timeDomainData, frequencyData, prefersReduced]);

  // Drawing functions
  function drawOrb(ctx: CanvasRenderingContext2D, cx: number, cy: number, radius: number, state: VoiceState, micLevel: number, time: number) {
    const colors = getStateColors(state);
    const pulseScale = getOrbPulseScale(state, micLevel, time);
    
    ctx.save();
    ctx.translate(cx, cy);
    ctx.scale(pulseScale, pulseScale);
    ctx.translate(-cx, -cy);
    
    // Ring 1: Outer glow pulse (largest)
    const ringGradient1 = ctx.createRadialGradient(cx, cy, radius * 0.6, cx, cy, radius * 1.8);
    ringGradient1.addColorStop(0, colors.glow + '30');
    ringGradient1.addColorStop(0.4, colors.glow + '10');
    ringGradient1.addColorStop(1, 'transparent');
    ctx.beginPath();
    ctx.arc(cx, cy, radius * 1.8, 0, Math.PI * 2);
    ctx.fillStyle = ringGradient1;
    ctx.fill();
    
    // Ring 2: Mid pulse
    const ringGradient2 = ctx.createRadialGradient(cx, cy, radius * 0.4, cx, cy, radius * 1.3);
    ringGradient2.addColorStop(0, colors.glow + '40');
    ringGradient2.addColorStop(0.5, colors.glow + '15');
    ringGradient2.addColorStop(1, 'transparent');
    ctx.beginPath();
    ctx.arc(cx, cy, radius * 1.3, 0, Math.PI * 2);
    ctx.fillStyle = ringGradient2;
    ctx.fill();
    
    // Ring 3: Core glow
    const ringGradient3 = ctx.createRadialGradient(cx, cy, 0, cx, cy, radius);
    ringGradient3.addColorStop(0, colors.primary);
    ringGradient3.addColorStop(0.7, colors.primary + 'CC');
    ringGradient3.addColorStop(1, colors.primary + '30');
    ctx.beginPath();
    ctx.arc(cx, cy, radius, 0, Math.PI * 2);
    ctx.fillStyle = ringGradient3;
    ctx.fill();
    
    // Inner core highlight
    const coreGradient = ctx.createRadialGradient(cx - radius * 0.2, cy - radius * 0.2, 0, cx, cy, radius * 0.5);
    coreGradient.addColorStop(0, '#ffffff80');
    coreGradient.addColorStop(1, 'transparent');
    ctx.beginPath();
    ctx.arc(cx, cy, radius * 0.5, 0, Math.PI * 2);
    ctx.fillStyle = coreGradient;
    ctx.fill();
    
    ctx.restore();
  }

  function drawOrbitalParticles(ctx: CanvasRenderingContext2D, cx: number, cy: number, radius: number, state: VoiceState, micLevel: number, time: number) {
    const colors = getStateColors(state);
    const particleAlpha = state === 'listening' ? 0.3 + 0.4 * micLevel : 0.15;
    
    for (let i = 0; i < PARTICLE_COUNT; i++) {
      const angle = (i / PARTICLE_COUNT) * Math.PI * 2 + time * 0.3;
      const r = radius * 1.3 + Math.sin(time * 2 + i * 0.5) * 8;
      const x = cx + Math.cos(angle) * r;
      const y = cy + Math.sin(angle) * r * 0.6; // Elliptical orbit
      
      ctx.beginPath();
      ctx.arc(x, y, 2, 0, Math.PI * 2);
      ctx.fillStyle = colors.primary.replace(')', `, ${particleAlpha})`).replace('rgb', 'rgba').replace('#', '');
      // Convert hex to rgba for alpha
      const hex = colors.primary.replace('#', '');
      const r255 = parseInt(hex.slice(0, 2), 16);
      const g255 = parseInt(hex.slice(2, 4), 16);
      const b255 = parseInt(hex.slice(4, 6), 16);
      ctx.fillStyle = `rgba(${r255}, ${g255}, ${b255}, ${particleAlpha})`;
      ctx.fill();
    }
  }

  function drawFrequencyBars(
    ctx: CanvasRenderingContext2D, 
    frequencyData: Uint8Array, 
    width: number, 
    maxHeight: number, 
    cx: number, 
    baseY: number,
    state: VoiceState
  ) {
    const barWidth = (width * 0.8) / BAR_COUNT * 0.6;
    const gap = (width * 0.8) / BAR_COUNT * 0.4;
    const startX = cx - (width * 0.8) / 2;
    
    frequencyData.forEach((value, i) => {
      if (i >= BAR_COUNT) return;
      const targetHeight = (value / 255) * maxHeight;
      
      // Spring damping per bar
      const currentHeight = barHeightsRef.current[i] || 0;
      const newHeight = currentHeight + (targetHeight - currentHeight) * 0.15;
      barHeightsRef.current[i] = newHeight;
      
      const x = startX + i * (barWidth + gap) + gap;
      const y = baseY - newHeight;
      
      // Gradient: green (bass) → amber (mid) → red (treble)
      const ratio = i / BAR_COUNT;
      const barGradient = ctx.createLinearGradient(0, baseY, 0, y);
      if (ratio < 0.4) { 
        barGradient.addColorStop(0, '#10b981'); 
        barGradient.addColorStop(1, '#34d399'); 
      } else if (ratio < 0.7) { 
        barGradient.addColorStop(0, '#f59e0b'); 
        barGradient.addColorStop(1, '#fbbf24'); 
      } else { 
        barGradient.addColorStop(0, '#ef4444'); 
        barGradient.addColorStop(1, '#f87171'); 
      }
      
      // Rounded rect
      roundRect(ctx, x, y, barWidth, newHeight, 4);
      ctx.fillStyle = barGradient;
      ctx.fill();
    });
  }

  function drawWaveform(
    ctx: CanvasRenderingContext2D, 
    timeDomainData: Uint8Array, 
    width: number, 
    height: number, 
    cx: number, 
    baseY: number,
    state: VoiceState
  ) {
    const colors = getStateColors(state);
    const waveWidth = width * 0.9;
    const startX = cx - waveWidth / 2;
    const centerY = baseY + height / 2;
    
    // Main waveform gradient
    const waveGradient = ctx.createLinearGradient(0, centerY - height / 2, 0, centerY + height / 2);
    waveGradient.addColorStop(0, colors.primary);
    waveGradient.addColorStop(0.5, colors.primary + '80');
    waveGradient.addColorStop(1, 'transparent');
    
    ctx.beginPath();
    ctx.moveTo(startX, centerY);
    
    timeDomainData.forEach((value, i) => {
      const x = startX + (i / (timeDomainData.length - 1)) * waveWidth;
      const y = centerY + ((value / 255) - 0.5) * height;
      ctx.lineTo(x, y);
    });
    
    ctx.lineTo(startX + waveWidth, centerY + height / 2);
    ctx.lineTo(startX, centerY + height / 2);
    ctx.closePath();
    ctx.fillStyle = waveGradient;
    ctx.fill();
    
    // Mirror reflection (fade)
    const reflectionGradient = ctx.createLinearGradient(0, centerY + height / 2, 0, centerY + height);
    reflectionGradient.addColorStop(0, colors.primary + '30');
    reflectionGradient.addColorStop(1, 'transparent');
    
    ctx.beginPath();
    ctx.moveTo(startX, centerY);
    timeDomainData.forEach((value, i) => {
      const x = startX + (i / (timeDomainData.length - 1)) * waveWidth;
      const y = centerY - ((value / 255) - 0.5) * height * 0.5; // Compressed reflection
      ctx.lineTo(x, y);
    });
    ctx.lineTo(startX + waveWidth, centerY);
    ctx.lineTo(startX, centerY);
    ctx.closePath();
    ctx.fillStyle = reflectionGradient;
    ctx.fill();
  }

  // Helper: Rounded rectangle
  function roundRect(ctx: CanvasRenderingContext2D, x: number, y: number, w: number, h: number, r: number) {
    ctx.beginPath();
    ctx.moveTo(x + r, y);
    ctx.lineTo(x + w - r, y);
    ctx.quadraticCurveTo(x + w, y, x + w, y + r);
    ctx.lineTo(x + w, y + h - r);
    ctx.quadraticCurveTo(x + w, y + h, x + w - r, y + h);
    ctx.lineTo(x + r, y + h);
    ctx.quadraticCurveTo(x, y + h, x, y + h - r);
    ctx.lineTo(x, y + r);
    ctx.quadraticCurveTo(x, y, x + r, y);
    ctx.closePath();
  }

  // Status indicator (top-right)
  const statusDotStyle = {
    position: 'absolute',
    top: 16,
    right: 16,
    width: 8,
    height: 8,
    borderRadius: '50%',
    background: statusColor,
    boxShadow: `0 0 8px ${statusColor}`,
    animation: isConnecting || isError ? 'pulse 1.5s ease-in-out infinite' : 'none',
  } as React.CSSProperties;

  return (
    <div
      style={{
        position: 'relative',
        width: '100%',
        height: '100%',
        minHeight: 300,
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
      }}
      className="canvas-2d-fallback"
      role="img"
      aria-label={`Voice bridge 2D visualization - ${voiceState} state, ${isConnected ? 'connected' : isConnecting ? 'connecting' : isError ? 'error' : 'disconnected'}`}
    >
      <canvas
        ref={canvasRef}
        style={{ display: 'block' }}
        aria-hidden="true"
      />
      
      <style>{`
        @keyframes pulse {
          0%, 100% { opacity: 1; transform: scale(1); }
          50% { opacity: 0.6; transform: scale(0.9); }
        }
      `}</style>

      <div style={statusDotStyle} aria-hidden="true" />
      
      {/* State Label */}
      <div
        style={{
          position: 'absolute',
          bottom: 24,
          left: '50%',
          transform: 'translateX(-50%)',
          fontSize: 14,
          fontWeight: 500,
          color: 'var(--color-text-muted)',
          textTransform: 'capitalize',
          letterSpacing: '0.05em',
        }}
        aria-live="polite"
      >
        {voiceState === 'processing' ? 'Thinking...' : voiceState}
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npm test -- --testPathPattern="Canvas2DFallback" --run`
Expected: PASS

- [ ] **Step 5: Manual verification (CRITICAL — this is the CPU path)**

- [ ] Open page in browser with WebGL disabled (or in environment without WebGL)
- [ ] Verify orb renders with 3 gradient glow rings
- [ ] Verify orb pulses smoothly based on micLevel and state
- [ ] Verify orbital particles orbit in idle/listening states
- [ ] Verify frequency bars animate with spring damping (0.15)
- [ ] Verify frequency bars have green→amber→red gradient by frequency position
- [ ] Verify waveform renders with gradient fill + mirror reflection
- [ ] Verify all colors use CSS variables (theme toggle works)
- [ ] Verify reduced motion disables particle orbit and orb pulse
- [ ] Verify status dot in top-right shows correct color
- [ ] Verify state label at bottom updates correctly

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/voice-bridge/Canvas2DFallback.tsx frontend/src/components/voice-bridge/__tests__/Canvas2DFallback.test.tsx
git commit -m "feat(voice-bridge): complete Canvas2DFallback overhaul — orb glow rings, orbital particles, spring bars, gradient waveform"
```

---

### Task 4: Transcript Panel — WidgetCard Wrapper & Enhancements

**Files:**
- Modify: `frontend/src/components/voice-bridge/VoiceBridgeContainer.tsx:169-191` (transcript section)
- Modify: `frontend/src/components/voice-bridge/TranscriptDisplay.tsx` (enhancements)

**Interfaces:**
- Consumes: `transcripts`, `handleClearTranscripts` from container
- Produces: Elevated transcript panel with WidgetCard wrapper

- [ ] **Step 1: Write failing tests**

```tsx
// frontend/src/components/voice-bridge/__tests__/TranscriptPanel.test.tsx
import { render, screen } from '@testing-library/react';
import { VoiceBridgeContainer } from '../VoiceBridgeContainer';
import { TranscriptDisplay } from '../TranscriptDisplay';
import { WidgetCard } from '@/components/dashboard/WidgetCard';
import { EmptyState } from '@/components/ui/EmptyState';

describe('Transcript Panel', () => {
  it('wraps TranscriptDisplay in WidgetCard', () => {
    render(<VoiceBridgeContainer />);
    expect(screen.getByText('Conversation')).toBeInTheDocument();
    expect(screen.getByTestId('transcript-widget-card')).toBeInTheDocument();
  });

  it('shows EmptyState when no transcripts', () => {
    render(<VoiceBridgeContainer />);
    expect(screen.getByText('No conversation yet')).toBeInTheDocument();
    expect(screen.getByText('Start speaking to see transcripts here')).toBeInTheDocument();
  });

  it('shows clear button when transcripts exist', () => {
    // Would need to mock transcripts
    render(<VoiceBridgeContainer />);
    // After adding mock transcripts
    expect(screen.getByRole('button', { name: /clear/i })).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm test -- --testPathPattern="TranscriptPanel" --run`
Expected: FAIL

- [ ] **Step 3: Implement Transcript Panel with WidgetCard wrapper**

```tsx
// In VoiceBridgeContainer.tsx, replace transcript section (lines 169-191):

{/* ── Transcript Panel ── */}
<motion.section
  initial={{ opacity: 0, y: 20 }}
  animate={{ opacity: 1, y: 0 }}
  transition={{ type: 'spring', stiffness: 300, damping: 30, delay: 0.25 }}
  className="flex-shrink-0 w-full max-w-2xl mx-auto px-6 pb-8"
>
  <WidgetCard
    data-testid="transcript-widget-card"
    title="Conversation"
    icon={MessageSquare}
    className="h-[320px] flex flex-col"
    action={
      transcripts.length > 0 && (
        <motion.button
          onClick={handleClearTranscripts}
          className="p-1.5 rounded-lg bg-[var(--c-subtle)] hover:bg-[var(--c-hairline)] dark:bg-[var(--c-panel-2)] dark:hover:bg-[var(--c-hairline)] text-[var(--color-text-muted)] hover:text-[var(--c-error)] transition-colors"
          whileHover={{ scale: 1.1 }}
          whileTap={{ scale: 0.9 }}
          aria-label="Clear transcript"
        >
          <Trash2 className="w-3.5 h-3.5" aria-hidden="true" />
        </motion.button>
      )
    }
  >
    <TranscriptDisplay transcripts={transcripts} maxHeight={280} className="flex-1" />
    
    {/* Scroll shadow hint */}
    <div className="relative">
      <div className="absolute bottom-0 left-0 right-0 h-8 bg-gradient-to-t from-[var(--c-panel)] to-transparent pointer-events-none" />
    </div>
  </WidgetCard>
</motion.section>
```

- [ ] **Step 4: Enhance TranscriptDisplay.tsx**

```tsx
// In TranscriptDisplay.tsx, update the empty state (lines 61-77) and add copy tooltip:

// Replace empty state block (lines 61-77):
if (transcripts.length === 0) {
  return (
    <div className={`flex flex-col items-center justify-center h-full text-center p-8 ${className}`} role="status" aria-live="polite">
      <EmptyState
        illustration="chat"
        icon={MessageSquare}
        title="No conversation yet"
        description="Start speaking to see transcripts here"
        size="md"
      />
    </div>
  );
}

// In the copy button handler (lines 55-59), add tooltip state:
const [copiedTooltip, setCopiedTooltip] = useState<{ index: number; timeout: NodeJS.Timeout } | null>(null);

// Update handleCopy:
const handleCopy = (text: string, index: number) => {
  navigator.clipboard.writeText(text);
  setCopiedIndex(index);
  if (copiedTooltip) clearTimeout(copiedTooltip.timeout);
  const timeout = setTimeout(() => {
    setCopiedIndex(null);
    setCopiedTooltip(null);
  }, 2000);
  setCopiedTooltip({ index, timeout });
};

// Update copy button render (lines 151-163):
<div className="absolute top-1 right-1 opacity-0 group-hover:opacity-100 transition-opacity flex items-center gap-1">
  <button
    onClick={() => handleCopy(entry.text, index)}
    className="relative p-1.5 rounded-lg bg-[var(--c-panel)]/80 dark:bg-[var(--c-panel)]/50 hover:bg-[var(--c-subtle)] dark:hover:bg-[var(--c-subtle-dark)] text-[var(--color-text-muted)] hover:text-[var(--color-text-primary)] transition-colors shadow-sm"
    aria-label="Copy message"
  >
    {copiedIndex === index ? (
      <motion.span
        initial={{ opacity: 0, scale: 0.5, y: -10 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        exit={{ opacity: 0, scale: 0.5, y: -10 }}
        className="absolute -top-6 left-1/2 -translate-x-1/2 whitespace-nowrap px-2 py-1 text-xs bg-[var(--c-success)] text-white rounded"
      >
        Copied!
      </motion.span>
    ) : (
      <Copy className="w-3.5 h-3.5" />
    )}
  </button>
</div>

// Add AnimatePresence import if not present:
import { motion, AnimatePresence, type Variants } from 'framer-motion';
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `npm test -- --testPathPattern="TranscriptPanel|TranscriptDisplay" --run`
Expected: PASS

- [ ] **Step 6: Manual verification**

- [ ] Open page — verify transcript panel wrapped in WidgetCard with proper styling
- [ ] Verify empty state uses EmptyState component with chat illustration + float animation
- [ ] Verify clear button appears when transcripts exist, with spring hover/tap
- [ ] Verify scroll shadow hint at bottom
- [ ] Verify copy button shows "Copied!" tooltip with animation
- [ ] Verify streaming char animation still works (spring stiffness 500)
- [ ] Verify theme toggle updates all colors
- [ ] Verify reduced motion disables animations

- [ ] **Step 7: Commit**

```bash
git add frontend/src/components/voice-bridge/VoiceBridgeContainer.tsx frontend/src/components/voice-bridge/TranscriptDisplay.tsx frontend/src/components/voice-bridge/__tests__/TranscriptPanel.test.tsx
git commit -m "feat(voice-bridge): elevate transcript panel with WidgetCard wrapper, EmptyState, copy tooltip"
```

---

### Task 5: Controls Bar — Floating Glass Pill & Enhanced VoiceControls

**Files:**
- Modify: `frontend/src/components/voice-bridge/VoiceBridgeContainer.tsx:193-208` (controls section)
- Modify: `frontend/src/components/voice-bridge/VoiceControls.tsx` (enhancements)

**Interfaces:**
- Consumes: `voiceState`, `isConnected`, `isMuted`, `isRecording`, handlers from container
- Produces: Floating glass pill with enhanced controls

- [ ] **Step 1: Write failing tests**

```tsx
// frontend/src/components/voice-bridge/__tests__/ControlsBar.test.tsx
import { render, screen } from '@testing-library/react';
import { VoiceBridgeContainer } from '../VoiceBridgeContainer';
import { VoiceControls } from '../VoiceControls';

describe('Controls Bar', () => {
  it('wraps VoiceControls in floating glass pill', () => {
    render(<VoiceBridgeContainer />);
    const pill = screen.getByTestId('controls-glass-pill');
    expect(pill).toHaveStyle({
      backdropFilter: 'blur(40px)', // backdrop-blur-2xl
      backgroundColor: expect.stringMatching(/var\(--c-glass-bg\)/),
    });
  });

  it('VoiceControls primary button shows expanding pulse ring when recording', () => {
    render(<VoiceControls isConnected isRecording onRecord={vi.fn()} onStop={vi.fn()} onMuteToggle={vi.fn()} onSettings={vi.fn()} />);
    const pulseRing = screen.getByTestId('record-pulse-ring');
    expect(pulseRing).toBeInTheDocument();
  });

  it('VoiceControls settings button has rotate spring on hover', () => {
    render(<VoiceControls isConnected onSettings={vi.fn()} />);
    const settingsBtn = screen.getByRole('button', { name: /open voice settings/i });
    expect(settingsBtn).toHaveAttribute('while-hover', expect.stringMatching(/rotate/));
  });

  it('VoiceControls status text includes state icon', () => {
    render(<VoiceControls isConnected voiceState="listening" />);
    expect(screen.getByText(/listening/i)).toBeInTheDocument();
    // Should have pulsing dot icon
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm test -- --testPathPattern="ControlsBar" --run`
Expected: FAIL

- [ ] **Step 3: Implement Controls Bar floating glass pill**

```tsx
// In VoiceBridgeContainer.tsx, replace controls section (lines 193-208):

{/* ── Controls ── */}
<motion.section
  initial={{ opacity: 0, y: 20, scale: 0.98 }}
  animate={{ opacity: 1, y: 0, scale: 1 }}
  transition={{ type: 'spring', stiffness: 300, damping: 30, delay: 0.4 }}
  className="flex-shrink-0"
>
  <div className="max-w-2xl mx-auto px-6 pb-6">
    <div data-testid="controls-glass-pill" className="relative">
      {/* Glass pill background */}
      <div className="absolute inset-0 bg-[var(--c-glass-bg)] border border-[var(--c-glass-border)] rounded-3xl backdrop-blur-2xl shadow-2xl dark:shadow-[0_8px_40px_rgba(0,0,0,0.4)]" />
      
      {/* Actual controls */}
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
        className="relative z-10 px-4 py-4"
      />
    </div>
  </div>
</motion.section>
```

- [ ] **Step 4: Enhance VoiceControls.tsx**

```tsx
// In VoiceControls.tsx, add pulse ring keyframes and enhance components:

// Add at top of file (after imports):
const pulseRingStyles = `
  @keyframes pulseRing {
    0% { transform: scale(1); opacity: 0.6; }
    100% { transform: scale(1.8); opacity: 0; }
  }
  .pulse-ring {
    animation: pulseRing 1.5s ease-out infinite;
  }
  @media (prefers-reduced-motion: reduce) {
    .pulse-ring { animation: none; }
  }
`;

// Inject styles once (useEffect with empty deps):
useEffect(() => {
  const styleEl = document.createElement('style');
  styleEl.textContent = pulseRingStyles;
  document.head.appendChild(styleEl);
  return () => document.head.removeChild(styleEl);
}, []);

// State icons mapping (add after BUTTON_VARIANTS):
const stateIcons = {
  idle: <Mic className="w-4 h-4" />,
  listening: <motion.span className="w-2 h-2 rounded-full bg-[var(--c-voice-listening)]" animate={{ opacity: [1, 0.5, 1] }} transition={{ duration: 1, repeat: Infinity }} />,
  speaking: <Volume2 className="w-4 h-4" />,
  processing: <Loader2 className="w-4 h-4 animate-spin" />,
  error: <AlertCircle className="w-4 h-4" />,
  muted: <MicOff className="w-4 h-4" />,
};

// Update primary button render (around line 147-193):
<motion.button
  className={getPrimaryButtonClass()}
  onClick={handleRecordClick}
  disabled={!isConnected}
  aria-label={isRecording ? 'Stop recording' : 'Start recording'}
  aria-pressed={isRecording}
  variants={buttonTapVariants}
  whileTap="tap"
  whileHover={isConnected && !isRecording ? 'hover' : undefined}
  whileFocus="focus"
  style={{ transition: prefersReduced ? 'none' : undefined }}
>
  {isRecording && (
    <>
      <motion.div
        data-testid="record-pulse-ring"
        className="pulse-ring absolute inset-0 rounded-full border-2"
        style={{ borderColor: 'currentColor', pointerEvents: 'none' }}
        animate={!prefersReduced ? {} : { opacity: 0 }}
      />
      <motion.div
        className="w-8 h-8 rounded bg-white"
        animate={{ scale: prefersReduced ? 1 : [1, 0.8, 1] }}
        transition={{ duration: 0.8, repeat: Infinity, ease: 'easeInOut' }}
        aria-hidden="true"
      />
    </>
  ) : voiceState === 'processing' || voiceState === 'speaking' ? (
    <motion.div
      className="w-8 h-8"
      animate={{ rotate: prefersReduced ? 0 : 360 }}
      transition={{ duration: 1, repeat: Infinity, ease: 'linear' }}
      aria-hidden="true"
    >
      <svg className="w-full h-full text-current" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
        <circle cx="12" cy="12" r="10" strokeOpacity="0.25" />
        <path d="M12 2a10 10 0 0 1 10 10" strokeLinecap="round" strokeOpacity="1" />
      </svg>
    </motion.div>
  ) : (
    <Mic className="w-8 h-8" aria-hidden="true" />
  )}
</motion.button>

// Update settings button (around line 196-207):
<motion.button
  className={getSettingsButtonClass()}
  onClick={onSettings}
  disabled={!isConnected}
  aria-label="Open voice settings"
  variants={settingsButtonVariants}
  whileHover={{ rotate: prefersReduced ? 0 : 30, transition: { type: 'spring', stiffness: 400, damping: 20 } }}
  whileTap={{ rotate: 0, scale: 0.9 }}
  style={{ transition: prefersReduced ? 'none' : undefined }}
>
  <Settings className="w-5 h-5" aria-hidden="true" />
</motion.button>

// Update status text (around line 210-231):
<motion.p
  className="text-center text-sm text-[var(--color-text-secondary)] max-w-md px-4 flex items-center justify-center gap-2"
  initial={{ opacity: 0 }}
  animate={{ opacity: 1 }}
  transition={{ delay: 0.3 }}
  aria-live="polite"
  aria-atomic="true"
>
  {stateIcons[voiceState] || stateIcons.idle}
  <span>
    {!isConnected
      ? 'Voice bridge disconnected. Click connect above to start.'
      : isMuted
      ? 'Microphone muted'
      : isRecording
      ? 'Listening... Speak now'
      : voiceState === 'processing'
      ? 'Processing...'
      : voiceState === 'speaking'
      ? 'Speaking...'
      : voiceState === 'idle'
      ? 'Tap the mic or say "Hey Agentium" to start'
      : 'Ready'}
  </span>
</motion.p>
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `npm test -- --testPathPattern="ControlsBar|VoiceControls" --run`
Expected: PASS

- [ ] **Step 6: Manual verification**

- [ ] Open page — verify controls float in glass pill with backdrop blur
- [ ] Verify primary button shows expanding pulse ring when recording
- [ ] Verify pulse ring respects prefers-reduced-motion
- [ ] Verify settings button rotates 30° on hover (spring)
- [ ] Verify mute button transitions smoothly
- [ ] Verify status text shows correct icon per state
- [ ] Verify status text typography improved (flex layout with icon)
- [ ] Verify theme toggle updates all colors
- [ ] Verify reduced motion disables all animations

- [ ] **Step 7: Commit**

```bash
git add frontend/src/components/voice-bridge/VoiceBridgeContainer.tsx frontend/src/components/voice-bridge/VoiceControls.tsx frontend/src/components/voice-bridge/__tests__/ControlsBar.test.tsx
git commit -m "feat(voice-bridge): elevate controls bar with floating glass pill, pulse ring, settings rotate spring, richer status"
```

---

### Task 6: ThreeScene/Three.js — Color Sync & Parallax

**Files:**
- Modify: `frontend/src/components/voice-bridge/ThreeScene.tsx` (color sync, parallax)
- Modify: `frontend/src/components/voice-bridge/VoiceOrb3D.tsx` (verify color sync)

**Interfaces:**
- Consumes: `useThreeColors` hook, `voiceState`, `prefersReduced`
- Produces: GPU visualization with perfect design system color sync

- [ ] **Step 1: Write failing tests**

```tsx
// frontend/src/components/voice-bridge/__tests__/ThreeSceneColorSync.test.tsx
import { render, screen } from '@testing-library/react';
import { ThreeScene } from '../ThreeScene';
import { useThreeColors } from '../hooks/useThreeColors';

// Mock Three.js
vi.mock('three', () => ({
  WebGLRenderer: vi.fn(() => ({
    setPixelRatio: vi.fn(),
    setSize: vi.fn(),
    domElement: document.createElement('canvas'),
    dispose: vi.fn(),
  })),
  Scene: vi.fn(() => ({ add: vi.fn() })),
  OrthographicCamera: vi.fn(),
  AmbientLight: vi.fn(),
  DirectionalLight: vi.fn(),
  PointLight: vi.fn(),
  EffectComposer: vi.fn(() => ({ addPass: vi.fn(), render: vi.fn(), setSize: vi.fn(), dispose: vi.fn() })),
  RenderPass: vi.fn(),
  UnrealBloomPass: vi.fn(),
  FXAAPass: vi.fn(),
  Clock: vi.fn(() => ({ getDelta: vi.fn(() => 1/60) })),
  Vector2: vi.fn(),
  SRGBColorSpace: 'srgb',
  ACESFilmicToneMapping: 1,
}));

describe('ThreeScene Color Sync', () => {
  it('syncs colors from CSS variables via useThreeColors', () => {
    // Verify useThreeColors reads --c-voice-listening, --c-voice-speaking, etc.
    const colors = useThreeColors();
    expect(colors).toHaveProperty('listening');
    expect(colors).toHaveProperty('speaking');
    expect(colors).toHaveProperty('thinking');
    expect(colors).toHaveProperty('error');
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm test -- --testPathPattern="ThreeSceneColorSync" --run`
Expected: FAIL (or incomplete coverage)

- [ ] **Step 3: Enhance ThreeScene.tsx for color sync verification**

```tsx
// In ThreeScene.tsx, ensure useThreeColors is used correctly and add parallax:

// In ThreeSceneInner component, verify color mapping:
const stateColor = colors[voiceState === 'idle' ? 'idle' : voiceState === 'muted' ? 'muted' : voiceState === 'error' ? 'error' : voiceState === 'processing' ? 'thinking' : voiceState];

// Pass to components that need it:
<VoiceOrb3D
  size={220}
  state={voiceState}
  micLevel={micLevel}
  frequencyData={frequencyData}
  colors={colors}
  prefersReduced={prefersReduced}
/>

// Add subtle parallax on mouse move (disabled in reduced motion)
const containerRef = useMemo(() => ({ current: null as HTMLDivElement | null }), []);
const mouseRef = useRef({ x: 0, y: 0 });

useEffect(() => {
  if (prefersReduced) return;
  
  const handleMouseMove = (e: MouseEvent) => {
    if (!containerRef.current) return;
    const rect = containerRef.current.getBoundingClientRect();
    mouseRef.current.x = (e.clientX - rect.left) / rect.width - 0.5;
    mouseRef.current.y = (e.clientY - rect.top) / rect.height - 0.5;
  };
  
  containerRef.current?.addEventListener('mousemove', handleMouseMove);
  return () => containerRef.current?.removeEventListener('mousemove', handleMouseMove);
}, [prefersReduced]);

// In render, apply parallax to camera:
<div
  ref={containerRef}
  style={{ position: 'relative', width: '100%', height: '100%', minHeight: 300 }}
  className="three-canvas"
>
  <ThreeProvider
    scene={three.scene}
    camera={three.camera}
    renderer={three.renderer}
    composer={three.composer}
    clock={three.clock}
    mouse={mouseRef.current} // Pass mouse for parallax
  >
    {/* ... components */}
  </ThreeProvider>
</div>
```

- [ ] **Step 4: Verify VoiceOrb3D uses colors correctly**

```tsx
// In VoiceOrb3D.tsx, ensure it uses colors prop from ThreeScene:
// Should already work if it destructures colors prop and uses colors.listening, etc.
// Verify no hardcoded colors — all from colors prop
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `npm test -- --testPathPattern="ThreeScene|VoiceOrb3D" --run`
Expected: PASS

- [ ] **Step 6: Manual verification (GPU path)**

- [ ] Open page in browser with WebGL enabled
- [ ] Verify ThreeScene loads without error
- [ ] Verify orb colors match CSS variables exactly (compare with 2D fallback)
- [ ] Verify theme toggle updates Three.js colors in 220ms sync
- [ ] Verify subtle parallax on mouse move (desktop only)
- [ ] Verify parallax disabled in reduced motion
- [ ] Verify bloom, FXAA post-processing active
- [ ] Verify particle field, frequency bars, waveform surface render

- [ ] **Step 7: Commit**

```bash
git add frontend/src/components/voice-bridge/ThreeScene.tsx frontend/src/components/voice-bridge/VoiceOrb3D.tsx
git commit -m "feat(voice-bridge): verify ThreeScene color sync, add reduced-motion-aware parallax"
```

---

### Task 7: Global Motion Orchestration & Integration Testing

**Files:**
- Modify: `frontend/src/components/voice-bridge/VoiceBridgeContainer.tsx` (wrap entire content in motion.div with variants)

**Interfaces:**
- Consumes: All section components
- Produces: Staggered page entrance animation

- [ ] **Step 1: Write failing test**

```tsx
// frontend/src/components/voice-bridge/__tests__/PageMotionOrchestration.test.tsx
import { render, screen } from '@testing-library/react';
import { VoiceBridgeContainer } from '../VoiceBridgeContainer';
import { motion } from 'framer-motion';

describe('Page Motion Orchestration', () => {
  it('wraps all sections in motion.div with staggerChildren', () => {
    render(<VoiceBridgeContainer />);
    const pageWrapper = screen.getByTestId('page-motion-wrapper');
    expect(pageWrapper).toHaveAttribute('data-framer-motion-initial', '{"opacity":0}');
    expect(pageWrapper).toHaveAttribute('data-framer-motion-animate', '{"opacity":1}');
    // Should have staggerChildren in transition
  });

  it('sections have staggered entrance delays', () => {
    render(<VoiceBridgeContainer />);
    const header = screen.getByTestId('voice-bridge-header');
    const visualization = screen.getByTestId('visualization-section');
    const transcript = screen.getByTestId('transcript-section');
    const controls = screen.getByTestId('controls-section');
    
    // Each should have increasing delay
    expect(header).toHaveAttribute('data-framer-motion-transition', expect.stringMatching(/delay.*0/));
    expect(visualization).toHaveAttribute('data-framer-motion-transition', expect.stringMatching(/delay.*0\.1/));
    expect(transcript).toHaveAttribute('data-framer-motion-transition', expect.stringMatching(/delay.*0\.2/));
    expect(controls).toHaveAttribute('data-framer-motion-transition', expect.stringMatching(/delay.*0\.3/));
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm test -- --testPathPattern="PageMotionOrchestration" --run`
Expected: FAIL

- [ ] **Step 3: Implement global motion orchestration**

```tsx
// In VoiceBridgeContainer.tsx, wrap entire return content:

const pageVariants = {
  hidden: { opacity: 0 },
  visible: {
    opacity: 1,
    transition: {
      staggerChildren: 0.1,
      delayChildren: 0.1,
    },
  },
};

const sectionVariants = {
  hidden: { opacity: 0, y: 20 },
  visible: { 
    opacity: 1, 
    y: 0, 
    transition: { type: 'spring', stiffness: 300, damping: 30 }
  },
};

// Replace the outer div (line 118):
return (
  <motion.div
    data-testid="page-motion-wrapper"
    variants={pageVariants}
    initial="hidden"
    animate="visible"
    className={`h-full flex flex-col bg-[var(--c-canvas)] transition-colors duration-200 ${className}`}
  >
    <motion.header
      data-testid="voice-bridge-header"
      variants={sectionVariants}
      // ... existing header props
    >
      {/* header content */}
    </motion.header>

    <motion.section
      data-testid="visualization-section"
      variants={sectionVariants}
      className="relative flex-1 overflow-hidden"
    >
      {/* visualization wrapper + ThreeScene */}
    </motion.section>

    <motion.section
      data-testid="transcript-section"
      variants={sectionVariants}
      className="flex-shrink-0 w-full max-w-2xl mx-auto px-6 pb-8"
    >
      {/* transcript panel */}
    </motion.section>

    <motion.footer
      data-testid="controls-section"
      variants={sectionVariants}
      className="flex-shrink-0"
    >
      {/* controls bar */}
    </motion.footer>

    <VoiceSettings ... />
  </motion.div>
);
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npm test -- --testPathPattern="PageMotionOrchestration" --run`
Expected: PASS

- [ ] **Step 5: Manual verification — Full page integration**

- [ ] Open page — verify staggered entrance: header → visualization → transcript → controls
- [ ] Verify each section springs in smoothly
- [ ] Verify theme toggle works across ALL sections simultaneously (220ms)
- [ ] Verify reduced motion disables ALL springs (instant)
- [ ] Test CPU path (disable WebGL) — full flow works
- [ ] Test GPU path — full flow works
- [ ] Connect → record → speak → process → stop flow
- [ ] Settings modal opens/closes
- [ ] Transcript streams correctly
- [ ] No console errors
- [ ] Mobile responsive (320px, 768px, 1024px, 1440px)

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/voice-bridge/VoiceBridgeContainer.tsx frontend/src/components/voice-bridge/__tests__/PageMotionOrchestration.test.tsx
git commit -m "feat(voice-bridge): add global staggered motion orchestration, full integration"
```

---

### Task 8: Final Polish & Dual-Path Verification Checklist

**Files:**
- Review: All modified files

**Interfaces:**
- N/A — verification task

- [ ] **Step 1: Run full test suite**

Run: `npm test -- --run`
Expected: All tests PASS

- [ ] **Step 2: Run lint & type-check**

Run: `npm run lint && npm run type-check`
Expected: No errors

- [ ] **Step 3: Manual dual-path verification (CRITICAL)**

| Test | CPU (2D) | GPU (3D) |
|------|----------|----------|
| Page loads without error | [ ] | [ ] |
| Visualization renders correctly | [ ] Canvas2DFallback | [ ] ThreeScene |
| Voice state changes reflect visually | [ ] | [ ] |
| Theme toggle (light/dark) | [ ] 220ms sync | [ ] 220ms sync |
| Reduced motion disables all animation | [ ] CSS + Framer | [ ] Three.js uniforms frozen |
| Keyboard navigation works | [ ] | [ ] |
| Screen reader announces status | [ ] | [ ] |
| Connect/disconnect flow | [ ] | [ ] |
| Recording start/stop | [ ] | [ ] |
| Settings modal opens/closes | [ ] | [ ] |
| Transcript streaming animation | [ ] | [ ] |
| No memory leaks (10min session) | [ ] | [ ] |
| Mobile responsive (320px+) | [ ] | [ ] |

- [ ] **Step 4: Performance check**

- [ ] Open Chrome DevTools → Performance tab
- [ ] Record 10s interaction
- [ ] Verify 60fps (no long frames > 16ms)
- [ ] Verify no layout shift (CLS = 0)
- [ ] Verify GPU acceleration (transform/opacity only)

- [ ] **Step 5: Final commit**

```bash
git add -A
git commit -m "feat(voice-bridge): complete layout redesign — premium polish with dual-path parity

- Header: gradient brand orb, animated status dot, spring connect button
- Visualization: radial glow, dot grid, vignette layers (both paths)
- Canvas2DFallback: orb glow rings, orbital particles, spring bars, gradient waveform+reflection
- Transcript: WidgetCard wrapper, EmptyState, copy tooltip
- Controls: floating glass pill, pulse ring, settings rotate spring, richer status
- ThreeScene: color sync verified, reduced-motion parallax
- Global: staggered spring entrance, 220ms theme sync
- Accessibility: ARIA, keyboard, reduced motion, WCAG AA contrast
- Design system: 100% CSS variable compliance"
```

---

## Execution Handoff

**Plan complete and saved to:** `docs/superpowers/plans/2026-07-27-voice-bridge-layout-redesign.md`

**Two execution options:**

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration
- **REQUIRED SUB-SKILL:** Use superpowers:subagent-driven-development
- Fresh subagent per task + two-stage review

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints
- **REQUIRED SUB-SKILL:** Use superpowers:executing-plans
- Batch execution with checkpoints for review

**Which approach?**
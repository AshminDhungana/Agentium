# Voice Bridge Page Redesign — Immersive Hero Layout with Living Organism Orb

> **Goal:** Transform the Voice Bridge page into a premium, immersive SaaS experience matching Dashboard/Agents quality. Full-screen hero visualization with floating glass UI panels. CPU-first Canvas 2D implementation with Three.js GPU parity. Living Organism Orb that morphs between states organically.

---

## Global Constraints (from CLAUDE.md & existing codebase)

- **Design tokens**: Use CSS variables from `index.css` exclusively — `--c-canvas`, `--c-panel`, `--c-brand`, `--c-voice-*`, `--c-glass-*`, `--color-text-*`, `--c-success/warning/error`, `--c-hairline`
- **Glassmorphism**: `backdrop-blur-xl`, semi-transparent backgrounds, `--c-glass-border` borders
- **Motion**: Framer Motion spring physics `stiffness: 300, damping: 30`, staggerChildren for entrances
- **Accessibility**: `prefers-reduced-motion` respected, ARIA live regions, semantic HTML, WCAG AA contrast
- **Theme sync**: 220ms `transition-colors duration-200` across all elements
- **Dual-path**: ThreeScene (GPU) + Canvas2DFallback (CPU) with auto-fallback via `useThreeScene` hook
- **Component patterns**: `WidgetCard`, `EmptyState`, shadcn/ui primitives
- **Testing**: Vitest + React Testing Library, jsdom with Canvas/WebGL mocks

---

## Architecture: Immersive Hero Layout

```
┌─────────────────────────────────────────────────────────────┐
│  FULL VIEWPORT (100vh × 100vw)                              │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  CANVAS LAYER (fixed, inset-0, z-0)                 │   │
│  │  ┌─────────────────────────────────────────────┐   │   │
│  │  │        LIVING ORGANISM ORB (center)         │   │   │
│  │  │  • 3-ring gradient system                   │   │   │
│  │  │  • State morph animation (idle→listen→speak)│   │   │
│  │  │  • Surface noise/shimmer                    │   │   │
│  │  │  • Particle atmosphere                      │   │   │
│  │  │  • Audio-reactive aperture                  │   │   │
│  │  └─────────────────────────────────────────────┘   │   │
│  │  • Radial glow atmosphere (state-colored)         │   │
│  │  • Subtle grid pattern (opacity 0.02)             │   │
│  │  • Vignette edges (fade to --c-canvas)            │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  FLOATING GLASS PANELS (z-10, absolute)             │   │
│  │                                                     │   │
│  │  TOP-RIGHT: Status badge (compact, animated dot)   │   │
│  │                                                     │   │
│  │  BOTTOM-CENTER: Controls Pill (glass, rounded-3xl) │   │
│  │    [Mute] [● Record/Stop] [Settings]                │   │
│  │    State label with icon (ARIA live)                │   │
│  │                                                     │   │
│  │  BOTTOM-LEFT (collapsed): Transcript drawer handle  │   │
│  │  ▼ Expand → Floating panel (320px wide, max-h-80)   │   │
│  │       WidgetCard wrapper, EmptyState when empty     │   │
│  │       Streaming chars animation                     │   │
│  └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

**Layout variants:**
- **Desktop (≥1024px)**: Full immersive as above
- **Tablet (768-1023px)**: Transcript drawer becomes bottom sheet (swipe up)
- **Mobile (<768px)**: Transcript modal drawer, controls always visible, orb scales to 80vw

---

## Living Organism Orb — Visual Specification

### State Definitions

| State | Aperture | Surface | Particles | Color Shift | Motion |
|-------|----------|---------|-----------|-------------|--------|
| **Idle** | Closed (small core) | Slow breathing pulse (1.0→1.03×) | Drifting orbit (slow, sparse) | Neutral slate | Organic sway, 6s cycle |
| **Listening** | Expanding (aperture opens) | Ripple waves from center | Inward spiral flow, velocity ∝ micLevel | → `--c-voice-listening` (blue) | Responsive, spring-damped |
| **Speaking** | Fully open | Radiating waveform rings | Outward burst streams, trails | → `--c-voice-speaking` (emerald) | Rhythmic, audio-synced |
| **Processing** | Contracting iris | Geometric rotation facets | Concentric rings, slowing | → `--c-voice-thinking` (purple) | Deliberate, 2s rotation |
| **Error** | Jagged flutter | Distortion spikes | Explosive scatter | → `--c-voice-error` (red) | Sharp, damped oscillation |
| **Muted** | Sealed | Dimmed, desaturated | Frozen, minimal | Desaturated neutral | Static |

### 3-Ring Gradient System (CPU Canvas 2D)

```
┌─ OUTER RING (1.5× base radius)
│  Radial gradient: transparent → stateColor/15% → stateColor/30%
│  ShadowBlur: 60px, stateColor/25%
│  Animation: slow scale pulse (1.0→1.08×, 4s ease-in-out)
│
├─ MID RING (1.15× base radius) — THE BRAND RING
│  Conic gradient: 0° stateColor → 120° brandColor → 240° accentColor → 360° stateColor
│  Stroke width: 3px (scaled by DPR)
│  Animation: rotation (30s/rev idle, 8s/rev active)
│  Blob distortion: noise-based radius variance (±8px)
│
└─ INNER CORE (0.9× base radius)
   Radial gradient: center highlight → stateColor → stateColor/90%
   Specular: offset radial gradient (white/40% at -20%,-20%)
   Aperture mask: circular clip-path animated (0% closed → 100% open)
```

### Surface Detail (CPU-friendly)

**Noise Shader Simulation** — Instead of WebGL shaders, use:
- Pre-rendered noise texture (64×64 canvas, cached) drawn with `globalCompositeOperation: 'overlay'`
- Or: multiple radial gradients with phase offsets creating interference patterns
- Animation: translate noise pattern slowly (0.5px/frame) for "living membrane" feel

**Aperture Animation** — Circular sector clip:
```javascript
// Idle: 15% open (tiny pupil)
// Listening: micLevel × 85% + 15% (reactive)
// Speaking: 90% + waveform modulation
// Processing: 5% (contracted iris)
// Error: rapid flutter 5%↔25% (10Hz)
```

---

## Floating Glass Panel System

### Controls Pill (Bottom Center, Always Visible)
```tsx
<motion.div 
  className="fixed bottom-6 left-1/2 -translate-x-1/2 z-20"
  initial={{ opacity: 0, y: 30 }}
  animate={{ opacity: 1, y: 0 }}
  transition={{ type: 'spring', stiffness: 300, damping: 30, delay: 0.4 }}
>
  <div className="relative">
    {/* Glass background */}
    <div className="absolute inset-0 bg-[var(--c-glass-bg)] 
      border border-[var(--c-glass-border)] rounded-3xl 
      backdrop-blur-2xl shadow-2xl" />
    
    {/* Content */}
    <VoiceControls 
      className="relative z-10 px-6 py-4" 
      reducedMotion={prefersReduced}
    />
  </div>
</motion.div>
```

**VoiceControls upgrades:**
- Primary button: Living pulse ring (CSS keyframes + `prefers-reduced-motion`)
- State icon: Dynamic SVG morphing (Mic → Waveform → Loader → Alert → MicOff)
- Settings button: Spring rotate (30°) on hover
- Label: ARIA live region with polished copy per state

### Transcript Drawer (Bottom-Left, Expandable)
```tsx
// Collapsed: Floating handle button
<motion.button
  className="fixed bottom-6 left-6 z-20 glass-pill"
  initial={{ opacity: 0, x: -30 }}
  animate={{ opacity: 1, x: 0 }}
  transition={{ type: 'spring', delay: 0.5 }}
  onClick={toggleTranscript}
>
  <MessageSquare className="w-5 h-5" />
  <span className="hidden sm:inline ml-2">Transcript</span>
  <motion.span className="ml-1" animate={{ rotate: isOpen ? 180 : 0 }}>
    <ChevronUp className="w-4 h-4" />
  </motion.span>
</motion.button>

// Expanded: Floating panel (AnimatePresence)
<AnimatePresence>
  {isOpen && (
    <motion.div
      className="fixed bottom-24 left-6 z-20 w-96 max-h-[60vh]"
      initial={{ opacity: 0, y: 20, scale: 0.95 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      exit={{ opacity: 0, y: 20, scale: 0.95 }}
      transition={{ type: 'spring', stiffness: 300, damping: 30 }}
    >
      <WidgetCard className="flex flex-col h-full">
        <TranscriptDisplay 
          transcripts={transcripts} 
          maxHeight={400} 
          className="flex-1" 
        />
      </WidgetCard>
    </motion.div>
  )}
</AnimatePresence>
```

### Status Badge (Top-Right)
- Compact glass pill with animated dot + text
- Dot: Spring scale pulse when connecting, steady when connected
- Color: CSS variable resolved (`--c-success`, `--c-warning`, `--c-voice-listening`, `--c-error`)

---

## Canvas 2D Implementation — Living Orb

### Animation Loop Architecture
```typescript
// Single RAF loop with delta-time physics
const animate = (timestamp: number) => {
  const dt = Math.min((timestamp - lastTime) / 1000, 1/30); // cap at 30fps min
  lastTime = timestamp;
  
  // 1. Update physics (spring systems, particle positions)
  updateOrbPhysics(dt);
  updateParticles(dt);
  updateAperture(dt);
  
  // 2. Render layers (back to front)
  renderAtmosphere();
  renderParticleField();
  renderOrbRings();
  renderCoreWithAperture();
  renderSurfaceNoise();
  
  // 3. Schedule next
  if (!prefersReduced) requestAnimationFrame(animate);
};
```

### Spring Physics (Critically Damped)
```typescript
// Avatar scale spring
const springConfig = { stiffness: 180, damping: 22 }; // critically damped
// Aperture spring  
const apertureSpring = { stiffness: 300, damping: 30 }; // snappy
// Particle physics
const particleDrag = 0.98;
```

### Performance Optimizations (CPU Path)
- **Offscreen canvas** for static noise texture (generated once)
- **Particle pooling** — reuse objects, no GC pressure
- **Dirty rect rendering** — only redraw changed regions (optional, complexity trade-off)
- **DPR clamping** — `Math.min(devicePixelRatio, 2)` for HiDPI without overdraw
- **Reduced motion** — skip physics, render single static frame at target state

---

## ThreeScene Parity (GPU Path)

The ThreeScene must mirror the Living Orb visual language:

| CPU Technique | GPU Equivalent |
|---------------|----------------|
| 3 radial gradient rings | 3 `MeshBasicMaterial` with `transparent: true`, custom shader for conic mid-ring |
| Noise overlay | Shader noise (`snoise`) on sphere surface |
| Aperture mask | Shader `discard` or alpha test with animated threshold |
| Particle field | `InstancedMesh` (2000 particles), GPU vertex animation |
| Waveform rings | `RingGeometry` with shader displacement |

**Shaders needed:**
- `orb-surface.glsl`: Noise + color gradient + aperture mask
- `orb-mid-ring.glsl`: Conic gradient + blob distortion
- `particle-field.glsl`: Size/opacity by distance + audio uniform

---

## Motion Orchestration (Page Entrance)

```typescript
const pageVariants = {
  hidden: { opacity: 0 },
  visible: {
    opacity: 1,
    transition: {
      staggerChildren: 0.08,
      delayChildren: 0.15,
    },
  },
};

const sectionVariants = {
  hidden: { opacity: 0, y: 20, scale: 0.98 },
  visible: {
    opacity: 1,
    y: 0,
    scale: 1,
    transition: { type: 'spring', stiffness: 300, damping: 30 },
  },
};

// Applied to: Canvas (immediate), StatusBadge (0.1s), ControlsPill (0.2s), TranscriptHandle (0.3s)
```

---

## Accessibility Checklist

- [ ] `prefers-reduced-motion`: All spring physics disabled, static gradient frame rendered
- [ ] Canvas: `role="img"` + dynamic `aria-label` describing state + mic level
- [ ] ARIA live regions: Transcript (`polite`), Status label (`assertive` for errors), State changes
- [ ] Keyboard: `Tab` order — Status → Controls (Mute, Record, Settings) → Transcript toggle → Transcript items
- [ ] Focus visible: All interactive elements have `focus-visible:ring-2 focus-visible:ring-[var(--c-brand)]`
- [ ] Color contrast: All text on glass ≥ 4.5:1 (verify with `--c-glass-bg` + `--color-text-*`)
- [ ] Screen reader: Transcript entries have `role="log"`, speaker labels, timestamps

---

## Responsive Breakpoints

| Breakpoint | Layout Change |
|------------|---------------|
| `≥1280px` | Full immersive, transcript drawer 384px |
| `1024-1279px` | Full immersive, transcript drawer 320px |
| `768-1023px` | Transcript becomes bottom sheet (slide up), controls pill fixed |
| `<768px` | Orb 80vw, transcript modal drawer (full width), controls condensed |

---

## Files to Modify/Create

### Modify (Layout & Integration)
1. `VoiceBridgeContainer.tsx` — Complete restructuring to immersive hero layout
2. `ThreeScene.tsx` — Add Living Orb shaders, particle field, state morph logic
3. `Canvas2DFallback.tsx` — Rewrite with Living Orb physics + 3-ring system
4. `VoiceControls.tsx` — Upgrade to glass pill, living pulse, morphing state icon
5. `TranscriptDisplay.tsx` — Floating panel integration, streaming char animation
6. `index.css` — Add any missing design tokens (orb radii, animation durations)

### Create (New Components)
7. `CanvasOrb.tsx` — Shared orb logic extracted for both Three/Canvas paths
8. `TranscriptDrawer.tsx` — Floating panel with AnimatePresence
9. `StatusBadge.tsx` — Compact top-right indicator
10. `hooks/useOrbPhysics.ts` — Spring physics, aperture, state morph (shared)

### Tests
11. `VoiceBridgeContainer.immersive.test.tsx` — Layout, motion variants, ARIA
12. `Canvas2DFallback.living-orb.test.tsx` — State transitions, reduced motion
13. `VoiceControls.glass-pill.test.tsx` — Pulse ring, state icon, keyboard nav

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

## Success Criteria

1. **Visual Parity**: CPU Canvas 2D matches Three.js GPU quality (side-by-side indistinguishable)
2. **Layout Impact**: "Wow" factor on first load — immersive, premium, professional
3. **Animation Quality**: 60fps sustained, organic spring physics, no jank
4. **Accessibility**: Passes axe-core, keyboard navigable, reduced motion works
5. **Design Consistency**: Colors, glass, motion tokens identical to Dashboard/Agents
6. **Theme Sync**: 220ms transitions across all elements on theme toggle
7. **Responsive**: Works beautifully mobile → desktop

---

## Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| Canvas 2D performance on low-end | DPR clamp, particle count scaling, RAF throttling option |
| Shader complexity breaking on mobile | Fallback to simpler shader variant, test on device |
| Layout shift on transcript expand | Reserve space with `min-height`, `transform` only |
| Reduced motion looking "broken" | Design static frames as intentional "hero states" |
| Three.js bundle size | Lazy load (already via `Suspense`), code-split shaders |

---

**Next Step:** Create implementation plan via `writing-plans` skill.
# VoiceBridge Page Redesign - Design Specification

**Date**: 2026-07-26  
**Status**: Approved for Implementation  
**Approach**: Immersive 3D Audio Visualization (Approach 1)  
**Three.js Integration**: Full 3D with custom shaders, instanced meshes, post-processing  
**References**: [Three.js Audio Visualization Best Practices](https://tympanus.net/codrops/2023/12/19/creating-audio-reactive-visuals-with-dynamic-particles-in-three-js/), [2025 Three.js + GSAP + Web Audio](https://tympanus.net/codrops/2025/06/18/coding-a-3d-audio-visualizer-with-three-js-gsap-web-audio-api/), [WebGL Audio Techniques](https://visualizer.rojanacharya.com/blog/webgl-audio-visualization-techniques)

---

## 1. Executive Summary

Complete redesign of the VoiceBridge page (`frontend/src/pages/VoiceBridgePage.tsx`) with full Three.js 3D integration. The new design replaces all canvas-based visualizations (VoiceOrb, WaveformVisualizer, FrequencyBars) with GPU-accelerated Three.js equivalents featuring custom shaders, while maintaining exact fidelity to the existing Agentium design system (CSS variables from `frontend/src/index.css`).

**Key Goals**:
- Immersive 3D voice orb with state-reactive shaders
- 3D waveform surface and instanced frequency bars
- Ambient particle field reacting to audio
- Glassmorphism UI panels using existing design tokens
- Full dark/light mode parity via CSS variables
- Accessibility-first (ARIA, keyboard, reduced motion)

---

## 2. Architecture & Layout

### Page Structure
```
VoiceBridgePage (within MainLayout)
├── Header Bar (sticky, glassmorphism)
│   ├── Brand: "Voice Bridge" + live mic icon
│   ├── ConnectionStatus3D (orb + 3D status dot)
│   └── Connect/Disconnect (glass button)
├── ThreeScene Canvas (flex-1, centered)
│   ├── VoiceOrb3D (hero, center stage)
│   ├── WaveformSurface3D (below orb)
│   ├── FrequencyBars3D (instanced, surrounding)
│   └── ParticleField (ambient)
├── TranscriptPanel (slide-up, glassmorphism, max-h-[40vh])
└── ControlsBar (bottom, glassmorphism, fixed mobile)
    ├── Mute, Primary Record/Stop, Settings
    └── Status Text (live region)
```

### Responsive Behavior
| Breakpoint | Layout | Orb Size | Waveform |
|------------|--------|----------|----------|
| Mobile (< 640px) | Stacked, transcript slide-up | 140px | Full width, 120px tall |
| Tablet (640-1024px) | Side-by-side transcript | 180px | 400px wide |
| Desktop (> 1024px) | Three-column | 220px | 600px wide |

---

## 3. Three.js Scene Specification

### 3.1 Renderer & Camera
```typescript
// Renderer
const renderer = new THREE.WebGLRenderer({
  antialias: true,
  alpha: true,
  powerPreference: "high-performance",
  preserveDrawingBuffer: false,
});
renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
renderer.outputColorSpace = THREE.SRGBColorSpace;
renderer.toneMapping = THREE.ACESFilmicToneMapping;
renderer.toneMappingExposure = 1.0;

// Camera: Orthographic for consistent sizing
const aspect = containerWidth / containerHeight;
const frustumSize = 25;
const camera = new THREE.OrthographicCamera(
  (frustumSize * aspect) / -2,
  (frustumSize * aspect) / 2,
  frustumSize / 2,
  frustumSize / -2,
  0.1,
  100
);
camera.position.set(0, 0, 30);
camera.lookAt(0, 0, 0);
```

### 3.2 Lighting
| Light | Type | Position | Intensity | Color | Purpose |
|-------|------|----------|-----------|-------|---------|
| Ambient | AmbientLight | - | 0.35 | 0xffffff | Base fill |
| Key | DirectionalLight | (10, 15, 10) | 0.7 | 0xffffff | Orb highlights |
| State | PointLight | (0, 0, 0) | 1.5 | **Dynamic** | Orb glow (state color) |
| Rim | DirectionalLight | (-5, 5, -5) | 0.3 | 0x4444ff | Subtle rim |

### 3.3 Post-Processing (EffectComposer)
```typescript
const composer = new EffectComposer(renderer);
composer.addPass(new RenderPass(scene, camera));

// Bloom for orb glow - optimized resolution for performance
const bloomPass = new UnrealBloomPass(
  new THREE.Vector2(width, height),
  0.6,   // strength
  0.4,   // radius
  0.85,  // threshold
);
composer.addPass(bloomPass);

// FXAA (last) - using SMAA for better quality on modern devices
import { SMAAPass } from 'three/addons/postprocessing/SMAAPass.js';
const smaaPass = new SMAAPass(
  width * renderer.getPixelRatio(),
  height * renderer.getPixelRatio(),
);
composer.addPass(smaaPass);

// Optional: Chromatic aberration for speaking state emphasis
const chromaticPass = new ShaderPass(ChromaticAberrationShader);
chromaticPass.enabled = false; // Enable only during speaking
composer.addPass(chromaticPass);
```

**Performance Note**: On mobile or reduced capability devices, disable bloom and use FXAA instead of SMAA. The `EffectComposer` should be recreated on resize.

---

## 4. 3D Visualization Components

### 4.1 VoiceOrb3D (Hero Element)

**Geometry**: Dual-layer approach (inspired by 2025 Codrops tutorial)
- **Outer Layer**: `new THREE.IcosahedronGeometry(4.8, 2)` with wireframe `ShaderMaterial` (glowing edges)
- **Inner Layer**: `new THREE.IcosahedronGeometry(4.5, 2)` with `MeshPhysicalMaterial` (solid core)

**Outer Wireframe Material**: Custom `ShaderMaterial` with:
- Simplex noise vertex displacement
- Fresnel edge glow
- Audio-reactive pulse (bass → scale, mid → displacement, treble → edge intensity)

**Inner Core Material**: `THREE.MeshPhysicalMaterial` with `onBeforeCompile` injection:
```glsl
// Vertex: displacement
varying vec3 vNormal;
varying vec2 vUv;
uniform float uTime;
uniform float uBass;      // 0-1 normalized bass energy
uniform float uMid;       // 0-1 normalized mid energy
uniform float uTreble;    // 0-1 normalized treble energy

void main() {
  vNormal = normalize(normalMatrix * normal);
  vUv = uv;
  vec3 pos = position;
  
  // Multi-band displacement
  float displacement = 0.0;
  displacement += snoise(vec3(pos * 0.3 + uTime * 0.2, uTime * 0.5)) * uBass * 0.6;
  displacement += snoise(vec3(pos * 0.7 + uTime * 0.4, uTime * 0.3)) * uMid * 0.3;
  displacement += snoise(vec3(pos * 1.5 + uTime * 0.8, uTime)) * uTreble * 0.15;
  
  pos += normal * displacement;
  
  gl_Position = projectionMatrix * modelViewMatrix * vec4(pos, 1.0);
}
```

```glsl
// Fragment: fresnel glow + emissive pulse
varying vec3 vNormal;
varying vec2 vUv;
uniform vec3 uCoreColor;
uniform vec3 uGlowColor;
uniform float uTime;
uniform float uBass;
uniform float uPulsePhase;

void main() {
  vec3 viewDir = normalize(cameraPosition - (modelViewMatrix * vec4(position, 1.0)).xyz);
  float fresnel = pow(1.0 - dot(viewDir, vNormal), 3.0);
  
  // Core color with bass-reactive pulse
  vec3 color = uCoreColor * (1.0 + uBass * 0.3);
  
  // Pulsing emission pulse effect synced to beat
  float pulse = sin(uTime * 4.0 + uPulsePhase) * 0.5 + 0.5;
  color += uGlowColor * (fresnel * 0.8 + pulse * uBass * 0.4);
  
  gl_FragColor = vec4(color, 0.9);
}
```

**State Specifications** (using frequency bands from Web Audio Analyser):

| State | Bass (uBass) | Mid (uMid) | Treble (uTreble) | Wireframe | Core Material | Animation |
|-------|-------------|------------|------------------|-----------|---------------|-----------|
| **idle** | 0.1 | 0.1 | 0.05 | Subtle pulse (scale 1.0→1.015) | transmission 0, roughness 0.35, clearcoat 1.0 | Slow rotation (0.03 rad/s), gentle pulse |
| **listening** | micLevel×0.8 | micLevel×0.6 | micLevel×0.4 | Noise displacement active | transmission 0.1, roughness 0.15, clearcoat 1.0, emissive @ 0.3 | Pulse + noise displacement, particle attract |
| **speaking** | fft[0-10] avg | fft[10-50] avg | fft[50-100] avg | Frequency-reactive vertices | transmission 0.2, roughness 0.08, clearcoat 1.0, emissive @ 0.5 | Rotation (0.12 rad/s) + emission burst, chromatic aberration |
| **processing** | 0.15 | 0.2 | 0.1 | "Thinking" wave pattern | transmission 0.05, roughness 0.2, clearcoat 0.8, emissive thinking @ 0.4 | Gentle rotation + sinusoidal vertex wave |
| **error** | 0.6 | 0.3 | 0.2 | Sharp shake + red pulse | transmission 0, roughness 0.5, clearcoat 0, emissive error @ 0.6 | Red pulse, shake, particle burst, chromatic aberration |
| **muted** | 0 | 0 | 0 | Static, desaturated | transmission 0, roughness 0.8, clearcoat 0 | Static, slow desaturated pulse |

**Simplex Noise**: Use `three/examples/jsm/libs/simplex-noise.js` or inline GLSL implementation for vertex displacement.

### 4.2 WaveformSurface3D

**Geometry**: `new THREE.PlaneGeometry(20, 4, 200, 40)` → 8000 vertices  
**Material**: `THREE.ShaderMaterial` (translucent gradient surface)  
**Position**: `(0, -8, 0)` (below orb)

**Shader**:
```glsl
// Vertex: Y displacement from timeDomainData texture
uniform sampler2D uWaveTexture; // 256x1 data texture
uniform float uWaveAmplitude;

void main() {
  vec3 pos = position;
  float waveSample = texture2D(uWaveTexture, vec2(uv.x, 0.5)).r;
  pos.y += (waveSample - 0.5) * uWaveAmplitude * 2.0;
  gl_Position = projectionMatrix * modelViewMatrix * vec4(pos, 1.0);
}

// Fragment: gradient + grid lines
varying vec2 vUv;
uniform vec3 uColor;
uniform float uTime;

void main() {
  vec3 color = uColor * mix(0.2, 1.0, vUv.y);
  // Grid lines
  float grid = step(0.98, fract(vUv.x * 200.0)) + step(0.95, fract(vUv.y * 40.0));
  color = mix(color, uColor * 1.5, grid * 0.3);
  float alpha = 0.4 + 0.3 * vUv.y;
  gl_FragColor = vec4(color, alpha);
}
```

**Update**: `timeDomainData` → `DataTexture` (256×1, RedFormat) each frame

### 4.3 FrequencyBars3D (InstancedMesh)

**Geometry**: `new THREE.CylinderGeometry(0.08, 0.08, 1, 6, 1, true)` (open-ended)  
**Count**: 48 instances (matching `BAR_COUNT` from current)  
**Material**: Single `THREE.MeshPhysicalMaterial` with per-instance color via `instanceColor` attribute  
**Positioning**: Semi-circle around orb, radius 12, Y range -2 to 2

```typescript
// Instance attributes
const colors = new Float32Array(48 * 3);
const offsets = new Float32Array(48 * 3);
for (let i = 0; i < 48; i++) {
  const angle = (i / 48) * Math.PI - Math.PI / 2; // Semi-circle
  offsets[i * 3] = Math.cos(angle) * 12;
  offsets[i * 3 + 1] = -2 + (i / 48) * 4; // Y spread
  offsets[i * 3 + 2] = Math.sin(angle) * 12;
  
  // Color gradient: green → amber → red
  const ratio = i / 48;
  if (ratio < 0.5) { colors[i*3]=0.13; colors[i*3+1]=0.84; colors[i*3+2]=0.37; }
  else if (ratio < 0.75) { colors[i*3]=0.96; colors[i*3+1]=0.62; colors[i*3+2]=0.07; }
  else { colors[i*3]=0.94; colors[i*3+1]=0.27; colors[i*3+2]=0.27; }
}
```

**Animation**: Spring-damped `scaleY` per instance (target from `frequencyData`, damping 0.15)

### 4.4 ParticleField

**Geometry**: `THREE.BufferGeometry` with 2000 vertices  
**Material**: `THREE.PointsMaterial` with custom shader for size/opacity  
**Attributes**: `position`, `velocity`, `size`, `baseColor`, `phase`

```glsl
// Vertex: physics simulation
attribute vec3 velocity;
attribute float baseSize;
attribute vec3 baseColor;
attribute float phase;
uniform float uTime;
uniform float uDelta;
uniform float uMicLevel;
uniform int uState; // 0=idle, 1=listening, 2=speaking, 3=processing

void main() {
  vec3 pos = position;
  float t = uTime;
  
  if (uState == 1) { // listening - attract to center
    vec3 toCenter = -pos;
    pos += toCenter * uDelta * 0.5 * uMicLevel;
    pos += velocity * uDelta * 0.1;
  } else if (uState == 2) { // speaking - explode outward
    pos += velocity * uDelta * 2.0 * (1.0 + uMicLevel);
  } else if (uState == 3) { // processing - spiral
    float angle = t * 0.5 + phase;
    mat2 rot = mat2(cos(angle), -sin(angle), sin(angle), cos(angle));
    pos.xz = rot * pos.xz;
    pos.y += sin(t * 2.0 + phase) * 0.02;
  } else { // idle - drift
    pos += vec3(sin(t + phase) * 0.01, cos(t * 0.7 + phase) * 0.01, 0.0);
  }
  
  // Size based on distance to camera + audio level
  float size = baseSize * (1.0 + uMicLevel * 2.0) * (300.0 / length(modelViewMatrix * vec4(pos, 1.0)).xyz });
  gl_PointSize = size;
  gl_Position = projectionMatrix * modelViewMatrix * vec4(pos, 1.0);
  
  vColor = baseColor;
  vAlpha = 0.3 + 0.7 * uMicLevel;
}

// Fragment
varying vec3 vColor;
varying float vAlpha;
void main() {
  float dist = length(gl_PointCoord - 0.5);
  if (dist > 0.5) discard;
  float alpha = (1.0 - dist * 2.0) * vAlpha;
  gl_FragColor = vec4(vColor, alpha);
}
```

---

## 5. UI Components (React + Framer Motion)

### 5.1 Glassmorphism System
Using existing CSS variables from `index.css`:

```css
.glass-panel {
  background: var(--c-glass-bg);
  border: 1px solid var(--c-glass-border);
  backdrop-filter: blur(16px) saturate(180%);
  box-shadow: 
    0 4px 24px rgba(0,0,0,0.08),
    0 0 0 1px var(--c-glass-border);
}
.dark .glass-panel {
  box-shadow: 
    0 4px 24px rgba(0,0,0,0.3),
    0 0 0 1px var(--c-glass-border);
}
```

### 5.2 Component Specifications

| Component | Animation | Glassmorphism | Key Details |
|-----------|-----------|---------------|-------------|
| **Header** | Fade in (0.3s), slide down | Full width, sticky top-4 | ConnectionStatus3D dot uses Three.js sprite |
| **TranscriptPanel** | Slide up (y: 100%→0, spring), fade | max-h-[40vh], rounded-t-3xl | Auto-scroll, streaming char animation |
| **ControlsBar** | Fade in (0.4s delay), slide up | Fixed bottom mobile, sticky desktop | Primary btn: 3D ring expansion on record |
| **VoiceSettings** | Slide up (existing), glass | Full existing functionality | Tab navigation, range inputs |

### 5.3 Framer Motion Variants
```typescript
const panelVariants = {
  hidden: { opacity: 0, y: 20, scale: 0.98 },
  visible: { 
    opacity: 1, y: 0, scale: 1, 
    transition: { type: 'spring', stiffness: 300, damping: 30 } 
  },
  exit: { opacity: 0, y: -10, scale: 0.98, transition: { duration: 0.2 } }
};

const buttonVariants = {
  tap: { scale: 0.92 },
  hover: { scale: 1.05 },
  focus: { scale: 1.02 },
};

const recordRingVariants = {
  initial: { scale: 1, opacity: 0.6 },
  animate: { scale: [1, 1.5], opacity: [0.6, 0] },
  transition: { duration: 1.2, repeat: Infinity, ease: 'easeOut' }
};
```

### 5.4 Prefers-Reduced-Motion
```css
@media (prefers-reduced-motion: reduce) {
  .three-canvas * { animation: none !important; }
  .framer-motion * { transition: none !important; animation: none !important; }
}
```
In Three.js: skip vertex displacement, particle physics, rotation animations when `prefersReducedMotion` is true.

---

## 6. Color System (Exact Design System Match)

### CSS Variables (from `frontend/src/index.css`)

**Light Mode**:
```css
--c-canvas: #f9fafb;
--c-panel: #ffffff;
--c-panel-2: #f8fafc;
--c-hairline: #e5e7eb;
--c-subtle: #f3f4f6;
--c-brand: #2563eb;
--c-brand-soft: #dbeafe;
--c-brand-fg: #ffffff;
--c-voice-listening: #2563eb;     /* blue-600 */
--c-voice-speaking: #059669;      /* emerald-600 */
--c-voice-thinking: #7c3aed;      /* violet-600 */
--c-voice-error: #dc2626;         /* red-600 */
--c-voice-glow: rgba(37, 99, 235, 0.2);
--c-glass-bg: rgba(255, 255, 255, 0.85);
--c-glass-border: rgba(37, 99, 235, 0.12);
```

**Dark Mode**:
```css
--c-canvas: #0f1117;
--c-panel: #161b27;
--c-panel-2: #1c2333;
--c-hairline: #1e2535;
--c-subtle: #252f40;
--c-brand: #3b82f6;
--c-brand-soft: rgba(59, 130, 246, 0.12);
--c-brand-fg: #ffffff;
--c-voice-listening: #3b82f6;     /* blue-500 */
--c-voice-speaking: #10b981;      /* emerald-500 */
--c-voice-thinking: #8b5cf6;      /* violet-500 */
--c-voice-error: #ef4444;         /* red-500 */
--c-voice-glow: rgba(59, 130, 246, 0.3);
--c-glass-bg: rgba(22, 27, 39, 0.85);
--c-glass-border: rgba(59, 130, 246, 0.15);
```

### Three.js Color Sync
```typescript
// In VoiceBridgeContainer or ThreeScene hook
const syncColors = () => {
  const rootStyles = getComputedStyle(document.documentElement);
  const getColor = (varName: string) => new THREE.Color(
    rootStyles.getPropertyValue(varName).trim()
  );
  
  return {
    listening: getColor('--c-voice-listening'),
    speaking: getColor('--c-voice-speaking'),
    thinking: getColor('--c-voice-thinking'),
    error: getColor('--c-voice-error'),
    idle: new THREE.Color('#64748b'),
    muted: new THREE.Color('#9ca3af'),
    canvasBg: getColor('--c-canvas'),
    panelBg: getColor('--c-panel'),
    glassBorder: getColor('--c-glass-border'),
  };
};

// Listen for theme change
const observer = new MutationObserver(() => {
  const colors = syncColors();
  // Update all Three.js materials
  updateSceneColors(colors);
});
observer.observe(document.documentElement, { attributes: true, attributeFilter: ['class'] });
```

---

## 7. Accessibility

| Requirement | Implementation |
|-------------|----------------|
| **ARIA Live Regions** | Status text: `aria-live="polite" aria-atomic="true"` |
| **Keyboard Navigation** | All buttons focusable, Enter/Space activation, Escape closes settings |
| **Focus Indicators** | Uses existing `--c-brand` / `--c-brand-soft` focus rings |
| **Screen Readers** | `role="img" aria-label="Voice visualization: listening, microphone level: 45%"` |
| **Color Contrast** | All text meets WCAG AA (design system compliant) |
| **Reduced Motion** | CSS + Three.js + Framer Motion all respect `prefers-reduced-motion` |

---

## 8. Performance Budget

| Metric | Target | Strategy |
|--------|--------|----------|
| **Bundle Size** | < 150KB gzipped (Three.js) | Dynamic import (`React.lazy`), tree-shaking |
| **Initial Paint** | < 1.5s | Defer Three.js init until tab visible |
| **Animation FPS** | 60fps (120fps capable) | InstancedMesh, GPU shaders, minimal CPU work |
| **Memory** | < 100MB | Dispose geometries/materials, texture reuse |
| **Mobile** | 30fps minimum | Reduce particle count (2000→500), lower detail |

---

## 9. File Structure

### New Files
```
frontend/src/
├── components/voice-bridge/
│   ├── ThreeScene.tsx              # Three.js canvas, scene, camera, renderer, composer
│   ├── VoiceOrb3D.tsx              # Orb mesh with shader material
│   ├── WaveformSurface3D.tsx       # Plane with displacement shader
│   ├── FrequencyBars3D.tsx         # InstancedMesh bars
│   ├── ParticleField.tsx           # Points with custom shader
│   ├── ConnectionStatus3D.tsx      # Status indicator with 3D dot
│   ├── hooks/
│   │   ├── useThreeScene.ts        # Three.js lifecycle, resize, animation loop
│   │   ├── useThreeColors.ts       # CSS variable sync hook
│   │   └── useReducedMotion.ts     # prefers-reduced-motion hook
│   └── shaders/
│       ├── orbVertex.glsl
│       ├── orbFragment.glsl
│       ├── waveformVertex.glsl
│       ├── waveformFragment.glsl
│       ├── particleVertex.glsl
│       └── particleFragment.glsl
├── styles/
│   └── voice-bridge-three.css      # Three.js specific styles
└── pages/
    └── VoiceBridgePage.tsx         # Updated imports
```

### Modified Files
```
frontend/src/components/voice-bridge/
├── VoiceBridgeContainer.tsx        # Replace canvas viz with ThreeScene
├── VoiceControls.tsx               # Add 3D record ring, glassmorphism
├── TranscriptDisplay.tsx           # Glassmorphism panel
├── VoiceSettings.tsx               # Glassmorphism update
└── ConnectionStatus.tsx            # Keep compact for header
```

### Deprecated (keep for fallback)
```
VoiceOrb.tsx           → VoiceOrb3D.tsx
WaveformVisualizer.tsx → WaveformSurface3D.tsx
FrequencyBars.tsx      → FrequencyBars3D.tsx
MicrophoneLevel.tsx    → Keep (2D fallback)
```

---

## 10. Implementation Phases

| Phase | Deliverable | Est. Hours | Dependencies |
|-------|-------------|------------|--------------|
| **1. Foundation** | ThreeScene.tsx with renderer, camera, lighting, resize, composer | 3 | - |
| **2. VoiceOrb3D** | Orb geometry, MeshPhysicalMaterial, 6 state shaders, animation | 5 | Phase 1 |
| **3. WaveformSurface3D** | Plane, ShaderMaterial, DataTexture update, gradient shader | 3 | Phase 1 |
| **4. FrequencyBars3D** | InstancedMesh (48), spring animation, color gradient | 3 | Phase 1 |
| **5. ParticleField** | BufferGeometry (2000), physics shader, state behaviors | 3 | Phase 1 |
| **6. React Integration** | ThreeScene in Container, props flow, audio data bridge | 2 | Phases 2-5 |
| **7. UI Polish** | Glassmorphism panels, Transcript/Controls/Settings updates | 3 | Phase 6 |
| **8. Theme & Accessibility** | CSS var sync, dark/light, reduced motion, ARIA | 2 | Phase 7 |
| **9. Optimization** | Mobile profiling, bundle analysis, cleanup, testing | 3 | All |

**Total Estimated**: 27 hours

---

## 11. Risk Mitigation

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Three.js bundle size | High | Medium | Dynamic import, `@babel/plugin-transform-modules-commonjs` tree-shaking |
| Mobile GPU performance | Medium | High | Adaptive quality: reduce particles, disable bloom, lower geometry detail |
| Memory leaks | Medium | High | Strict `dispose()` in useEffect cleanup, WeakRef for textures |
| Theme sync race conditions | Low | Medium | MutationObserver + initial sync in useEffect |
| Audio visualization latency | Low | High | Use existing `useAudioVisualization` hook (AudioWorklet) |
| Browser WebGL support | Very Low | High | Fallback to canvas visualizations via capability detection |

---

## 12. Testing Checklist

- [ ] Light mode: all colors match design system exactly
- [ ] Dark mode: all colors match design system exactly
- [ ] Theme toggle: smooth 220ms transition (matches `html.theme-transition`)
- [ ] Reduced motion: all animations disabled, static visualizations
- [ ] Keyboard: full navigation, focus visible, Escape closes modals
- [ ] Screen reader: status announced, transcripts readable
- [ ] Mobile: 30fps+, touch interactions work, no layout shift
- [ ] Desktop: 60fps+, hover effects, responsive layout at all breakpoints
- [ ] Memory: no leaks after 10min continuous use
- [ ] Cleanup: unmount remount cycle leaves no Three.js objects

---

## 13. Approval

**Design Approved By**: [User]  
**Date**: 2026-07-26  
**Next Step**: Invoke `writing-plans` skill to create implementation plan

---

*This specification is the single source of truth for the VoiceBridge page redesign. All implementation decisions should reference this document.*
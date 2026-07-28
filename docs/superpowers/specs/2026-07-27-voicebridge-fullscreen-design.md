# VoiceBridge Full-Screen Toggle Design Spec

**Date:** 2026-07-27  
**Status:** Draft — awaiting implementation plan approval

---

## 1. Problem Statement

The VoiceBridge page (`/voice-bridge`) currently runs inside `MainLayout` with persistent sidebar, top bar, and chrome. Users want a **full-screen immersive mode** that hides all chrome (sidebar, top bar, floating chat widget) to focus purely on the voice experience — similar to a "kiosk" or "presentation" mode. A toggle button in the **StatusBadge (top-right)** should switch between normal and immersive modes, with state persisted across sessions.

---

## 2. Goals & Non-Goals

### Goals
- Add immersive/full-screen toggle in StatusBadge (top-right, next to connection status)
- Hide Sidebar, TopBar, and FloatingChatWidget when immersive mode is active on `/voice-bridge`
- Persist preference to `localStorage` (`voiceBridge:immersive`)
- Smooth transitions (fade + slide) when toggling
- Respect `prefers-reduced-motion`
- Keyboard accessible (Enter/Space on button, Escape to exit immersive)
- Zero breaking changes to other pages

### Non-Goals
- True browser Fullscreen API (`requestFullscreen()`) — this is **layout immersive**, not OS fullscreen
- Changes to other pages (Dashboard, Chat, etc.)
- VoiceBridgeContainer internal logic changes (it already renders full-viewport canvas)

---

## 3. Architecture

### 3.1 New Context: `VoiceBridgeImmersiveContext`

**Location:** `frontend/src/components/voice-bridge/ImmersiveContext.tsx`

```tsx
interface ImmersiveContextValue {
  isImmersive: boolean;
  toggleImmersive: () => void;
  setImmersive: (value: boolean) => void;
}
```

- Created in `VoiceBridgeContainer` (provider)
- Consumed by `StatusBadge` (toggle button) and `MainLayout` (hide chrome)
- Initial value from `localStorage.getItem('voiceBridge:immersive') === 'true'`
- Persists on every change

### 3.2 Integration Points

| Component | Role |
|-----------|------|
| `VoiceBridgeContainer` | Provides `VoiceBridgeImmersiveContext` |
| `StatusBadge` | Consumes context → renders toggle button |
| `MainLayout` | Consumes context (via portal or global store) → conditionally hides chrome when `location.pathname === '/voice-bridge' && isImmersive` |

**Note:** Since `MainLayout` is outside `VoiceBridgeContainer` in the React tree, we have two options:

| Option | Approach | Trade-off |
|--------|----------|-----------|
| **A. Global Zustand store** (recommended) | `useImmersiveStore` in `voice-bridge/store.ts`; `MainLayout` subscribes | Simple, no context bridging, works across routes |
| **B. Portal + Context** | Render provider at app root; `MainLayout` consumes via context | More React-idiomatically pure, but requires refactor of provider location |

**Recommendation: Option A (Zustand store)** — minimal, performant, aligns with existing `useAuthStore`/`useBackendStore` patterns in the codebase.

---

## 4. Component Design

### 4.1 New Store: `voice-bridge/store.ts`

```ts
import { create } from 'zustand';
import { persist } from 'zustand/middleware';

interface ImmersiveState {
  isImmersive: boolean;
  toggleImmersive: () => void;
  setImmersive: (value: boolean) => void;
}

export const useVoiceBridgeImmersiveStore = create<ImmersiveState>()(
  persist(
    (set) => ({
      isImmersive: false,
      toggleImmersive: () => set((s) => ({ isImmersive: !s.isImmersive })),
      setImmersive: (value) => set({ isImmersive: value }),
    }),
    { name: 'voiceBridge:immersive' }
  )
);
```

### 4.2 VoiceBridgeContainer Changes

```tsx
// In VoiceBridgeContainer (root of voice-bridge subtree)
import { useVoiceBridgeImmersiveStore } from './store';

export function VoiceBridgeContainer() {
  const { isImmersive, setImmersive } = useVoiceBridgeImmersiveStore();
  
  // Sync with MainLayout via store subscription (no prop drilling needed)
  // VoiceBridgeContainer just needs to initialize the store on mount
  useEffect(() => {
    // Store self-initializes from localStorage via persist middleware
  }, []);
  
  return (
    <VoiceBridgeImmersiveContext.Provider value={{ isImmersive, toggleImmersive, setImmersive }}>
      {/* existing JSX */}
    </VoiceBridgeImmersiveContext.Provider>
  );
}
```

### 4.3 StatusBadge — Toggle Button

**Location:** `frontend/src/components/voice-bridge/StatusBadge.tsx`

```tsx
import { Maximize, Minimize } from 'lucide-react';
import { useVoiceBridgeImmersiveStore } from './store';

export function StatusBadge({ status, voiceState }: StatusBadgeProps) {
  const { isImmersive, toggleImmersive } = useVoiceBridgeImmersiveStore();
  const { prefersReduced } = useReducedMotion();

  return (
    <motion.div
      className="fixed top-4 right-4 z-20 flex items-center gap-2"
      initial={{ opacity: 0, y: -20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: prefersReduced ? 0 : 0.3 }}
    >
      {/* Existing status badge content */}
      
      {/* NEW: Immersive toggle */}
      <button
        onClick={toggleImmersive}
        aria-label={isImmersive ? 'Exit immersive mode' : 'Enter immersive mode'}
        aria-pressed={isImmersive}
        className={cn(
          'p-2 rounded-xl transition-all duration-200',
          'bg-white/10 dark:bg-[#161b27]/80',
          'border border-white/10 dark:border-[#1e2535]',
          'hover:bg-white/20 dark:hover:bg-[#1e2535]',
          'focus:outline-none focus:ring-2 focus:ring-blue-500/50',
          isImmersive && 'bg-blue-500/20 text-blue-400'
        )}
      >
        {isImmersive ? <Minimize className="w-5 h-5" /> : <Maximize className="w-5 h-5" />}
      </button>
    </motion.div>
  );
}
```

### 4.4 MainLayout — Conditional Chrome Hiding

```tsx
// In MainLayout.tsx
import { useVoiceBridgeImmersiveStore } from '@/components/voice-bridge/store';
import { useLocation } from 'react-router-dom';

export function MainLayout() {
  const location = useLocation();
  const isVoiceBridge = location.pathname === '/voice-bridge';
  const isImmersive = useVoiceBridgeImmersiveStore((s) => s.isImmersive);
  
  const hideChrome = isVoiceBridge && isImmersive;

  return (
    <div className="flex h-screen bg-gray-50 dark:bg-[#0f1117]">
      {!hideChrome && (
        <>
          <Sidebar ... />
          {mobileOpen && <div className="fixed inset-0 z-30 bg-black/50 lg:hidden" ... />}
        </>
      )}

      <div className="flex min-w-0 flex-1 flex-col">
        {!hideChrome && (
          <TopBar ... />
        )}
        <main
          id="main-content"
          tabIndex={-1}
          className={cn(
            'relative min-h-0 flex-1 overflow-hidden outline-none',
            hideChrome && 'max-w-full' // remove sidebar width constraint
          )}
        >
          <KeepAliveOutlet />
        </main>
      </div>

      {/* FloatingChatWidget already hides on /voice-bridge via `hidden` prop */}
      <FloatingChatWidget hidden={location.pathname === '/chat' || location.pathname === '/voice-bridge'} />
    </div>
  );
}
```

---

## 5. Transitions & Animations

| Transition | Normal → Immersive | Immersive → Normal |
|------------|-------------------|-------------------|
| Sidebar | Slide left (`x: -100%`) + fade | Slide right (`x: 0`) + fade |
| TopBar | Slide up (`y: -100%`) + fade | Slide down (`y: 0`) + fade |
| Main content | Expand to full width (`max-w-full`) | Contract to `flex-1` with sidebar gap |
| Duration | 300ms spring (stiffness: 300, damping: 30) | Same |
| Reduced motion | Instant (opacity only) | Instant |

**Implementation:** Use `AnimatePresence` in `MainLayout` for exit animations, or CSS transitions on the container classes.

---

## 6. Keyboard Accessibility

| Key | Action |
|-----|--------|
| `Tab` / `Shift+Tab` | Focus toggle button (in StatusBadge) |
| `Enter` / `Space` | Toggle immersive mode |
| `Escape` | Exit immersive mode (if active) |

```tsx
// In StatusBadge toggle button
onKeyDown={(e) => {
  if (e.key === 'Escape' && isImmersive) toggleImmersive();
}}
```

---

## 7. Persistence

- **Key:** `voiceBridge:immersive` (via Zustand persist middleware)
- **Type:** `boolean`
- **Default:** `false`
- **Scope:** Per-browser, per-user (localStorage)
- **Sync:** Automatic on store hydration

---

## 8. Edge Cases

| Scenario | Behavior |
|----------|----------|
| User navigates away from `/voice-bridge` | Immersive mode auto-exits (MainLayout shows chrome again); store persists `true` so returning re-enters immersive |
| User refreshes in immersive mode | Store hydrates from localStorage → `isImmersive=true` → MainLayout hides chrome on mount |
| `prefers-reduced-motion` | All transitions disabled; instant toggle |
| Multiple tabs | Each tab independent (localStorage not synced cross-tab by default); could add `storage` event listener if needed |
| VoiceBridgeContainer unmounts | Store persists; no cleanup needed |

---

## 9. Testing Strategy

### Unit Tests
- `useVoiceBridgeImmersiveStore` — persist/rehydrate, toggle, setImmersive
- `StatusBadge` — renders correct icon, calls toggle, aria attributes

### Integration Tests
- `MainLayout` — hides Sidebar/TopBar when `isVoiceBridge && isImmersive`
- Full flow: mount VoiceBridgePage → click toggle → chrome hides → click toggle → chrome shows

### E2E (Playwright)
- Navigate to `/voice-bridge` → click maximize icon → verify Sidebar/TopBar hidden → refresh → verify immersive persists → click minimize → verify chrome restored

---

## 10. File Changes Summary

| File | Change Type |
|------|-------------|
| `frontend/src/components/voice-bridge/store.ts` | **New** — Zustand store with persist |
| `frontend/src/components/voice-bridge/ImmersiveContext.tsx` | **New** — React context (optional, for VoiceControls if needed) |
| `frontend/src/components/voice-bridge/StatusBadge.tsx` | **Modify** — add toggle button |
| `frontend/src/components/voice-bridge/VoiceBridgeContainer.tsx` | **Modify** — import store (ensure hydration) |
| `frontend/src/components/layout/MainLayout.tsx` | **Modify** — consume store, conditionally render chrome |
| `frontend/src/pages/VoiceBridgePage.tsx` | No change (just exports Container) |

---

## 11. Rollout Plan

1. Create store + context files
2. Update StatusBadge with toggle button
3. Update MainLayout to consume store
4. Add transitions (framer-motion AnimatePresence or CSS)
5. Test keyboard accessibility
6. Verify persistence across refresh/navigation

---

## Appendix: Visual Mockup (Text)

```
NORMAL MODE                          IMMERSIVE MODE
┌─────────────────────────────────┐  ┌─────────────────────────────────┐
│ ☰  Dashboard  Agents  ...   ≡  │  │  (no sidebar)                    │
├─────────────────────────────────┤  ├─────────────────────────────────┤
│ Agentium          Voice Bridge  │  │  (no top bar)                    │
├─────────────────────────────────┤  ├─────────────────────────────────┤
│                                 │  │                                  │
│    [3D Orb Canvas]              │  │    [3D Orb Canvas]              │
│                                 │  │                                  │
│              🎙  ⏸  ⚙  ◻    ◻  │  │              🎙  ⏸  ⚙  ◻  ◻  ◻│
│              Status  ☐ MAXIMIZE │  │              Status  ☐ MINIMIZE │
└─────────────────────────────────┘  └─────────────────────────────────┘
```

---

*End of Design Spec*
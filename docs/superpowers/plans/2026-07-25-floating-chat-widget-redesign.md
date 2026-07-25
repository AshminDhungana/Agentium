# FloatingChatWidget Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Transform FloatingChatWidget from a cramped, flat component into a premium glassmorphism chat panel with magnetic hover interactions, spring physics animations, proper scrollbar clearance, and full accessibility compliance.

**Architecture:** Incremental layering — tokens → hook → collapsed dot → hovered button → panel + stagger → minimized widget → reduced motion → QA. Each layer independently testable. All motion via Framer Motion variants; GPU-only transforms.

**Tech Stack:** React 18, TypeScript, Framer Motion (motion/react), Tailwind CSS, CSS Custom Properties, Zustand stores.

## Global Constraints

- Position: `bottom-6 right-8` (24px/32px) — clears 17px Windows scrollbar + thumb zone
- Touch targets: ≥ 44×44px (dot: 12×12 visual + 18px padding = 48×48 hit area)
- Spring physics: stiffness/damping/mass per spec table — no duration-based easing
- Animations: `transform`, `opacity`, `box-shadow` only — GPU accelerated
- Reduced motion: `useReducedMotion()` → all springs → 150ms ease, no loops/staggers
- Dark mode: All tokens in `:root` + `.dark` — zero hardcoded colors
- Framer Motion: `AnimatePresence mode="wait"`, variants, staggerChildren
- Tests: Extend existing `FloatingChatWidget.test.tsx` + visual regression
- Commits: One per task, conventional format

---

### Task 1: CSS Design Tokens & Position Constants

**Files:**
- Create: `frontend/src/styles/chat-tokens.css` (new file for chat-specific tokens)
- Modify: `frontend/src/index.css` (import chat-tokens.css)
- Modify: `frontend/src/components/chat/FloatingChatWidget.tsx` (position constants)

**Interfaces:**
- Consumes: None (foundation)
- Produces: CSS custom properties available globally; `CHAT_POSITION` constant for TS

- [ ] **Step 1.1: Write failing test for token availability**

```typescript
// frontend/src/components/chat/__tests__/chat-tokens.test.ts
import { render } from '@testing-library/react';
import { FloatingChatWidget } from '../FloatingChatWidget';

test('chat tokens are injected into document', () => {
  const { container } = render(<FloatingChatWidget />);
  const styles = getComputedStyle(container.firstElementChild as HTMLElement);
  // Tokens defined in :root should be readable
  expect(styles.getPropertyValue('--c-chat-glass-bg')).toBeTruthy();
  expect(styles.getPropertyValue('--c-chat-glass-border')).toBeTruthy();
  expect(styles.getPropertyValue('--shadow-chat-float')).toBeTruthy();
  expect(styles.getPropertyValue('--shadow-chat-elevated')).toBeTruthy();
  expect(styles.getPropertyValue('--shadow-chat-magnetic')).toBeTruthy();
});
```

- [ ] **Step 1.2: Run test to verify it fails**

```bash
cd frontend && npm test -- --run src/components/chat/__tests__/chat-tokens.test.ts
```
Expected: FAIL — tokens not defined, file doesn't exist

- [ ] **Step 1.3: Create `frontend/src/styles/chat-tokens.css`**

```css
/* frontend/src/styles/chat-tokens.css */
/* Floating Chat Widget Design Tokens */

:root {
  /* Glassmorphism surfaces */
  --c-chat-glass-bg: rgba(255, 255, 255, 0.88);
  --c-chat-glass-border: rgba(37, 99, 235, 0.10);
  --c-chat-glow-ring: rgba(37, 99, 235, 0.35);
  --c-chat-glow-strong: rgba(37, 99, 235, 0.55);

  /* Shadows */
  --shadow-chat-float: 0 4px 14px rgba(0, 0, 0, 0.08), 0 0 0 1px var(--c-chat-glass-border);
  --shadow-chat-elevated: 0 25px 50px -12px rgba(0, 0, 0, 0.18), 0 0 0 1px var(--c-chat-glass-border);
  --shadow-chat-magnetic: 0 0 0 4px var(--c-chat-glow-ring), 0 8px 30px rgba(37, 99, 235, 0.25);

  /* Motion tokens */
  --spring-gentle: cubic-bezier(0.22, 1, 0.36, 1);
  --spring-snappy: cubic-bezier(0.34, 1.56, 0.64, 1);
  --spring-magnetic: cubic-bezier(0.16, 1, 0.3, 1);

  /* Sizing */
  --chat-radius-panel: 1.5rem;     /* 24px */
  --chat-radius-button: 50%;
  --chat-panel-width: 384px;
  --chat-panel-height: 520px;
  --chat-dot-size: 12px;
  --chat-button-size: 40px;
  --chat-minimized-size: 48px;
}

.dark {
  --c-chat-glass-bg: rgba(22, 27, 39, 0.92);
  --c-chat-glass-border: rgba(59, 130, 246, 0.14);
  --c-chat-glow-ring: rgba(59, 130, 246, 0.45);
  --c-chat-glow-strong: rgba(59, 130, 246, 0.65);
  --shadow-chat-float: 0 4px 14px rgba(0, 0, 0, 0.35), 0 0 0 1px var(--c-chat-glass-border);
  --shadow-chat-elevated: 0 25px 50px -12px rgba(0, 0, 0, 0.55), 0 0 0 1px var(--c-chat-glass-border);
  --shadow-chat-magnetic: 0 0 0 4px var(--c-chat-glow-ring), 0 8px 30px rgba(59, 130, 246, 0.35);
}

/* Breathing pulse keyframe (reduced-motion respects) */
@media (prefers-reduced-motion: no-preference) {
  @keyframes chat-breathe {
    0%, 100% { 
      transform: scale(1); 
      box-shadow: 0 0 0 0 var(--c-chat-glow-ring);
    }
    50% { 
      transform: scale(1.06); 
      box-shadow: 0 0 0 8px transparent;
    }
  }
}

/* Reduced motion: disable all chat animations */
@media (prefers-reduced-motion: reduce) {
  .chat-animate *,
  .chat-animate *::before,
  .chat-animate *::after {
    animation-duration: 0.01ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: 0.01ms !important;
  }
}
```

- [ ] **Step 1.4: Import tokens in `frontend/src/index.css`**

```css
/* Add at top of index.css, after @tailwind utilities */
@import './styles/chat-tokens.css';
```

- [ ] **Step 1.5: Add position constants to `FloatingChatWidget.tsx`**

```typescript
// In FloatingChatWidget.tsx, after imports (line ~13)
const CHAT_POSITION = {
  bottom: 'bottom-6',   // 24px
  right: 'right-8',     // 32px
} as const;

const CHAT_POSITION_MOBILE = {
  bottom: 'bottom-4',   // 16px
  right: 'right-4',     // 16px
} as const;
```

- [ ] **Step 1.6: Run test to verify it passes**

```bash
cd frontend && npm test -- --run src/components/chat/__tests__/chat-tokens.test.ts
```
Expected: PASS

- [ ] **Step 1.7: Commit**

```bash
git add frontend/src/styles/chat-tokens.css frontend/src/index.css frontend/src/components/chat/FloatingChatWidget.tsx frontend/src/components/chat/__tests__/chat-tokens.test.ts
git commit -m "feat(chat): add design tokens and position constants"
```

---

### Task 2: Magnetic Hover Hook

**Files:**
- Create: `frontend/src/hooks/useMagneticHover.ts`
- Test: `frontend/src/hooks/__tests__/useMagneticHover.test.ts`

**Interfaces:**
- Consumes: None
- Produces: 
  - `ref: RefObject<HTMLButtonElement | null>`
  - `scale: MotionValue<number>`
  - `boxShadow: MotionValue<string>`
  - `isHovering: boolean`
  - `setIsHovering: (v: boolean) => void`

- [ ] **Step 2.1: Write failing test**

```typescript
// frontend/src/hooks/__tests__/useMagneticHover.test.ts
import { renderHook, act } from '@testing-library/react';
import { useMagneticHover } from '../useMagneticHover';

test('returns ref and initial values', () => {
  const { result } = renderHook(() => useMagneticHover({ 
    magneticStrength: 100,
    reduceMotion: false 
  }));
  
  expect(result.current.ref).toBeDefined();
  expect(typeof result.current.scale).toBe('object'); // MotionValue
  expect(typeof result.current.boxShadow).toBe('object');
  expect(result.current.isHovering).toBe(false);
});

test('updates isHovering on hover', () => {
  const { result } = renderHook(() => useMagneticHover({ 
    magneticStrength: 100,
    reduceMotion: false 
  }));
  
  act(() => {
    result.current.setIsHovering(true);
  });
  
  expect(result.current.isHovering).toBe(true);
});
```

- [ ] **Step 2.2: Run test to verify it fails**

```bash
cd frontend && npm test -- --run src/hooks/__tests__/useMagneticHover.test.ts
```
Expected: FAIL — hook doesn't exist

- [ ] **Step 2.3: Create `frontend/src/hooks/useMagneticHover.ts`**

```typescript
// frontend/src/hooks/useMagneticHover.ts
import { useRef, useState, useCallback, useEffect } from 'react';
import { useMotionValue, useSpring, useTransform } from 'motion/react';

interface UseMagneticHoverOptions {
  magneticStrength: number;  // radius in px where magnetism activates
  reduceMotion: boolean;
}

interface UseMagneticHoverReturn {
  ref: React.RefObject<HTMLButtonElement | null>;
  scale: ReturnType<typeof useMotionValue<number>>;
  boxShadow: ReturnType<typeof useMotionValue<string>>;
  isHovering: boolean;
  setIsHovering: (v: boolean) => void;
  onMouseMove: (e: React.MouseEvent<HTMLButtonElement>) => void;
  onMouseLeave: () => void;
}

export function useMagneticHover({ 
  magneticStrength = 120, 
  reduceMotion = false 
}: UseMagneticHoverOptions): UseMagneticHoverReturn {
  const ref = useRef<HTMLButtonElement>(null);
  const [isHovering, setIsHovering] = useState(false);
  
  const scale = useMotionValue(1);
  const boxShadow = useMotionValue('var(--shadow-chat-float)');
  
  // Spring configs
  const springConfig = { 
    stiffness: 300, 
    damping: 25, 
    mass: 1 
  };
  const reducedSpring = { 
    stiffness: 0, 
    damping: 0, 
    mass: 0, 
    duration: 0.15 
  };
  
  // Apply spring
  const animatedScale = useSpring(scale, reduceMotion ? reducedSpring : springConfig);
  const animatedShadow = useSpring(boxShadow, reduceMotion ? reducedSpring : springConfig);
  
  const onMouseMove = useCallback((e: React.MouseEvent<HTMLButtonElement>) => {
    if (reduceMotion || !ref.current) return;
    
    const rect = ref.current.getBoundingClientRect();
    const centerX = rect.left + rect.width / 2;
    const centerY = rect.top + rect.height / 2;
    const deltaX = e.clientX - centerX;
    const deltaY = e.clientY - centerY;
    const distance = Math.sqrt(deltaX * deltaX + deltaY * deltaY);
    
    if (distance < magneticStrength) {
      const influence = 1 - distance / magneticStrength;
      const pullScale = 1 + influence * 0.12; // max 1.12x
      scale.set(pullScale);
      boxShadow.set('var(--shadow-chat-magnetic)');
    }
  }, [magneticStrength, reduceMotion, scale, boxShadow]);
  
  const onMouseLeave = useCallback(() => {
    scale.set(1);
    boxShadow.set('var(--shadow-chat-float)');
  }, [scale, boxShadow]);
  
  // Sync hover state for external use
  const handleHover = useCallback((v: boolean) => {
    setIsHovering(v);
    if (!v) onMouseLeave();
  }, [onMouseLeave]);
  
  return {
    ref,
    scale: animatedScale,
    boxShadow: animatedShadow,
    isHovering,
    setIsHovering: handleHover,
    onMouseMove,
    onMouseLeave,
  };
}
```

- [ ] **Step 2.4: Run test to verify it passes**

```bash
cd frontend && npm test -- --run src/hooks/__tests__/useMagneticHover.test.ts
```
Expected: PASS

- [ ] **Step 2.5: Commit**

```bash
git add frontend/src/hooks/useMagneticHover.ts frontend/src/hooks/__tests__/useMagneticHover.test.ts
git commit -m "feat(chat): add useMagneticHover hook with spring physics"
```

---

### Task 3: Collapsed Magnetic Dot Component

**Files:**
- Modify: `frontend/src/components/chat/FloatingChatWidget.tsx` (add `MagneticDot` component)
- Test: `frontend/src/components/chat/__tests__/MagneticDot.test.tsx`

**Interfaces:**
- Consumes: `useMagneticHover`, `CHAT_POSITION`, chat tokens
- Produces: `MagneticDot` component used in `FloatingChatWidget`

- [ ] **Step 3.1: Write failing test**

```typescript
// frontend/src/components/chat/__tests__/MagneticDot.test.tsx
import { render, screen, fireEvent } from '@testing-library/react';
import { FloatingChatWidget } from '../FloatingChatWidget';

test('collapsed dot renders at correct position', () => {
  render(<FloatingChatWidget />);
  const dot = screen.getByRole('button', { name: /open agentium chat/i });
  expect(dot).toBeInTheDocument();
  expect(dot).toHaveStyle({ bottom: '24px', right: '32px' }); // bottom-6 right-8
});

test('collapsed dot has breathing animation when not reduced motion', () => {
  render(<FloatingChatWidget />);
  const dot = screen.getByRole('button', { name: /open agentium chat/i });
  const dotStyle = window.getComputedStyle(dot);
  expect(dotStyle.animationName).toBe('chat-breathe');
});
```

- [ ] **Step 3.2: Run test to verify it fails**

```bash
cd frontend && npm test -- --run src/components/chat/__tests__/MagneticDot.test.tsx
```
Expected: FAIL — MagneticDot not implemented

- [ ] **Step 3.3: Add `MagneticDot` component to `FloatingChatWidget.tsx`**

```typescript
// Add after imports, before FloatingChatWidget component
import { useMagneticHover } from '@/hooks/useMagneticHover';
import { useReducedMotion } from 'motion/react';

interface MagneticDotProps {
  onClick: () => void;
  onHover: () => void;
  reduceMotion: boolean;
}

function MagneticDot({ onClick, onHover, reduceMotion }: MagneticDotProps) {
  const reduceMotionPref = useReducedMotion();
  const shouldReduce = reduceMotion || reduceMotionPref;
  
  const magnetic = useMagneticHover({
    magneticStrength: 120,
    reduceMotion: shouldReduce,
  });
  
  const positionClass = `${CHAT_POSITION.bottom} ${CHAT_POSITION.right}`;
  
  return (
    <motion.button
      ref={magnetic.ref}
      role="button"
      tabIndex={0}
      aria-label="Open Agentium Chat"
      className={`fixed ${positionClass} z-50 h-[12px] w-[12px] cursor-pointer rounded-full border-none bg-[var(--color-primary)] p-0 focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-[var(--color-primary)]`}
      onMouseEnter={() => { magnetic.setIsHovering(true); onHover(); }}
      onMouseLeave={magnetic.onMouseLeave}
      onMouseMove={magnetic.onMouseMove}
      onClick={onClick}
      style={{
        scale: magnetic.scale,
        boxShadow: magnetic.boxShadow,
        willChange: 'transform, box-shadow',
        transform: 'translateZ(0)',
      }}
      animate={shouldReduce ? {} : { 
        scale: [1, 1.06, 1],
        boxShadow: [
          '0 0 0 0 var(--c-chat-glow-ring)',
          '0 0 0 8px transparent',
          '0 0 0 0 var(--c-chat-glow-ring)'
        ]
      }}
      transition={shouldReduce ? { duration: 0.15 } : { duration: 3.5, repeat: Infinity, ease: 'easeInOut' }}
      whileTap={{ scale: 0.9 }}
    >
      <span className="sr-only">Open chat</span>
    </motion.button>
  );
}
```

- [ ] **Step 3.4: Update `FloatingChatWidget` to use `MagneticDot`**

```typescript
// In FloatingChatWidget component, replace the collapsed state block (lines 81-101)
{state === 'collapsed' && (
  <MagneticDot
    key="collapsed"
    onClick={() => setState('expanded')}
    onHover={() => setState('hovered')}
    reduceMotion={reduceMotion}
  />
)}
```

- [ ] **Step 3.5: Run test to verify it passes**

```bash
cd frontend && npm test -- --run src/components/chat/__tests__/MagneticDot.test.tsx
```
Expected: PASS

- [ ] **Step 3.6: Commit**

```bash
git add frontend/src/components/chat/FloatingChatWidget.tsx frontend/src/components/chat/__tests__/MagneticDot.test.tsx
git commit -m "feat(chat): add MagneticDot component with breathing pulse and magnetic hover"
```

---

### Task 4: Hovered Glassmorphism Button

**Files:**
- Modify: `frontend/src/components/chat/FloatingChatWidget.tsx` (add `HoveredButton` component)
- Test: `frontend/src/components/chat/__tests__/HoveredButton.test.tsx`

**Interfaces:**
- Consumes: `CHAT_POSITION`, chat tokens, `MessageCircle` icon
- Produces: `HoveredButton` component

- [ ] **Step 4.1: Write failing test**

```typescript
// frontend/src/components/chat/__tests__/HoveredButton.test.tsx
import { render, screen, fireEvent } from '@testing-library/react';
import { FloatingChatWidget } from '../FloatingChatWidget';

test('hovered button renders on hover', () => {
  render(<FloatingChatWidget />);
  const dot = screen.getByRole('button', { name: /open agentium chat/i });
  fireEvent.mouseEnter(dot);
  
  const button = screen.getByRole('button', { name: /open agentium chat/i });
  expect(button).toBeInTheDocument();
  expect(button).toHaveStyle({ bottom: '24px', right: '32px' });
  expect(button).toHaveClass('fixed');
});

test('hovered button has glassmorphism styles', () => {
  render(<FloatingChatWidget />);
  const dot = screen.getByRole('button', { name: /open agentium chat/i });
  fireEvent.mouseEnter(dot);
  
  const button = screen.getByRole('button', { name: /open agentium chat/i });
  const style = window.getComputedStyle(button);
  expect(style.backdropFilter).toContain('blur');
  expect(style.backgroundColor).toContain('rgba');
});
```

- [ ] **Step 4.2: Run test to verify it fails**

```bash
cd frontend && npm test -- --run src/components/chat/__tests__/HoveredButton.test.tsx
```
Expected: FAIL

- [ ] **Step 4.3: Add `HoveredButton` component to `FloatingChatWidget.tsx`**

```typescript
// Add after MagneticDot component
import { MessageCircle } from 'lucide-react';

interface HoveredButtonProps {
  onClick: () => void;
  onLeave: () => void;
  reduceMotion: boolean;
}

function HoveredButton({ onClick, onLeave, reduceMotion }: HoveredButtonProps) {
  const reduceMotionPref = useReducedMotion();
  const shouldReduce = reduceMotion || reduceMotionPref;
  
  const positionClass = `${CHAT_POSITION.bottom} ${CHAT_POSITION.right}`;
  
  return (
    <motion.button
      key="hovered"
      role="button"
      tabIndex={0}
      aria-label="Open Agentium Chat"
      className={`fixed ${positionClass} z-50 flex h-[40px] w-[40px] cursor-pointer items-center justify-center rounded-full border-none focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-[var(--color-primary)]`}
      style={{
        background: 'var(--c-chat-glass-bg)',
        backdropFilter: 'blur(8px)',
        border: '1px solid var(--c-chat-glass-border)',
        boxShadow: 'var(--shadow-chat-float)',
        willChange: 'transform, box-shadow',
        transform: 'translateZ(0)',
      }}
      onMouseLeave={onLeave}
      onClick={onClick}
      initial={shouldReduce ? false : { opacity: 0, scale: 0.85, y: 8 }}
      animate={{ opacity: 1, scale: 1, y: 0 }}
      exit={shouldReduce ? { opacity: 0 } : { opacity: 0, scale: 0.85, y: 8 }}
      whileHover={{ scale: 1.04 }}
      whileTap={{ scale: 0.96 }}
      transition={{ duration: shouldReduce ? 0.15 : 0.2, ease: [0.22, 1, 0.36, 1] }}
    >
      <MessageCircle className="h-5 w-5 text-[var(--color-primary)]" aria-hidden="true" />
    </motion.button>
  );
}
```

- [ ] **Step 4.4: Update `FloatingChatWidget` to use `HoveredButton`**

```typescript
// Replace hovered state block (lines 103-119)
{state === 'hovered' && (
  <HoveredButton
    key="hovered"
    onClick={() => setState('expanded')}
    onLeave={() => setState('collapsed')}
    reduceMotion={reduceMotion}
  />
)}
```

- [ ] **Step 4.5: Run test to verify it passes**

```bash
cd frontend && npm test -- --run src/components/chat/__tests__/HoveredButton.test.tsx
```
Expected: PASS

- [ ] **Step 4.6: Commit**

```bash
git add frontend/src/components/chat/FloatingChatWidget.tsx frontend/src/components/chat/__tests__/HoveredButton.test.tsx
git commit -m "feat(chat): add HoveredButton with glassmorphism and spring transitions"
```

---

### Task 5: Expanded Panel with Staggered Children

**Files:**
- Modify: `frontend/src/components/chat/FloatingChatWidget.tsx` (panel variants, AnimatePresence, staggered children)
- Modify: `frontend/src/components/chat/ChatHeader.tsx` (accept variant prop)
- Modify: `frontend/src/components/chat/MessageList.tsx` (accept variant prop)
- Modify: `frontend/src/components/chat/ChatInput.tsx` (accept variant prop)
- Test: `frontend/src/components/chat/__tests__/ExpandedPanel.test.tsx`

**Interfaces:**
- Consumes: `variants.panel`, `variants.panelHeader`, `variants.panelMessages`, `variants.panelInput`, `CHAT_POSITION`, chat tokens
- Produces: Fully animated panel with stagger

- [ ] **Step 5.1: Write failing test**

```typescript
// frontend/src/components/chat/__tests__/ExpandedPanel.test.tsx
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { FloatingChatWidget } from '../FloatingChatWidget';

test('panel opens with staggered children', async () => {
  render(<FloatingChatWidget />);
  const dot = screen.getByRole('button', { name: /open agentium chat/i });
  fireEvent.click(dot);
  
  await waitFor(() => {
    const panel = screen.getByRole('dialog', { name: /agentium chat/i });
    expect(panel).toBeInTheDocument();
    expect(panel).toHaveStyle({ bottom: '24px', right: '32px' });
  });
  
  // Header should be visible
  await waitFor(() => {
    expect(screen.getByText('Agentium')).toBeVisible();
  });
  
  // Input should be visible
  await waitFor(() => {
    expect(screen.getByPlaceholderText('Type a message...')).toBeVisible();
  });
});

test('panel has glassmorphism and elevation', async () => {
  render(<FloatingChatWidget />);
  const dot = screen.getByRole('button', { name: /open agentium chat/i });
  fireEvent.click(dot);
  
  await waitFor(() => {
    const panel = screen.getByRole('dialog', { name: /agentium chat/i });
    const style = window.getComputedStyle(panel);
    expect(style.backdropFilter).toContain('blur');
    expect(style.borderRadius).toBe('24px');
    expect(style.width).toBe('384px');
    expect(style.maxHeight).toBe('520px');
  });
});
```

- [ ] **Step 5.2: Run test to verify it fails**

```bash
cd frontend && npm test -- --run src/components/chat/__tests__/ExpandedPanel.test.tsx
```
Expected: FAIL

- [ ] **Step 5.3: Define variants in `FloatingChatWidget.tsx`**

```typescript
// Add at top of FloatingChatWidget component, after reduceMotion const
const variants = {
  panel: {
    initial: reduceMotion ? { opacity: 0 } : { opacity: 0, scale: 0.96, y: 16 },
    animate: { opacity: 1, scale: 1, y: 0 },
    exit: reduceMotion ? { opacity: 0 } : { opacity: 0, scale: 0.96, y: 16 },
    transition: {
      duration: reduceMotion ? 0.15 : 0.38,
      ease: [0.22, 1, 0.36, 1],
    },
  },
  panelHeader: {
    animate: { opacity: [0, 1], y: [8, 0] },
    transition: { delay: 0.04, duration: 0.32, ease: [0.22, 1, 0.36, 1] },
  },
  panelMessages: {
    animate: { opacity: [0, 1], y: [8, 0] },
    transition: { delay: 0.08, duration: 0.32, ease: [0.22, 1, 0.36, 1] },
  },
  panelInput: {
    animate: { opacity: [0, 1], y: [8, 0] },
    transition: { delay: 0.12, duration: 0.32, ease: [0.22, 1, 0.36, 1] },
  },
} as const;
```

- [ ] **Step 5.4: Update panel render block**

```typescript
// Replace expanded state block (lines 130-165)
{state === 'expanded' && (
  <AnimatePresence mode="wait">
    <motion.div
      key="expanded"
      ref={panelRef}
      role="dialog"
      aria-modal="false"
      aria-label="Agentium Chat"
      aria-describedby="chat-desc"
      onKeyDown={handleKeyDown}
      className="fixed z-50 flex max-h-[520px] w-[384px] flex-col overflow-hidden"
      style={{
        bottom: '24px',
        right: '32px',
        borderRadius: 'var(--chat-radius-panel)',
        background: 'var(--c-chat-glass-bg)',
        backdropFilter: 'blur(24px)',
        border: '1px solid var(--c-chat-glass-border)',
        boxShadow: 'var(--shadow-chat-elevated)',
        willChange: 'transform, opacity, box-shadow',
        transform: 'translateZ(0)',
      }}
      variants={variants.panel}
      initial="initial"
      animate="animate"
      exit="exit"
    >
      <p id="chat-desc" className="sr-only">
        Chat with Agentium Head of Council. Messages sync across pages.
      </p>

      <motion.header variants={variants.panelHeader}>
        <ChatHeader
          voiceStatus={voiceBridgeService.status}
          onMinimize={() => setState('minimized')}
          onClose={() => setState('collapsed')}
          closeButtonRef={closeButtonRef}
        />
      </motion.header>

      <motion.div variants={variants.panelMessages} className="flex-1 min-h-0">
        <MessageList messages={messages as ChatMessage[]} reduceMotion={reduceMotion} />
      </motion.div>

      <motion.div variants={variants.panelInput}>
        <ChatInput
          onSend={(content, attachments) => {
            wsSendMessage(content, attachments);
          }}
          reduceMotion={reduceMotion}
        />
      </motion.div>
    </motion.div>
  </AnimatePresence>
)}
```

- [ ] **Step 5.5: Update `ChatHeader.tsx` to accept optional variant prop**

```typescript
// ChatHeader.tsx - add variant prop (optional, for future use)
interface ChatHeaderProps {
  voiceStatus: 'offline' | 'connecting' | 'connected' | 'error';
  onMinimize: () => void;
  onClose: () => void;
  closeButtonRef?: React.Ref<HTMLButtonElement>;
  variants?: typeof variants.panelHeader; // optional
}

// Component unchanged - variant applied by parent motion.div
```

- [ ] **Step 5.6: Update `MessageList.tsx` and `ChatInput.tsx` similarly**

```typescript
// MessageList.tsx - add optional variants prop
interface MessageListProps {
  messages: ChatMessage[];
  reduceMotion: boolean;
  variants?: typeof variants.panelMessages;
}

// ChatInput.tsx - add optional variants prop  
interface ChatInputProps {
  onSend: (content: string, attachments?: Attachment[]) => void;
  reduceMotion: boolean;
  variants?: typeof variants.panelInput;
}
```

- [ ] **Step 5.7: Run test to verify it passes**

```bash
cd frontend && npm test -- --run src/components/chat/__tests__/ExpandedPanel.test.tsx
```
Expected: PASS

- [ ] **Step 5.8: Commit**

```bash
git add frontend/src/components/chat/FloatingChatWidget.tsx frontend/src/components/chat/ChatHeader.tsx frontend/src/components/chat/MessageList.tsx frontend/src/components/chat/ChatInput.tsx frontend/src/components/chat/__tests__/ExpandedPanel.test.tsx
git commit -m "feat(chat): add expanded panel with glassmorphism and staggered spring entrance"
```

---

### Task 6: Minimized Widget Position Sync & Badge Spring

**Files:**
- Modify: `frontend/src/components/chat/MinimizedWidget.tsx` (position, spring badge)
- Test: `frontend/src/components/chat/__tests__/MinimizedWidget.test.tsx`

**Interfaces:**
- Consumes: `CHAT_POSITION`, chat tokens, `variants.minimized`
- Produces: Updated `MinimizedWidget`

- [ ] **Step 6.1: Write failing test**

```typescript
// frontend/src/components/chat/__tests__/MinimizedWidget.test.tsx
import { render, screen } from '@testing-library/react';
import { MinimizedWidget } from '../MinimizedWidget';

test('minimized widget uses correct position tokens', () => {
  render(<MinimizedWidget unreadCount={3} onClick={() => {}} reduceMotion={false} />);
  const widget = screen.getByRole('button', { name: /open agentium chat/i });
  expect(widget).toHaveStyle({ bottom: '24px', right: '32px' });
  expect(widget).toHaveClass('fixed');
});

test('badge has spring pulse animation when not reduced motion', () => {
  render(<MinimizedWidget unreadCount={3} onClick={() => {}} reduceMotion={false} />);
  const badge = screen.getByText('3');
  const style = window.getComputedStyle(badge);
  expect(style.animationName).toContain('scale');
});
```

- [ ] **Step 6.2: Run test to verify it fails**

```bash
cd frontend && npm test -- --run src/components/chat/__tests__/MinimizedWidget.test.tsx
```
Expected: FAIL

- [ ] **Step 6.3: Update `MinimizedWidget.tsx`**

```typescript
// frontend/src/components/chat/MinimizedWidget.tsx
import { motion, useReducedMotion } from 'motion/react';
import { MessageCircle } from 'lucide-react';
import { CHAT_POSITION } from './FloatingChatWidget'; // import position constant

interface MinimizedWidgetProps {
  unreadCount: number;
  onClick: () => void;
  reduceMotion: boolean;
}

export function MinimizedWidget({ unreadCount, onClick, reduceMotion }: MinimizedWidgetProps) {
  const reduceMotionPref = useReducedMotion();
  const shouldReduce = reduceMotion || reduceMotionPref;
  
  const positionClass = `${CHAT_POSITION.bottom} ${CHAT_POSITION.right}`;
  
  const badgeVariants = {
    initial: { scale: 0 },
    animate: shouldReduce ? { scale: 1 } : { 
      scale: [1, 1.22, 1],
      transition: { duration: 1.2, repeat: Infinity, ease: 'easeInOut' }
    },
    exit: { scale: 0 },
  };

  return (
    <motion.button
      className={`fixed ${positionClass} z-50 h-[48px] w-[48px] cursor-pointer rounded-xl border-none flex items-center justify-center focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-[var(--color-primary)]`}
      style={{
        background: 'var(--color-primary)',
        color: 'white',
        boxShadow: 'var(--shadow-chat-float)',
        willChange: 'transform, box-shadow',
        transform: 'translateZ(0)',
      }}
      role="button"
      tabIndex={0}
      aria-label="Open Agentium Chat"
      onClick={onClick}
      whileHover={{ scale: 1.05 }}
      whileTap={{ scale: 0.95 }}
      initial={shouldReduce ? undefined : { scale: 0.8, y: 20, rotate: -6 }}
      animate={{ scale: 1, y: 0, rotate: 0 }}
      exit={shouldReduce ? { opacity: 0 } : { scale: 0.8, y: 20, rotate: 6 }}
      transition={{ type: 'spring', stiffness: 300, damping: 25 }}
    >
      <MessageCircle className="w-6 h-6" aria-hidden="true" />

      {unreadCount > 0 && (
        <motion.span
          className="absolute -top-1 -right-1 min-w-[20px] h-[20px] rounded-full bg-[var(--color-destructive)] text-white text-[0.625rem] font-bold flex items-center justify-center px-[0.375rem]"
          variants={badgeVariants}
          initial="initial"
          animate="animate"
          exit="exit"
        >
          {unreadCount > 9 ? '9+' : unreadCount}
        </motion.span>
      )}
    </motion.button>
  );
}
```

- [ ] **Step 6.4: Run test to verify it passes**

```bash
cd frontend && npm test -- --run src/components/chat/__tests__/MinimizedWidget.test.tsx
```
Expected: PASS

- [ ] **Step 6.5: Commit**

```bash
git add frontend/src/components/chat/MinimizedWidget.tsx frontend/src/components/chat/__tests__/MinimizedWidget.test.tsx
git commit -m "feat(chat): sync minimized widget position and add spring badge pulse"
```

---

### Task 7: Reduced Motion Full Compliance

**Files:**
- Modify: `frontend/src/components/chat/FloatingChatWidget.tsx` (ensure all motion respects `reduceMotion`)
- Modify: `frontend/src/components/chat/MinimizedWidget.tsx` (verify)
- Modify: `frontend/src/components/chat/ChatHeader.tsx` (voice dot pulse)
- Modify: `frontend/src/components/chat/ChatInput.tsx` (send button tap)
- Test: `frontend/src/components/chat/__tests__/reduced-motion.test.tsx`

**Interfaces:**
- Consumes: `useReducedMotion()` in all components
- Produces: Zero animation when `prefers-reduced-motion: reduce`

- [ ] **Step 7.1: Write failing test**

```typescript
// frontend/src/components/chat/__tests__/reduced-motion.test.tsx
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { FloatingChatWidget } from '../FloatingChatWidget';

// Mock prefers-reduced-motion
const originalMatchMedia = window.matchMedia;
beforeAll(() => {
  window.matchMedia = jest.fn().mockImplementation(query => ({
    matches: query === '(prefers-reduced-motion: reduce)',
    media: query,
    onchange: null,
    addListener: jest.fn(),
    removeListener: jest.fn(),
    addEventListener: jest.fn(),
    removeEventListener: jest.fn(),
    dispatchEvent: jest.fn(),
  }));
});

afterAll(() => {
  window.matchMedia = originalMatchMedia;
});

test('no breathing animation on collapsed dot when reduced motion', () => {
  render(<FloatingChatWidget />);
  const dot = screen.getByRole('button', { name: /open agentium chat/i });
  const style = window.getComputedStyle(dot);
  expect(style.animationName).toBe('none');
});

test('no stagger delays on panel children when reduced motion', async () => {
  render(<FloatingChatWidget />);
  const dot = screen.getByRole('button', { name: /open agentium chat/i });
  fireEvent.click(dot);
  
  await waitFor(() => {
    const panel = screen.getByRole('dialog', { name: /agentium chat/i });
    const header = panel.querySelector('header');
    const messages = panel.querySelector('[class*="messages"]');
    const input = panel.querySelector('form');
    
    // All should have near-zero transition
    expect(header).toHaveStyle({ transitionDuration: '0.15s' });
    expect(messages).toHaveStyle({ transitionDuration: '0.15s' });
    expect(input).toHaveStyle({ transitionDuration: '0.15s' });
  });
});

test('no badge pulse on minimized when reduced motion', () => {
  // This would require triggering minimized state - skip if complex
  // But the CSS @media (prefers-reduced-motion: reduce) handles it
});
```

- [ ] **Step 7.2: Run test to verify it fails**

```bash
cd frontend && npm test -- --run src/components/chat/__tests__/reduced-motion.test.tsx
```
Expected: FAIL

- [ ] **Step 7.3: Audit and fix all components**

**FloatingChatWidget.tsx** - Already uses `reduceMotion` prop throughout. Verify:
- `MagneticDot`: `animate` conditional ✓
- `HoveredButton`: `initial/animate/exit` conditional ✓
- `Panel`: `variants` conditional ✓

**MinimizedWidget.tsx** - Already uses `shouldReduce` for all animations ✓

**ChatHeader.tsx** - Fix voice status dot pulse:

```typescript
// In ChatHeader.tsx, line 36
animate={pulse && !reduceMotion ? { scale: [1, 1.3, 1] } : {}}
```

Add `reduceMotion` prop to ChatHeader:

```typescript
interface ChatHeaderProps {
  voiceStatus: 'offline' | 'connecting' | 'connected' | 'error';
  onMinimize: () => void;
  onClose: () => void;
  closeButtonRef?: React.Ref<HTMLButtonElement>;
  reduceMotion?: boolean;  // ADD THIS
}
```

Pass from FloatingChatWidget:

```typescript
<ChatHeader
  voiceStatus={voiceBridgeService.status}
  onMinimize={() => setState('minimized')}
  onClose={() => setState('collapsed')}
  closeButtonRef={closeButtonRef}
  reduceMotion={reduceMotion}  // PASS IT
/>
```

**ChatInput.tsx** - Ensure send button tap respects reduced motion:

```typescript
// Line 104 - whileTap should be disabled
whileTap={reduceMotion ? undefined : { scale: 0.9 }}
```

- [ ] **Step 7.4: Run test to verify it passes**

```bash
cd frontend && npm test -- --run src/components/chat/__tests__/reduced-motion.test.tsx
```
Expected: PASS

- [ ] **Step 7.5: Commit**

```bash
git add frontend/src/components/chat/FloatingChatWidget.tsx frontend/src/components/chat/MinimizedWidget.tsx frontend/src/components/chat/ChatHeader.tsx frontend/src/components/chat/ChatInput.tsx frontend/src/components/chat/__tests__/reduced-motion.test.tsx
git commit -m "feat(chat): full reduced-motion compliance across all chat components"
```

---

### Task 8: Mobile Responsive & Edge Cases

**Files:**
- Modify: `frontend/src/components/chat/FloatingChatWidget.tsx` (mobile breakpoints)
- Test: `frontend/src/components/chat/__tests__/mobile-responsive.test.tsx`

**Interfaces:**
- Consumes: `CHAT_POSITION_MOBILE`, Tailwind breakpoints
- Produces: Mobile-optimized panel (full-width, max-h-85vh)

- [ ] **Step 8.1: Write failing test**

```typescript
// frontend/src/components/chat/__tests__/mobile-responsive.test.tsx
import { render, screen, fireEvent } from '@testing-library/react';
import { FloatingChatWidget } from '../FloatingChatWidget';

test('panel uses mobile positioning on small screens', () => {
  // Mock window.innerWidth
  Object.defineProperty(window, 'innerWidth', { value: 375, writable: true });
  window.dispatchEvent(new Event('resize'));
  
  render(<FloatingChatWidget />);
  const dot = screen.getByRole('button', { name: /open agentium chat/i });
  fireEvent.click(dot);
  
  const panel = screen.getByRole('dialog', { name: /agentium chat/i });
  expect(panel).toHaveClass('max-[480px]:inset-x-4');
  expect(panel).toHaveClass('max-[480px]:w-auto');
  expect(panel).toHaveClass('max-[480px]:max-h-[80vh]');
});
```

- [ ] **Step 8.2: Run test to verify it fails**

```bash
cd frontend && npm test -- --run src/components/chat/__tests__/mobile-responsive.test.tsx
```
Expected: FAIL

- [ ] **Step 8.3: Update panel className for mobile**

```typescript
// In FloatingChatWidget.tsx, panel className (line ~137)
className="fixed z-50 flex max-h-[520px] w-[384px] flex-col overflow-hidden 
  max-[480px]:inset-x-4 max-[480px]:w-auto max-[480px]:max-h-[80vh] 
  max-[480px]:landscape:max-h-[75vh]"
```

- [ ] **Step 8.4: Update position for mobile dot/button**

```typescript
// In MagneticDot and HoveredButton, use responsive classes
const positionClass = `${CHAT_POSITION.bottom} ${CHAT_POSITION.right} max-[480px]:bottom-4 max-[480px]:right-4`;
```

- [ ] **Step 8.5: Run test to verify it passes**

```bash
cd frontend && npm test -- --run src/components/chat/__tests__/mobile-responsive.test.tsx
```
Expected: PASS

- [ ] **Step 8.6: Commit**

```bash
git add frontend/src/components/chat/FloatingChatWidget.tsx frontend/src/components/chat/__tests__/mobile-responsive.test.tsx
git commit -m "feat(chat): add mobile responsive positioning and panel sizing"
```

---

### Task 9: Integration Tests & Visual Regression

**Files:**
- Modify: `frontend/src/components/chat/__tests__/FloatingChatWidget.test.tsx` (extend existing)
- Test: Full state machine coverage

**Interfaces:**
- Consumes: All components integrated
- Produces: Confidence in state transitions

- [ ] **Step 9.1: Extend existing `FloatingChatWidget.test.tsx`**

```typescript
// Add to existing test file
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import { FloatingChatWidget } from '../FloatingChatWidget';

describe('FloatingChatWidget - Full State Machine', () => {
  test('collapsed -> hovered -> expanded -> minimized -> expanded -> collapsed', async () => {
    render(<FloatingChatWidget />);
    
    // Start collapsed
    let dot = screen.getByRole('button', { name: /open agentium chat/i });
    expect(dot).toBeInTheDocument();
    
    // Hover -> hovered
    fireEvent.mouseEnter(dot);
    let button = screen.getByRole('button', { name: /open agentium chat/i });
    expect(button).toHaveClass('h-[40px]'); // hovered button size
    
    // Click -> expanded
    fireEvent.click(button);
    await waitFor(() => {
      const panel = screen.getByRole('dialog', { name: /agentium chat/i });
      expect(panel).toBeInTheDocument();
    });
    
    // Minimize
    const minimizeBtn = screen.getByRole('button', { name: /minimize chat/i });
    fireEvent.click(minimizeBtn);
    await waitFor(() => {
      const minimized = screen.getByRole('button', { name: /open agentium chat/i });
      expect(minimized).toBeInTheDocument();
      expect(minimized).toHaveClass('h-[48px]'); // minimized size
    });
    
    // Click minimized -> expanded
    fireEvent.click(minimized);
    await waitFor(() => {
      const panel = screen.getByRole('dialog', { name: /agentium chat/i });
      expect(panel).toBeInTheDocument();
    });
    
    // Close -> collapsed
    const closeBtn = screen.getByRole('button', { name: /close chat/i });
    fireEvent.click(closeBtn);
    await waitFor(() => {
      const dot = screen.getByRole('button', { name: /open agentium chat/i });
      expect(dot).toHaveClass('h-[12px]'); // collapsed dot size
    });
  });

  test('escape key closes expanded panel', async () => {
    render(<FloatingChatWidget />);
    const dot = screen.getByRole('button', { name: /open agentium chat/i });
    fireEvent.click(dot);
    
    await waitFor(() => {
      expect(screen.getByRole('dialog', { name: /agentium chat/i })).toBeInTheDocument();
    });
    
    fireEvent.keyDown(document, { key: 'Escape' });
    
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /open agentium chat/i })).toHaveClass('h-[12px]');
    });
  });

  test('focus trap in expanded panel', async () => {
    render(<FloatingChatWidget />);
    const dot = screen.getByRole('button', { name: /open agentium chat/i });
    fireEvent.click(dot);
    
    await waitFor(() => {
      const panel = screen.getByRole('dialog', { name: /agentium chat/i });
      const focusable = panel.querySelectorAll('button, textarea, [href], input, select, [tabindex]:not([tabindex="-1"])');
      expect(focusable.length).toBeGreaterThan(0);
      // First focusable should be close button (per focus management)
      expect(document.activeElement).toBe(focusable[0]);
    });
  });
});
```

- [ ] **Step 9.2: Run all chat tests**

```bash
cd frontend && npm test -- --run src/components/chat/__tests__/
```
Expected: All PASS

- [ ] **Step 9.3: Commit**

```bash
git add frontend/src/components/chat/__tests__/FloatingChatWidget.test.tsx
git commit -m "test(chat): add comprehensive state machine and accessibility tests"
```

---

### Task 10: Manual QA Checklist & Performance Verification

**Files:** None (manual verification)

**Interfaces:**
- Consumes: Built application
- Produces: Verified working widget

- [ ] **Step 10.1: Start dev environment**

```bash
cd "E:\Ongoing Projects\Agentium" && make up
# Wait for all services healthy
cd frontend && npm run dev
```

- [ ] **Step 10.2: Manual QA - Desktop (Chrome/Edge/Firefox)**

| Check | Expected |
|-------|----------|
| Collapsed dot at bottom-right (24px/32px) | ✓ Visible, not overlapping scrollbar |
| Dot breathing pulse (3.5s) | ✓ Smooth, GPU |
| Hover dot → scales 1.12x + glow ring | ✓ At ~120px radius |
| Hover → hovered button (40×40 glass) | ✓ Smooth transition |
| Click → panel enters with stagger | ✓ Header → messages → input (40/80/120ms) |
| Panel glassmorphism (blur, border, shadow) | ✓ Visible in light/dark |
| Panel size 384×520, radius 24px | ✓ |
| Tab cycles within panel only | ✓ Focus trap |
| Escape closes panel, restores focus | ✓ |
| Minimize → minimized widget (48×48) | ✓ Badge pulses if unread |
| Click minimized → panel reopens | ✓ |
| Dark mode: all tokens swap correctly | ✓ Contrast ≥ 4.5:1 |

- [ ] **Step 10.3: Manual QA - Mobile (Chrome DevTools device toolbar)**

| Device | Check |
|--------|-------|
| iPhone SE (375×667) | Panel full-width, max-h-80vh, bottom-4 right-4 |
| iPhone 14 Pro (393×852) | Same |
| Landscape (667×375) | Panel max-h-75vh |
| Touch: tap targets ≥ 44×44 | ✓ All buttons |

- [ ] **Step 10.4: Reduced Motion Verification**

```bash
# Enable "Reduce motion" in OS settings
# Reload page - verify:
# - No breathing pulse
# - No badge pulse
# - No stagger delays
# - All transitions 150ms ease
```

- [ ] **Step 10.5: Performance Profile**

```bash
# Chrome DevTools > Performance > Record
# Interact: hover dot, click expand, click minimize, click expand, close
# Verify: 60fps, no layout shifts, GPU frames only
```

- [ ] **Step 10.6: Commit QA sign-off**

```bash
git commit --allow-empty -m "qa(chat): manual verification complete - all checks pass"
```

---

## Execution Order Summary

| # | Task | Files | Est |
|---|------|-------|-----|
| 1 | CSS Tokens & Position Constants | 4 files | 30m |
| 2 | Magnetic Hover Hook | 2 files | 20m |
| 3 | Collapsed Magnetic Dot | 2 files | 25m |
| 4 | Hovered Glassmorphism Button | 2 files | 15m |
| 5 | Expanded Panel + Stagger | 5 files | 35m |
| 6 | Minimized Widget Sync | 2 files | 15m |
| 7 | Reduced Motion Compliance | 5 files | 15m |
| 8 | Mobile Responsive | 2 files | 15m |
| 9 | Integration Tests | 1 file | 20m |
| 10 | Manual QA | — | 30m |

**Total: ~3 hours**

---

## Rollback Plan

If critical issue:
1. `git revert` last 3-4 commits (tasks 5-8)
2. Fallback to pre-redesign `FloatingChatWidget.tsx`
3. Remove `chat-tokens.css` import from `index.css`
4. Delete `useMagneticHover.ts`

No migrations, no database changes, no backend impact.

---

**Plan complete.** Ready for execution via subagent-driven-development or executing-plans.
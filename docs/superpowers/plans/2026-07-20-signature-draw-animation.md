# Signature Draw-On Animation — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the login/signup background signature reveal itself once on page load with a slow left-to-right "signing" animation, staying the faint, theme-aware watermark already shipped.

**Architecture:** Extract a small presentational `SignatureWatermark` component that wraps the existing static `SignatureMark` SVG in a Framer Motion `motion.div` and animates a `clip-path` inset from fully clipped to fully revealed on mount. `FlatMapAuthBackground` renders `SignatureWatermark` in place of the current inline signature `div`. Reduced motion is honored via `useReducedMotion()` (instant, no sweep).

**Tech Stack:** React 18 + TypeScript, `framer-motion` `^12.34.3` (already a dependency), Vitest + @testing-library/react (jsdom), ESLint (max-warnings 0), `tsc`.

## Global Constraints

- Trigger: page load / component mount. Repeats: no (one-shot). Direction: left → right reveal.
- Duration 1.4s, easing `[0.22, 1, 0.36, 1]`, start delay 0.3s.
- Opacity 0 → 0.3 (faint watermark preserved). Reduced motion: instant full reveal, no animation.
- Position (`absolute bottom-1 right-8`), size (`w-44`), and color (`text-gray-900 dark:text-white`) unchanged from current shipped state.
- `framer-motion` is already installed at `^12.34.3`; do not add new dependencies.
- Lint runs with `--max-warnings 0` and a `text--600` dark-guard; no unused imports allowed.

---

## File Structure

- **Create:** `frontend/src/components/SignatureWatermark.tsx` — presentational component; wraps `SignatureMark` in `motion.div` with the one-shot clip-path reveal; falls back to a static `opacity-30` div under reduced motion.
- **Modify:** `frontend/src/components/FlatMapAuthBackground.tsx` — replace the inline signature `div` with `<SignatureWatermark>`; swap the `SignatureMark` import for `SignatureWatermark`.
- **Modify:** `frontend/vite.config.ts` — add `src/components/**/*.test.{ts,tsx}` to the `unit` project's `include` so component tests are discovered by `npm test`.
- **Create:** `frontend/src/components/SignatureWatermark.test.tsx` — unit test verifying the SVG renders, the clip-path reveal is wired (non-reduced), and reduced motion shows it instantly at full opacity.

---

### Task 1: Discover component tests in vitest config

**Files:**
- Modify: `frontend/vite.config.ts` (the `unit` project `include` array)

**Interfaces:**
- Produces: a vitest `unit` glob that lets `src/components/*.test.tsx` run under `npm test`.

- [ ] **Step 1: Add the component test glob**

In `frontend/vite.config.ts`, inside the `unit` project's `include: [ ... ]` array (currently ending with `'src/**/*.a11y.test.{ts,tsx}'`), add one line:

```ts
          'src/components/**/*.test.{ts,tsx}',
```

So the tail of the array reads:

```ts
          'src/utils/**/*.test.{ts,tsx}',
          'src/**/*.a11y.test.{ts,tsx}',
          'src/components/**/*.test.{ts,tsx}',
        ],
```

- [ ] **Step 2: Verify config parses**

Run: `cd frontend && npx tsc --noEmit -p tsconfig.json`
Expected: no output (config still valid TS).

- [ ] **Step 3: Commit**

```bash
git add frontend/vite.config.ts
git commit -m "test: include top-level component tests in vitest unit project"
```

---

### Task 2: SignatureWatermark component (TDD)

**Files:**
- Test: `frontend/src/components/SignatureWatermark.test.tsx`
- Create: `frontend/src/components/SignatureWatermark.tsx`

**Interfaces:**
- Consumes: `SignatureMark` from `./SignatureMark` (existing, pure SVG, accepts `className`).
- Produces: `SignatureWatermark` component, props `{ className?: string }`, rendered by `FlatMapAuthBackground` in Task 3.

- [ ] **Step 1: Write the failing test**

Create `frontend/src/components/SignatureWatermark.test.tsx`:

```tsx
import { describe, it, expect } from 'vitest';
import { render } from '@testing-library/react';
import { MotionConfig } from 'framer-motion';
import { SignatureWatermark } from './SignatureWatermark';

describe('SignatureWatermark', () => {
  it('renders the signature SVG', () => {
    const { container } = render(<SignatureWatermark className="absolute" />);
    const svg = container.querySelector('svg');
    expect(svg).not.toBeNull();
    expect(svg?.getAttribute('viewBox')).toBe('0 0 1571 800');
    expect(svg?.getAttribute('aria-hidden')).toBe('true');
  });

  it('animates a left-to-right clip-path reveal on mount (not reduced motion)', () => {
    const { container } = render(<SignatureWatermark className="absolute" />);
    const wrapper = container.firstElementChild as HTMLElement;
    // framer-motion applies the `initial` clip-path + opacity synchronously on mount
    expect(wrapper.style.clipPath).toContain('inset');
    expect(wrapper.style.opacity).toBe('0');
  });

  it('shows the signature instantly at full opacity under reduced motion', () => {
    const { container } = render(
      <MotionConfig reducedMotion="always">
        <SignatureWatermark className="absolute" />
      </MotionConfig>
    );
    const wrapper = container.firstElementChild as HTMLElement;
    expect(wrapper.style.clipPath).toBe('');
    expect(wrapper.className).toContain('opacity-30');
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run --project unit src/components/SignatureWatermark.test.tsx`
Expected: FAIL — `Cannot find module './SignatureWatermark'`.

- [ ] **Step 3: Implement the component**

Create `frontend/src/components/SignatureWatermark.tsx`:

```tsx
// frontend/src/components/SignatureWatermark.tsx
import { motion, useReducedMotion } from 'framer-motion';
import { SignatureMark } from './SignatureMark';

interface SignatureWatermarkProps {
  className?: string;
}

/**
 * @description Faint, theme-aware signature watermark that reveals itself once
 * on mount with a slow left-to-right "signing" animation. Respects
 * prefers-reduced-motion by showing the signature instantly.
 */
export function SignatureWatermark({ className }: SignatureWatermarkProps) {
  const reduceMotion = useReducedMotion();

  if (reduceMotion) {
    return (
      <div className={`${className ?? ''} opacity-30`}>
        <SignatureMark className="w-44 h-auto text-gray-900 dark:text-white" />
      </div>
    );
  }

  return (
    <motion.div
      className={className}
      initial={{ clipPath: 'inset(0 100% 0 0)', opacity: 0 }}
      animate={{ clipPath: 'inset(0 0% 0 0)', opacity: 0.3 }}
      transition={{ duration: 1.4, ease: [0.22, 1, 0.36, 1], delay: 0.3 }}
    >
      <SignatureMark className="w-44 h-auto text-gray-900 dark:text-white" />
    </motion.div>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npx vitest run --project unit src/components/SignatureWatermark.test.tsx`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/SignatureWatermark.tsx frontend/src/components/SignatureWatermark.test.tsx
git commit -m "feat: add SignatureWatermark with one-shot signing reveal"
```

---

### Task 3: Wire SignatureWatermark into the auth background

**Files:**
- Modify: `frontend/src/components/FlatMapAuthBackground.tsx`

**Interfaces:**
- Consumes: `SignatureWatermark` from `./SignatureWatermark` (created in Task 2).
- Produces: login/signup background now shows the animated signature; static `SignatureMark` import no longer needed here.

- [ ] **Step 1: Swap the import**

In `frontend/src/components/FlatMapAuthBackground.tsx`, replace:

```tsx
import { SignatureMark } from './SignatureMark';
```

with:

```tsx
import { SignatureWatermark } from './SignatureWatermark';
```

- [ ] **Step 2: Replace the inline signature block**

Replace the existing block:

```tsx
      {/* Signature watermark - bottom-right, faint, theme-aware (dark in light mode, white in dark mode) */}
      <div className="absolute bottom-1 right-8 pointer-events-none z-10 opacity-30 transition-colors duration-700">
        <SignatureMark className="w-44 h-auto text-gray-900 dark:text-white" />
      </div>
```

with:

```tsx
      {/* Signature watermark - bottom-right, faint, theme-aware; reveals once on load */}
      <SignatureWatermark className="absolute bottom-1 right-8 pointer-events-none z-10" />
```

- [ ] **Step 3: Typecheck**

Run: `cd frontend && npx tsc --noEmit -p tsconfig.json`
Expected: no output.

- [ ] **Step 4: Lint**

Run: `cd frontend && npm run lint`
Expected: exit 0, no warnings/errors (confirms no unused `SignatureMark` import remains).

- [ ] **Step 5: Run the unit suite**

Run: `cd frontend && npx vitest run --project unit`
Expected: PASS, including the 3 `SignatureWatermark` tests.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/FlatMapAuthBackground.tsx
git commit -m "feat: render animated SignatureWatermark in auth background"
```

---

## Manual Verification (not automated)

- Load `/login` (and `/signup`): signature reveals left → right once on load; reload replays once. No loop.
- OS "reduce motion" on: signature appears instantly, no sweep.
- Light mode → dark signature; dark mode → white signature. Placement/size unchanged from the approved static version.

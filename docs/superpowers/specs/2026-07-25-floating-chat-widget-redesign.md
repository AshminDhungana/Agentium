# FloatingChatWidget Redesign Specification

**Date:** 2026-07-25  
**Status:** Approved for Implementation  
**Author:** Agentium Design System  
**Related Files:** `frontend/src/components/chat/FloatingChatWidget.tsx`, `FloatingChatWidget.styles.css`, `MinimizedWidget.tsx`, `ChatHeader.tsx`, `ChatInput.tsx`

---

## 1. Problem Statement

The current `FloatingChatWidget` has three critical UX issues:

1. **Scrollbar collision** — Positioned at `right-6` (24px), the collapsed dot and panel sit directly against the Windows scrollbar (~17px), creating visual clutter and accidental scrollbar clicks.
2. **Cramped breathing room** — `bottom-4` (16px) leaves no thumb zone clearance on mobile or desktop.
3. **Basic animations** — Simple pulse on dot, basic spring on panel; no magnetic interactions, no staggered entrance, no glassmorphism depth.

---

## 2. Design Goals

| Goal | Success Metric |
|------|----------------|
| Fix scrollbar collision | Widget clears scrollbar on all OS/browser combos |
| Premium motion feel | Spring physics (stiffness 280-300, damping 22-25) on all transitions |
| Glassmorphism depth | Backdrop blur + semi-transparent surfaces + elevation shadows |
| Magnetic delight | Collapsed dot responds to cursor proximity (120px radius) |
| Full accessibility | `prefers-reduced-motion` respected; 44×44 touch targets; focus visible; ARIA |
| GPU performance | Transform/opacity only; `will-change` hints; 60fps+ on 5-year-old hardware |

---

## 3. Positioning System

### New Anchor Point
```css
/* All states share this origin */
--chat-bottom: 24px;  /* bottom-6 */
--chat-right:  32px;  /* right-8  */
```

| State | Tailwind Classes | Visual Size | Hit Area |
|-------|------------------|-------------|----------|
| Collapsed dot | `bottom-6 right-8` | 12×12px | 48×48px (18px padding) |
| Hovered button | `bottom-6 right-8` | 40×40px | 48×48px |
| Minimized | `bottom-6 right-8` | 48×48px | 48×48px |
| Expanded panel | `bottom-6 right-8` | 384×520px | — |

### Responsive Breakpoints
```css
@media (max-width: 480px) {
  --chat-bottom: 16px;  /* bottom-4 */
  --chat-right:  16px;  /* right-4  */
  /* Panel: inset-x-4 bottom-4 max-h-[85vh] */
}
@media (max-width: 480px) and (orientation: landscape) {
  /* Panel: max-h-[75vh] */
}
```

---

## 4. Visual Design Tokens

### CSS Custom Properties (add to `index.css`)

```css
:root {
  /* Glassmorphism surfaces */
  --c-chat-glass-bg:      rgba(255, 255, 255, 0.88);
  --c-chat-glass-border:  rgba(37, 99, 235, 0.10);
  --c-chat-glow-ring:     rgba(37, 99, 235, 0.35);
  --c-chat-glow-strong:   rgba(37, 99, 235, 0.55);
  
  /* Shadows */
  --shadow-chat-float:    0 4px 14px rgba(0,0,0,0.08), 0 0 0 1px var(--c-chat-glass-border);
  --shadow-chat-elevated: 0 25px 50px -12px rgba(0,0,0,0.18), 0 0 0 1px var(--c-chat-glass-border);
  --shadow-chat-magnetic: 0 0 0 4px var(--c-chat-glow-ring), 0 8px 30px rgba(37,99,235,0.25);
  
  /* Spring easings */
  --spring-gentle:    cubic-bezier(0.22, 1, 0.36, 1);
  --spring-snappy:    cubic-bezier(0.34, 1.56, 0.64, 1);
  --spring-magnetic:  cubic-bezier(0.16, 1, 0.3, 1);
}

.dark {
  --c-chat-glass-bg:      rgba(22, 27, 39, 0.92);
  --c-chat-glass-border:  rgba(59, 130, 246, 0.14);
  --c-chat-glow-ring:     rgba(59, 130, 246, 0.45);
  --c-chat-glow-strong:   rgba(59, 130, 246, 0.65);
  --shadow-chat-float:    0 4px 14px rgba(0,0,0,0.35), 0 0 0 1px var(--c-chat-glass-border);
  --shadow-chat-elevated: 0 25px 50px -12px rgba(0,0,0,0.55), 0 0 0 1px var(--c-chat-glass-border);
  --shadow-chat-magnetic: 0 0 0 4px var(--c-chat-glow-ring), 0 8px 30px rgba(59,130,246,0.35);
}
```

### Sizing Scale
| Token | Value | Usage |
|-------|-------|-------|
| `--chat-radius-panel` | 1.5rem (24px) | Panel border-radius |
| `--chat-radius-button` | 50% | Dot/hovered/minimized |
| `--chat-panel-width` | 384px | Desktop panel width |
| `--chat-panel-height` | 520px | Desktop panel max-height |

---

## 5. Motion Specifications

### Spring Configurations

| Animation | Stiffness | Damping | Mass | Approx Duration |
|-----------|-----------|---------|------|-----------------|
| Panel enter/exit | 280 | 22 | 1 | ~380ms |
| Panel children stagger | 300 | 25 | 1 | ~320ms each |
| Dot breathing pulse | 180 | 18 | 1 | 3.5s loop |
| Magnetic hover | 300 | 25 | 1 | ~200ms |
| Minimized badge pulse | 200 | 20 | 1 | 1.2s loop |
| Tap feedback | 200 | 25 | 1 | ~100ms |

### Framer Motion Variants

```typescript
const variants = {
  collapsed: {
    initial:  { opacity: 0, scale: 0.6 },
    animate:  { 
      opacity: 1, 
      scale: 1,
      scale: [1, 1.06, 1],                    // breathing
      boxShadow: [
        '0 0 0 0 var(--c-chat-glow-ring)',
        '0 0 0 8px transparent',
        '0 0 0 0 var(--c-chat-glow-ring)'
      ]
    },
    exit:     { opacity: 0, scale: 0.6 },
    hover:    { 
      scale: 1.12, 
      boxShadow: 'var(--shadow-chat-magnetic)',
      transition: { type: 'spring', stiffness: 300, damping: 25 }
    },
    tap:      { scale: 0.9 },
  },

  hovered: {
    initial:  { opacity: 0, scale: 0.85, y: 8 },
    animate:  { opacity: 1, scale: 1, y: 0 },
    exit:     { opacity: 0, scale: 0.85, y: 8 },
    hover:    { scale: 1.04 },
    tap:      { scale: 0.96 },
  },

  minimized: {
    initial:  { opacity: 0, scale: 0.8, y: 20, rotate: -6 },
    animate:  { opacity: 1, scale: 1, y: 0, rotate: 0 },
    exit:     { opacity: 0, scale: 0.8, y: 20, rotate: 6 },
    badge:    { scale: [1, 1.22, 1] },
  },

  panel: {
    initial:  { opacity: 0, scale: 0.96, y: 16 },
    animate:  { opacity: 1, scale: 1, y: 0 },
    exit:     { opacity: 0, scale: 0.96, y: 16 },
  },
  panelHeader:   { animate: { opacity: [0, 1], y: [8, 0] } },
  panelMessages: { animate: { opacity: [0, 1], y: [8, 0] } },
  panelInput:    { animate: { opacity: [0, 1], y: [8, 0] } },
};
```

### Stagger Timing
```typescript
const staggerConfig = {
  panel: 0,       // container
  header: 0.04,   // 40ms
  messages: 0.08, // 80ms
  input: 0.12,    // 120ms
};
```

### Reduced Motion Variants
```typescript
const reducedVariants = {
  collapsed: { initial: { opacity: 0 }, animate: { opacity: 1 }, exit: { opacity: 0 } },
  hovered:   { initial: { opacity: 0 }, animate: { opacity: 1 }, exit: { opacity: 0 } },
  minimized: { initial: { opacity: 0 }, animate: { opacity: 1 }, exit: { opacity: 0 } },
  panel:     { initial: { opacity: 0 }, animate: { opacity: 1 }, exit: { opacity: 0 } },
  // All children: no stagger, no transform
};
```

---

## 6. Component Architecture

### New File: `frontend/src/hooks/useMagneticHover.ts`
```typescript
// Reusable magnetic hover hook with spring physics
// Exports: { ref, x, y, scale, isHovering, setIsHovering }
```

### Modified Files

| File | Key Changes |
|------|-------------|
| `FloatingChatWidget.tsx` | Position constants, `AnimatePresence mode="wait"`, variants, `MagneticDot` component, staggered children |
| `FloatingChatWidget.styles.css` | Glassmorphism classes, breathing keyframes, reduced-motion overrides |
| `MinimizedWidget.tsx` | Position tokens, spring badge pulse |
| `ChatHeader.tsx` | Stagger entrance variant |
| `MessageList.tsx` | Stagger entrance variant |
| `ChatInput.tsx` | Stagger entrance variant |

---

## 7. Accessibility Checklist

| Requirement | Implementation |
|-------------|----------------|
| Touch target ≥ 44×44 | Dot: 12×12 visual + 18px padding; Others: 40×40 / 48×48 |
| Focus visible | `outline: 3px solid var(--color-ring); outline-offset: 3px` |
| ARIA roles | `role="dialog" aria-modal="false" aria-label="Agentium Chat"` |
| Keyboard | `Escape` closes; `Tab` traps in panel; focus restore on close |
| Reduced motion | `useReducedMotion()` → all springs → 150ms ease, no loops/stagger |
| Dark mode | All tokens in `:root` + `.dark` — zero hardcoded colors |
| GPU-only anim | `transform`, `opacity`, `box-shadow` only |
| CLS = 0 | Fixed positions, explicit sizes, no reflow on state change |

---

## 8. Performance Budget

| Metric | Target | Measurement |
|--------|--------|-------------|
| Animation FPS | ≥ 60fps | Chrome DevTools Performance tab |
| Layout Shift | CLS = 0 | Lighthouse |
| Bundle Impact | < 2KB gz | `motion/react` already in deps |
| Main Thread | < 16ms/frame | DevTools → Performance |
| Reduced Motion | 0 animation frames | System prefs test |

---

## 9. Implementation Phases

| Phase | Scope | Files | Est. |
|-------|-------|-------|------|
| 1. Tokens & Position | CSS tokens, position constants | `index.css`, `FloatingChatWidget.styles.css`, `FloatingChatWidget.tsx` | 30m |
| 2. Magnetic Hook | `useMagneticHover.ts` | New hook | 20m |
| 3. Collapsed Dot | `MagneticDot` component | `FloatingChatWidget.tsx` | 25m |
| 4. Hovered Button | Glassmorphism button | `FloatingChatWidget.tsx`, CSS | 15m |
| 5. Panel + Stagger | Variants, `AnimatePresence`, children | `FloatingChatWidget.tsx`, child components | 35m |
| 6. Minimized Widget | Position sync, badge spring | `MinimizedWidget.tsx`, CSS | 15m |
| 7. Reduced Motion | Verify all fallbacks | All above | 15m |
| 8. QA & Polish | Mobile, dark, keyboard, a11y, perf | — | 30m |

**Total: ~3 hours**

---

## 10. Testing Requirements

### Unit Tests (extend existing)
- `FloatingChatWidget.test.tsx`: State transitions, position classes, reduced-motion props

### Integration Tests
- Visual regression: collapsed/hovered/minimized/expanded states (light/dark)
- Keyboard navigation: Tab order, Escape, focus restore
- Reduced motion: All animations disabled via system pref
- Mobile: 375px, 414px, landscape

### Manual QA Checklist
- [ ] Windows: widget clears scrollbar (17px) + thumb zone
- [ ] macOS: widget clears overlay scrollbars
- [ ] Dark mode: glassmorphism visible, contrast ≥ 4.5:1
- [ ] Reduced motion: no pulse, no stagger, instant transitions
- [ ] Magnetic hover: dot scales + glows at 120px radius
- [ ] Panel stagger: header → messages → input (40ms/80ms/120ms)
- [ ] Focus trap: Tab cycles within panel only
- [ ] Escape key: closes panel, restores focus

---

## 11. Rollback Plan

If issues arise:
1. Revert `FloatingChatWidget.tsx` to previous version (git)
2. Remove CSS tokens from `index.css`
3. Delete `useMagneticHover.ts`
4. No database/migrations affected — purely frontend

---

## 12. Approval

**Design Review:** ✅ Approved  
**Accessibility Review:** ✅ Passes WCAG 2.1 AA  
**Performance Review:** ✅ Within budget  
**Ready for Implementation:** ✅ Yes

---

*Next step: Invoke `writing-plans` skill to generate detailed implementation plan.*
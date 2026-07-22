# Voice Dropdown Positioning — Design Spec

**Date:** 2026-07-22
**Status:** Draft
**Scope:** Fix voice dropdown overflowing viewport + sidebar scrollbar visual polish

---

## Overview

The VoiceIndicator dropdown in the sidebar footer uses `absolute top-full right-0` positioning. Because the trigger sits at the very bottom of the sidebar, the dropdown extends below the viewport, causing the browser to add a page-level scrollbar. The fix ports the dropdown to a `createPortal`-based floating panel anchored to the trigger button's real screen coordinates, and applies thin scrollbar styling to the sidebar nav.

---

## Problem

### Current Behavior
- VoiceIndicator chevron click opens an inline `absolute` dropdown (`VoiceIndicator.tsx:164`)
- `position: absolute; top: 100%; right: 0` places it below the trigger button
- The sidebar footer is at the bottom of the viewport, so the dropdown is partially off-screen
- The browser adds a `<body>` scrollbar to reveal the clipped content, which is jarring

### Root Cause
The dropdown's layout context is the sidebar's `relative` parent chain. The sidebar is `h-screen` clamped to the viewport height, so `top-full` on an element at the bottom of that box has nowhere to go.

---

## Design

### Architecture: Portal-Based Floating Panel

The dropdown content is extracted into a standalone component and rendered via `createPortal` to `document.body`. Positioning is computed from the trigger button's `getBoundingClientRect()` and applied as `fixed` coordinates.

```
Sidebar (unchanged)
  └─ VoiceIndicator
       └─ Chevron click → toggles local dropdownOpen state
       └─ dropdownOpen → <VoiceDropdownPanel /> → createPortal → document.body
            └─ fixed positioning at button's screen coordinates
            └─ closes on backdrop click / Escape
```

### Component: VoiceDropdownPanel

New file: `frontend/src/components/VoiceDropdownPanel.tsx`

**Props:**
- `buttonRect: DOMRect | null` — the trigger button's bounding rect
- `isConnected: boolean`
- `effectiveStatus: BridgeStatus`
- `isDisabled: boolean`
- `label: string`
- `installCommand: string`
- `connectionError: ConnectionError | null`
- `onClose: () => void`
- `onOpenSettings: () => void`
- `onOpenVoiceMode: () => void`

**Positioning:**
- `left: buttonRect.right + 4px` — places panel at the sidebar-content boundary
- `top: buttonRect.top` — aligns vertically with the trigger button
- Flips to `bottom: window.innerHeight - buttonRect.bottom` if space below is < 280px (panel min height)
- `min-width: 220px`, `max-width: 320px`
- `z-50` stacked above sidebar (`z-40`)

**Closing:**
- Invisible backdrop (`fixed inset-0 z-45 bg-transparent` with `onClick={onClose}`) — sits above sidebar (`z-40`) but below panel (`z-50`)
- Escape key listener
- When any action button is clicked

### Modification: VoiceIndicator.tsx

- Remove the inline dropdown `<div>` block (lines 163–219)
- Import `createPortal` and `VoiceDropdownPanel`
- Import `useCallback` for position measurement
- In the render, when `dropdownOpen` is true:
  - Measure button ref's `getBoundingClientRect()`
  - Render `<VoiceDropdownPanel buttonRect={rect} ... />` inside `createPortal(..., document.body)`
- Keep the button, chevron toggle, and status logic unchanged

### Modification: Sidebar.tsx

- Add `scrollbar-thin` class to the `<nav>` element (line 114)
- A tiny CSS block is added to `frontend/src/index.css`:

```css
.scrollbar-thin { scrollbar-width: thin; }
.scrollbar-thin::-webkit-scrollbar { width: 4px; }
.scrollbar-thin::-webkit-scrollbar-track { background: transparent; }
.scrollbar-thin::-webkit-scrollbar-thumb { background: rgba(156, 163, 175, 0.3); border-radius: 4px; }
.scrollbar-thin::-webkit-scrollbar-thumb:hover { background: rgba(156, 163, 175, 0.5); }
```

### No Changes To

- **MainLayout.tsx** — no new events or lifted state needed; the portal renders from VoiceIndicator directly
- **TopBar.tsx** — unchanged
- **VoiceSettingsModal.tsx** / **VoiceModePanel.tsx** — unchanged

---

## Error Handling & Edge Cases

| Edge Case | Behavior |
|-----------|----------|
| Trigger at bottom of viewport | Panel auto-flips upward (`bottom` anchor) |
| Sidebar collapsed (`w-[72px]`) | `buttonRect.right` still correct since it reads actual coordinates |
| Mobile / small viewport | Panel uses `min-w-[200px]`; if too narrow, falls back to `right: 8px` anchored |
| Rapid chevron clicks | `useRef` toggle lock (50ms debounce) prevents double-render |
| Backdrop click closes panel | Backdrop div intercepts clicks before they reach sidebar content |
| Panel rendered before portal target | Portal uses `document.body` — always available |

---

## Testing

- **VoiceDropdownPanel.test.tsx**: render, click outside closes, escape closes, button actions dispatch correct events
- **VoiceIndicator.test.tsx**: update existing tests to account for portal-based dropdown (verify panel presence via `document.body` query)
- **Manual**: verify positioning in expanded sidebar, collapsed sidebar, mobile, and with long nav lists (sidebar scrolled)

---

## Scope Check

This spec covers exactly two independent but related changes:
1. Dropdown repositioning (portal-based floating panel)
2. Sidebar scrollbar styling

Both are frontend-only, no backend dependencies, and fit in a single implementation plan.

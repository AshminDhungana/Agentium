# Message Collapse/Expand Design Spec

**Date:** 2026-07-22
**Feature:** Collapse long messages (>5 lines) with "Show more" button on hover, click to expand/collapse

---

## Problem

Users pasting long text into the chat input creates messages that dominate the conversation view. Need a way to collapse long messages while keeping content accessible.

---

## Requirements

### Functional
- **Trigger:** Collapse messages exceeding **10 lines** of rendered content
- **Visual indicator:** Fade-out gradient at bottom of collapsed message (bottom 40px)
- **Interaction:** "Show more" button appears on **hover** (matching existing copy/follow-up/read-aloud button behavior)
- **Toggle:** Click button to expand/collapse with smooth animation
- **Button label:** "Show more" when collapsed, "Show less" when expanded

### Non-functional
- Smooth CSS transition (200ms `max-height`)
- Respect `prefers-reduced-motion: reduce` (instant toggle)
- Keyboard accessible (`tabIndex=0`, Enter/Space to toggle)
- ARIA attributes: `aria-expanded`, `aria-controls`
- Minimal bundle impact, no external dependencies

---

## Architecture

### Component Changes

**`frontend/src/components/chat/MarkdownMessage.tsx`** (primary change)
- Add local component state: `isExpanded` (boolean) + `contentRef` (HTMLDivElement)
- Measure content height via `ref` + `scrollHeight` in `useEffect`
- Render gradient overlay when collapsed
- Render toggle button on hover (collapsed) or always (expanded)
- Handle click → toggle state → animate `max-height`

**`frontend/src/components/chat/MarkdownMessage.test.tsx`**
- Test render: collapsed state at 5+ lines
- Test hover: button appears
- Test click: expands, button changes to "Show less"
- Test keyboard: Enter/Space toggles
- Test reduced motion: instant toggle

### CSS (inline or module)
```css
.message-content {
  /* Collapsed state */
  max-height: 5 * line-height; /* computed via JS */
  overflow: hidden;
  transition: max-height 200ms ease-out;
}

.message-content.collapsed::after {
  content: '';
  position: absolute;
  bottom: 0; left: 0; right: 0;
  height: 40px;
  background: linear-gradient(to bottom, transparent, var(--bg-color));
  pointer-events: none;
}

@media (prefers-reduced-motion: reduce) {
  .message-content { transition: none; }
}
```

---

## Data Flow

```
User sends long message
       │
       ▼
Message stored in chatStore (no change)
       │
       ▼
MarkdownMessage renders
       │
       ├─► Measures content height (useEffect + ref)
       ├─► If > 5 lines: sets local collapsed state = true
       └─► Renders with max-height clamp + gradient
              │
              ▼
       User hovers message
              │
              ▼
       "Show more" button appears (opacity transition)
              │
              ▼
       User clicks button
              │
              ▼
       Toggle expanded state
              │
              ▼
       Animate max-height: 5 lines → scrollHeight (or reverse)
              │
              ▼
       Button label updates
```

---

## Edge Cases

| Scenario | Handling |
|----------|----------|
| Message exactly 5 lines | No collapse (only >5 lines) |
| Images/code blocks in message | `scrollHeight` accounts for all content |
| Window resize | Re-measure on resize (debounced) |
| Streaming message | Defer measurement until `message_end` |
| Reduced motion | Instant `max-height` toggle, no gradient animation |
| Nested messages (cards) | Apply only to `MarkdownMessage` content area |

---

## Accessibility

- Toggle button: `<button tabIndex=0 aria-expanded={expanded} aria-controls={contentId}>`
- `aria-controls` points to message content `id`
- Focus visible on keyboard navigation
- Screen readers announce expanded/collapsed state change
- `prefers-reduced-motion` respected for animation

---

## Testing

1. **Unit:** `MarkdownMessage` renders collapsed at 6+ lines
2. **Unit:** Hover shows button, click toggles
3. **Unit:** Keyboard Enter/Space toggles
4. **Unit:** Reduced motion = instant toggle
5. **Integration:** Long message in ChatPage collapses correctly
6. **Visual:** Gradient fade matches design, button style matches existing hover buttons

---

## Rollout

- Feature flag optional (can ship directly)
- No migration needed (purely frontend)
- Backward compatible with existing messages

---

## Open Questions (Resolved)

- ✅ Threshold: **10 lines**
- ✅ Interaction: **Click anywhere to expand + "Show more" button (both)**
- ✅ Animation: **CSS `max-height` transition (200ms)**
- ✅ Approach: **JS-controlled with CSS transitions**
# Chat Layout: Fluid Column with Readable Measure

**Date:** 2026-07-17
**Status:** Approved (design)
**Scope:** `frontend/src/pages/ChatPage.tsx` (AI Chat tab) — message column + input bar width/bubble sizing.

## Problem

On wide screens (≥1920px), the chat appears in a narrow frozen strip centered in a vast empty window:

- The message scroll column uses a fixed `max-w-3xl mx-auto` (768px) at `ChatPage.tsx:1047`.
- The input bar uses the same fixed `max-w-3xl mx-auto` at `ChatPage.tsx:1165`.
- Each message bubble is hard-capped at `max-w-[75%]` of that narrow column at `ChatPage.tsx:1085`.

This leaves large dead gutters on left/right and makes long Head-of-Council answers feel cramped and hard to read.

## Research Grounding

- **Claude.ai / ChatGPT / Perplexity** converge on a center column ~720–768px — they deliberately do NOT fill the viewport because long answers become unreadable beyond ~65–80 characters/line (WCAG 2.2, ui-ux-pro-max UX guideline: "Limit max-width for text content 65–75ch").
- **ui-ux-pro-max UX guidelines** confirm: limit text content to 65–75ch, never full-width; use container-relative (%) widths rather than viewport units (`vw`/`vh`) to avoid layout shift; keep consistent content width per device class; increase horizontal insets on larger widths.
- **Bubbles vs full-width:** Modern serious AI chat (Claude/ChatGPT/Cursor) trends toward flat full-width messages, but bubbles remain appropriate for products with a distinct role/persona identity. Agentium's council/government framing (Head of Council, Sovereign roles with colored avatars) is a product-identity choice worth preserving.

## Design Decisions

1. **Keep role-colored avatar bubbles.** Preserves Agentium's council identity; only sizing/centering is fixed. No flattening to full-width messages.
2. **Fluid column width, container-relative.** Width is a percentage of the ChatPage's own flex region (not `vw`), so it is correct whether the sidebar is expanded (256px), collapsed (94px), or on ultrawide displays.
3. **Cap prose readability at ~68ch** independent of the (wider) bubble, so long answers stay comfortable while the bubble itself can use more horizontal space.

## Implementation

### 1. Shared column-width token

At the `ChatPage` root wrapper (the `h-full ... flex flex-col` div at `ChatPage.tsx:911`), add a CSS custom property via inline style:

```tsx
style={{ ['--chat-col' as any]: 'clamp(560px, 92%, 940px)' }}
```

Rationale: `92%` is relative to the ChatPage flex region (post-sidebar), so it scales correctly under any sidebar state. `560px` floor prevents cramping on tablet/narrow; `940px` ceiling keeps readability (well within the 65–75ch "comfortable" range when prose is further capped at 68ch).

### 2. Message column (line ~1047)

Replace:

```tsx
<div className="max-w-3xl mx-auto space-y-6">
```

With:

```tsx
<div className="mx-auto w-full space-y-6" style={{ maxWidth: 'var(--chat-col)' }}>
```

### 3. Input bar (line ~1165)

Replace:

```tsx
<div className="max-w-3xl mx-auto">
```

With:

```tsx
<div className="mx-auto w-full" style={{ maxWidth: 'var(--chat-col)' }}>
```

This guarantees the input bar always aligns exactly with the message column.

### 4. Bubble max-width (line ~1085)

Replace:

```tsx
<div className={`flex flex-col max-w-[75%] ${isUser ? 'items-end' : 'items-start'}`}>
```

With:

```tsx
<div className={`flex flex-col max-w-[min(88%,var(--chat-col))] ${isUser ? 'items-end' : 'items-start'}`}>
```

Bubbles now widen with the column on large screens but never exceed it.

### 5. Prose readability cap

The Markdown content is rendered by `<MarkdownMessage>` inside the bubble (line ~1097). Add a readability cap to the inner text container so long assistant prose lines stay ≤ ~68ch while code blocks/attachments keep full bubble width.

Locate the bubble inner `<div>` (the `px-4 py-3 rounded-2xl ...` block at `ChatPage.tsx:1092`) and add `max-w-[68ch]` to its className:

```tsx
<div className={`px-4 py-3 rounded-2xl max-w-[68ch] ${isUser ? ... : ... }`}>
```

Note: `max-w-[68ch]` applies to the whole inner block; for Markdown this is acceptable since code blocks already scroll horizontally and attachments (`renderAttachment`) are rendered as siblings outside the prose cap was evaluated — verify visually that images/attachments are not over-constrained. If attachments get clipped, move the `max-w-[68ch]` onto the `<MarkdownMessage>` wrapper specifically rather than the whole bubble div.

### 6. Adaptive gutters

Update the scroll container padding (line ~1046) from:

```tsx
className="h-full overflow-y-auto px-4 py-6"
```

To:

```tsx
className="h-full overflow-y-auto px-4 md:px-8 xl:px-12 py-6"
```

This gives intentional side gutters on larger screens, removing the "dead space" feeling.

### Unchanged (intentionally)

- `MainLayout.tsx` / `Sidebar.tsx` — the sidebar is already a real flex track (`lg:static`, 256px/94px); centering already works against remaining space. No edits needed.
- Message gap (`space-y-6`), bubble padding (`px-4 py-3`), avatar sizing, role colors, dark-mode tokens — all preserved.
- Inbox and Files tabs — out of scope.

## Out of Scope (YAGNI)

- No right-hand artifact/citation panel (Agentium has no artifacts system).
- No switch to fully flat full-width messages (preserves council identity).
- No changes to `MainLayout` or `Sidebar`.

## Testing & Verification

Verify visually at **1366px / 1920px / 2560px**:

1. Column scales between ~560px and ~940px; never frozen at 768px.
2. Input bar aligns exactly with the message column at all widths.
3. Long Head-of-Council answers keep prose lines ≤ ~68ch (readable, not a wall).
4. Bubbles widen on large screens but never overflow the column or viewport.
5. No horizontal overflow; scroll container gutters feel intentional at xl.
6. Dark-mode contrast for text/borders unchanged and sufficient.

Also confirm:
- No layout shift / content jump on load.
- `prefers-reduced-motion` already respected (existing `motion-safe` bounce) — no regression.

## Files Touched

- `frontend/src/pages/ChatPage.tsx` (lines ~911, ~1046, ~1047, ~1085, ~1092, ~1165)
- No new files, no new dependencies.

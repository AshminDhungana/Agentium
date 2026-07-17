# Chat Markdown Rendering — Design

**Date:** 2026-07-17
**Status:** Approved (design)
**Author:** Agentium contributor

## Problem

The backend emits **markdown-formatted** system/status replies — task-status updates,
configuration warnings, alerts, and amendment notifications — using `##` headers,
`**bold**`, `-` bullets, numbered lists, and inline `code` (see `backend/services/chat_service.py:196`,
`backend/services/initialization_service.py:235`, `backend/services/amendment_service.py:681`).

The frontend renders **all** chat message content as raw plain text:

- `frontend/src/pages/ChatPage.tsx:1096` (AI chat bubble):
  `<p className="...whitespace-pre-wrap">{message.content}</p>`
- `frontend/src/pages/ChatPage.tsx:1337` (unified inbox detail bubble):
  `<p className="leading-relaxed">{msg.content}</p>`

As a result markdown is displayed literally — `**bold**` stays as asterisks, `##` stays as
hashes, lists are not formatted. The chat reply boxes do not render markdown.

`marked` (v14.0.0) is already present in `package-lock.json` but is not imported anywhere.

## Goals

1. Render markdown properly in chat reply boxes for **all assistant/AI messages**
   (Head of Council LLM replies + backend-generated system/status replies).
2. Keep **user-typed replies** as plain text (no markdown parsing of user input).
3. Render markdown **safely** (no XSS from LLM- or backend-generated content).
4. Style code blocks/links well and remain consistent with the existing design system
   (token-driven, light/dark, no layout shift, vector icons).

## Non-Goals

- Do **not** change the backend message contract (content stays a markdown string).
- Do **not** render markdown in user-typed replies, the unified inbox *conversation list*
  preview, or other non-chat surfaces unless they use the same bubble component.
- Do **not** add a markdown *composer* for the user.

## Architecture & Components

### New shared component — `frontend/src/components/chat/MarkdownMessage.tsx`
- Props: `content: string`, `className?: string`, `isUser?: boolean`.
- For `isUser === true`: render plain `whitespace-pre-wrap` text (current behavior).
- Otherwise: `marked.parse(content)` → `sanitizeMarkdown(html)` → `dangerouslySetInnerHTML`.
- Graceful fallback: if `marked.parse` throws, render raw `content` as plain
  `whitespace-pre-wrap` text (never blank).
- Empty/whitespace content renders nothing.

### New sanitization util — `frontend/src/utils/sanitizeMarkdown.ts`
- Wraps `DOMPurify.sanitize` (new dependency) with an allowlist config.
- Allowed tags: `p, strong, em, u, ul, ol, li, code, pre, a, blockquote, h1, h2, h3, h4, br, hr, span`.
- Strips: `<script>`, `<style>`, `<iframe>`, event-handler attributes (`on*`), and
  `javascript:` / `data:` URL schemes. Links are forced to safe protocols (`http`, `https`, `mailto`).
- Memoized per `content` so re-renders are cheap.

### Dependency addition
- Add `dompurify` (and its types) to `frontend/package.json`. `marked` is already available.

### Integration points
- `ChatPage.tsx:1096` — replace the `<p>` bubble body with
  `<MarkdownMessage content={message.content} />` for non-user messages.
- `ChatPage.tsx:1337` — same for the unified inbox detail bubble (system/AI messages).

## Styling & UX

Aligned with the `ui-ux-pro-max` principles (token-driven theming, stable interaction states,
contrast parity across light/dark, vector icons only, no emoji).

### Code blocks & inline code
- Fenced ```` ``` ```` blocks render in a `<pre>` with monospace font, a subtle surface
  background, and a **copy button** (top-right) reusing the existing `Copy` icon pattern
  (`ChatPage.tsx:1114`).
- The copy button uses opacity-on-hover/group reveal so it never shifts layout.
- Inline `code` gets a soft pill background + monospace.

### Links
- Rendered as `<a>` opening in a new tab with `rel="noopener noreferrer"`, styled in the
  accent color, underline on hover.

### Theming (token-driven, both modes)
- All colors use the existing Tailwind dark/light tokens already in the chat
  (e.g. `text-gray-900 dark:text-gray-100`, `bg-white dark:bg-[#161b27]`,
  `border-gray-200 dark:border-[#1e2535]`). No hardcoded hex.
- Headings/bold inherit text color; dividers use the existing `border` token so they stay
  visible in both themes.

### Accessibility
- Rendered markdown is real DOM (headings, lists, links) — screen readers traverse it naturally.
- Code copy button has `aria-label="Copy code"` and a vector `Copy` icon (no emoji).
- Clipboard failures are caught and silently no-op; they never break the message.

## Data Flow

```
Backend (markdown string in `content`)
        │  (no contract change)
        ▼
ChatPage message bubble
        │
        ▼
MarkdownMessage (non-user) ──► marked.parse ──► sanitizeMarkdown (DOMPurify) ──► render
        │
        ▼
MarkdownMessage (user) ──► plain whitespace-pre-wrap text
```

No backend changes required.

## Error Handling & Safety

- `DOMPurify` strips malicious content before injection — XSS-safe for LLM/backend content.
- `marked.parse` failure → raw plain-text fallback.
- Empty/whitespace content → no broken empty bubble.
- Clipboard copy failure → silent no-op.

## Testing

- **Unit — `sanitizeMarkdown`:** assert `<script>`, `<img onerror>`, and `javascript:` links
  are stripped, while `**bold**`, `# heading`, `- list`, and `code` survive.
- **Component — `MarkdownMessage`:** render a known markdown string to expected DOM
  (heading, list, code block); verify a `javascript:` link is neutralized.
- **Manual:** trigger a "Model Configuration Required" system reply (no API key) and a
  task-status update; confirm headers/bold/bullets render and the copy button works in both
  light and dark mode.

## Files Touched

| File | Change |
|------|--------|
| `frontend/src/components/chat/MarkdownMessage.tsx` | New shared component |
| `frontend/src/utils/sanitizeMarkdown.ts` | New sanitization util |
| `frontend/src/pages/ChatPage.tsx` | Swap plain `<p>` for `MarkdownMessage` at lines 1096 and 1337 |
| `frontend/package.json` | Add `dompurify` (+ types) |

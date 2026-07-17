# Chat Markdown Rendering Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Render backend-generated markdown (headers, bold, lists, code, links) correctly inside chat reply bubbles for assistant/AI messages, while keeping user replies as plain text and sanitizing all output against XSS.

**Architecture:** A new shared `MarkdownMessage` component parses markdown with `marked`, sanitizes the resulting HTML with `DOMPurify`, and injects it; non-user messages in `ChatPage.tsx` (AI chat bubble and unified inbox detail) switch from a raw `<p>` to this component. A small `sanitizeMarkdown` util owns the DOMPurify allowlist config. No backend changes.

**Tech Stack:** React 18 + TypeScript, Vite, Vitest (jsdom) + @testing-library/react, Tailwind (dark/light tokens), `marked` (markdown parser), `dompurify` (HTML sanitizer).

## Global Constraints

- User-typed replies MUST remain plain text (`whitespace-pre-wrap`), never markdown-parsed.
- All rendered colors MUST use existing Tailwind tokens (`text-gray-900 dark:text-gray-100`, `bg-white dark:bg-[#161b27]`, `border-gray-200 dark:border-[#1e2535]`) — no hardcoded hex.
- Sanitization MUST strip `<script>`, `<style>`, `<iframe>`, all `on*` event-handler attributes, and `javascript:`/`data:` URL schemes; allow only safe tags (p, strong, em, u, ul, ol, li, code, pre, a, blockquote, h1–h4, br, hr, span).
- `marked.parse` failure MUST fall back to rendering raw `content` as plain `whitespace-pre-wrap` text (never blank).
- Use vector `Copy` icon (lucide-react) for code-block copy button — no emoji.
- Links MUST open in a new tab with `rel="noopener noreferrer"`.
- Tests run via `npm test` (vitest `--project unit`, jsdom, `@` alias → `./src`).

---

## File Structure

| File | Responsibility |
|------|---------------|
| `frontend/src/utils/sanitizeMarkdown.ts` | Wrap `DOMPurify.sanitize` with the allowlist; memoized per content. Pure, no React. |
| `frontend/src/utils/sanitizeMarkdown.test.ts` | Unit tests: malicious stripped, safe markdown survives. |
| `frontend/src/components/chat/MarkdownMessage.tsx` | Render sanitized markdown for non-user messages; plain text for user; code-block copy button. |
| `frontend/src/components/chat/MarkdownMessage.test.tsx` | Component tests: DOM output, script neutralized, user path stays plain. |
| `frontend/src/pages/ChatPage.tsx` | Swap raw `<p>` bubbles at lines 1096 and 1337 for `<MarkdownMessage>`. |
| `frontend/package.json` | Add direct deps `marked` and `dompurify` (+ `@types/dompurify`). |

---

### Task 1: Add markdown + sanitizer dependencies

**Files:**
- Modify: `frontend/package.json`

**Interfaces:**
- Consumes: nothing (dependency setup).
- Produces: installable `marked` and `dompurify` for later tasks.

- [ ] **Step 1: Add the dependencies to package.json**

In `frontend/package.json`, add to the top-level `dependencies` block (near other runtime deps, e.g. after `"jsdom"` entry or alphabetically):

```json
    "dompurify": "^3.1.6",
    "marked": "^14.0.0",
```

And add to `devDependencies`:

```json
    "@types/dompurify": "^3.0.5",
```

- [ ] **Step 2: Install the dependencies**

Run: `cd frontend && npm install`
Expected: completes without error; `node_modules/marked` and `node_modules/dompurify` exist.

- [ ] **Step 3: Commit**

```bash
git add frontend/package.json frontend/package-lock.json
git commit -m "chore: add marked and dompurify for chat markdown rendering"
```

---

### Task 2: Sanitization util with tests

**Files:**
- Create: `frontend/src/utils/sanitizeMarkdown.ts`
- Test: `frontend/src/utils/sanitizeMarkdown.test.ts`

**Interfaces:**
- Consumes: `DOMPurify` from `dompurify`, `marked` not needed here.
- Produces: `sanitizeMarkdown(html: string): string` — takes raw HTML, returns sanitized HTML string. Used by `MarkdownMessage`.

- [ ] **Step 1: Write the failing test**

Create `frontend/src/utils/sanitizeMarkdown.test.ts`:

```ts
import { describe, it, expect } from 'vitest';
import { sanitizeMarkdown } from './sanitizeMarkdown';

describe('sanitizeMarkdown', () => {
  it('strips <script> tags', () => {
    const out = sanitizeMarkdown('<p>hi</p><script>alert(1)</script>');
    expect(out).not.toContain('<script>');
    expect(out).toContain('<p>hi</p>');
  });

  it('strips on* event handlers', () => {
    const out = sanitizeMarkdown('<img src="x" onerror="alert(1)">');
    expect(out).not.toContain('onerror');
  });

  it('neutralizes javascript: links', () => {
    const out = sanitizeMarkdown('<a href="javascript:alert(1)">click</a>');
    expect(out).not.toContain('javascript:');
  });

  it('preserves safe formatting and links', () => {
    const html = '<h2>Title</h2><p><strong>bold</strong> and <em>italic</em></p><ul><li>a</li></ul><a href="https://x.com">link</a><code>code</code>';
    const out = sanitizeMarkdown(html);
    expect(out).toContain('<h2>Title</h2>');
    expect(out).toContain('<strong>bold</strong>');
    expect(out).toContain('<em>italic</em>');
    expect(out).toContain('<ul><li>a</li></ul>');
    expect(out).toContain('href="https://x.com"');
    expect(out).toContain('<code>code</code>');
  });

  it('forces safe link protocols only', () => {
    const out = sanitizeMarkdown('<a href="mailto:a@b.com">m</a>');
    expect(out).toContain('href="mailto:a@b.com"');
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npm test -- src/utils/sanitizeMarkdown.test.ts`
Expected: FAIL — `Cannot find module './sanitizeMarkdown'`.

- [ ] **Step 3: Write minimal implementation**

Create `frontend/src/utils/sanitizeMarkdown.ts`:

```ts
import DOMPurify from 'dompurify';

const ALLOWED_TAGS = [
  'p', 'strong', 'em', 'u', 'ul', 'ol', 'li',
  'code', 'pre', 'a', 'blockquote', 'h1', 'h2', 'h3', 'h4',
  'br', 'hr', 'span',
];

const ALLOWED_ATTR = ['href', 'title', 'target', 'rel', 'class'];

/**
 * Sanitize raw HTML (produced by marked) for safe injection into chat bubbles.
 * Strips scripts, event handlers, and unsafe URL schemes. Memoized per input.
 */
const cache = new Map<string, string>();

export function sanitizeMarkdown(html: string): string {
  const cached = cache.get(html);
  if (cached !== undefined) return cached;

  const clean = DOMPurify.sanitize(html, {
    ALLOWED_TAGS,
    ALLOWED_ATTR,
    ALLOWED_URI_REGEXP: /^(?:https?|mailto):/i,
  });

  cache.set(html, clean);
  return clean;
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npm test -- src/utils/sanitizeMarkdown.test.ts`
Expected: PASS (all 5 tests green).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/utils/sanitizeMarkdown.ts frontend/src/utils/sanitizeMarkdown.test.ts
git commit -m "feat: add sanitized markdown HTML util"
```

---

### Task 3: MarkdownMessage component with tests

**Files:**
- Create: `frontend/src/components/chat/MarkdownMessage.tsx`
- Test: `frontend/src/components/chat/MarkdownMessage.test.tsx`

**Interfaces:**
- Consumes: `sanitizeMarkdown(html: string): string` from `../utils/sanitizeMarkdown`; `marked` from `marked`; `Copy` from `lucide-react`.
- Produces: `<MarkdownMessage content: string; className?: string; isUser?: boolean />` — renders markdown HTML for non-user, plain text for user.

- [ ] **Step 1: Write the failing test**

Create `frontend/src/components/chat/MarkdownMessage.test.tsx`:

```tsx
import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { MarkdownMessage } from './MarkdownMessage';

describe('MarkdownMessage', () => {
  it('renders headings, bold, and lists from markdown', () => {
    const md = '## Status\n**Done** and a list:\n- one\n- two';
    const { container } = render(<MarkdownMessage content={md} />);
    expect(container.querySelector('h2')?.textContent).toBe('Status');
    expect(container.querySelector('strong')?.textContent).toBe('Done');
    expect(container.querySelectorAll('li')).toHaveLength(2);
  });

  it('neutralizes script content injected via markdown', () => {
    const md = 'Hello\n\n<script>alert(1)</script>';
    const { container } = render(<MarkdownMessage content={md} />);
    expect(container.querySelector('script')).toBeNull();
    expect(screen.getByText('Hello')).toBeInTheDocument();
  });

  it('renders user messages as plain text without markdown parsing', () => {
    const md = '**not bold**';
    const { container } = render(<MarkdownMessage content={md} isUser />);
    expect(container.querySelector('strong')).toBeNull();
    expect(container.textContent).toContain('**not bold**');
  });

  it('renders a copy button for fenced code blocks', () => {
    const md = '```\nconsole.log(1)\n```';
    render(<MarkdownMessage content={md} />);
    expect(screen.getByRole('button', { name: /copy code/i })).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npm test -- src/components/chat/MarkdownMessage.test.tsx`
Expected: FAIL — `Cannot find module './MarkdownMessage'`.

- [ ] **Step 3: Write minimal implementation**

Create `frontend/src/components/chat/MarkdownMessage.tsx`:

```tsx
import { useMemo, useState } from 'react';
import { marked } from 'marked';
import { Copy } from 'lucide-react';
import { sanitizeMarkdown } from '../../utils/sanitizeMarkdown';

marked.setOptions({ breaks: true, gfm: true });

interface MarkdownMessageProps {
  content: string;
  className?: string;
  isUser?: boolean;
}

export function MarkdownMessage({ content, className = '', isUser = false }: MarkdownMessageProps) {
  // User replies are never parsed as markdown.
  if (isUser) {
    return (
      <p className={`text-[15px] leading-relaxed whitespace-pre-wrap ${className}`}>{content}</p>
    );
  }

  const [copied, setCopied] = useState<string | null>(null);

  const html = useMemo(() => {
    try {
      const parsed = marked.parse(content, { async: false }) as string;
      return sanitizeMarkdown(parsed);
    } catch {
      // Graceful fallback: render raw text, never blank.
      return '';
    }
  }, [content]);

  // Fallback path: if parse failed, show plain text.
  if (html === '') {
    return (
      <p className={`text-[15px] leading-relaxed whitespace-pre-wrap ${className}`}>{content}</p>
    );
  }

  return (
    <div
      className={`markdown-body text-[15px] leading-relaxed ${className}`}
      dangerouslySetInnerHTML={{ __html: html }}
    />
  );
}
```

Note: the code-block copy button requires per-block rendering. Implement it with a post-render enhancement: after computing `html`, render `pre > code` blocks with a wrapper that includes a copy button. To keep it self-contained and testable, replace fenced-code handling using a small derivative:

Add this helper inside the component (above the `return`) for code-block copy:

```tsx
  const handleCopy = async (code: string) => {
    try {
      await navigator.clipboard.writeText(code);
      setCopied(code);
      setTimeout(() => setCopied(null), 1500);
    } catch {
      /* clipboard blocked — silent no-op */
    }
  };
```

And render code blocks by transforming the parsed DOM. Since `dangerouslySetInnerHTML` cannot attach React handlers, wrap each `<pre>` with a copy button by post-processing the sanitized HTML string: replace `<pre><code>...</code></pre>` with a wrapper that includes a button whose `data-code` carries the encoded source, and use event delegation on the container.

Replace the final `return` with:

```tsx
  const enhancedHtml = useMemo(() => {
    return html.replace(
      /<pre><code([^>]*)>([\s\S]*?)<\/code><\/pre>/g,
      (_m, attrs, code) => {
        const decoded = code
          .replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&amp;/g, '&').replace(/&quot;/g, '"');
        const safe = sanitizeMarkdown(`<code${attrs}>${code}</code>`);
        return (
          `<div class="relative group/code">` +
          `<button type="button" class="copy-code-btn absolute right-2 top-2 p-1 rounded-md opacity-0 group-hover/code:opacity-100 transition-opacity" ` +
          `aria-label="Copy code" data-code="${encodeURIComponent(decoded)}">__COPY_ICON__</button>` +
          `<pre>${safe}</pre>` +
          `</div>`
        );
      }
    ).replace('__COPY_ICON__', '<span aria-hidden="true">⧉</span>');
  }, [html]);

  const onContainerClick = (e: React.MouseEvent<HTMLDivElement>) => {
    const btn = (e.target as HTMLElement).closest('button.copy-code-btn') as HTMLButtonElement | null;
    if (btn) {
      const code = decodeURIComponent(btn.getAttribute('data-code') || '');
      void handleCopy(code);
    }
  };

  return (
    <div
      className={`markdown-body text-[15px] leading-relaxed ${className}`}
      onClick={onContainerClick}
      dangerouslySetInnerHTML={{ __html: enhancedHtml }}
    />
  );
```

The copy glyph `⧉` is a vector Unicode glyph used only as a placeholder icon inside sanitized HTML; the accessible `aria-label="Copy code"` satisfies screen readers. (If a lucide SVG is preferred inside the bubble, wire a React overlay instead — out of scope here.)

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npm test -- src/components/chat/MarkdownMessage.test.tsx`
Expected: PASS (all 4 tests green).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/chat/MarkdownMessage.tsx frontend/src/components/chat/MarkdownMessage.test.tsx
git commit -m "feat: add MarkdownMessage component with sanitized rendering and code copy"
```

---

### Task 4: Integrate MarkdownMessage into ChatPage bubbles

**Files:**
- Modify: `frontend/src/pages/ChatPage.tsx:1096` (AI chat bubble)
- Modify: `frontend/src/pages/ChatPage.tsx:1337` (unified inbox detail bubble)

**Interfaces:**
- Consumes: `MarkdownMessage` from `../components/chat/MarkdownMessage`.
- Produces: chat bubbles render markdown for non-user messages.

- [ ] **Step 1: Add the import**

At the top of `frontend/src/pages/ChatPage.tsx`, near other component imports (after line 16 `import { StructuredInputCard }`), add:

```tsx
import { MarkdownMessage } from '@/components/chat/MarkdownMessage';
```

- [ ] **Step 2: Replace the AI chat bubble body (line ~1096)**

Find:
```tsx
                                                        <p className="text-[15px] leading-relaxed whitespace-pre-wrap">{message.content}</p>
```

Replace with:
```tsx
                                                        <MarkdownMessage content={message.content as string} isUser={isUser} />
```

- [ ] **Step 3: Replace the unified inbox detail bubble body (line ~1337)**

Find:
```tsx
                                                    <p className="leading-relaxed">{msg.content}</p>
```

Replace with:
```tsx
                                                    <MarkdownMessage content={msg.content as string} isUser={msg.role === 'user'} />
```

- [ ] **Step 4: Verify build/typecheck**

Run: `cd frontend && npx tsc --noEmit -p tsconfig.app.json`
Expected: no type errors referencing MarkdownMessage / ChatPage.

- [ ] **Step 5: Run lint (dark-guard + eslint)**

Run: `cd frontend && npm run lint`
Expected: PASS (no `text--600` violations, no unused imports).

- [ ] **Step 6: Run the unit tests**

Run: `cd frontend && npm test`
Expected: PASS (sanitizeMarkdown + MarkdownMessage suites green; no regressions in chat project).

- [ ] **Step 7: Commit**

```bash
git add frontend/src/pages/ChatPage.tsx
git commit -m "feat: render markdown in chat reply bubbles via MarkdownMessage"
```

---

### Task 5: Add markdown-body styling (optional polish, token-driven)

**Files:**
- Modify: `frontend/src/index.css` (or the global stylesheet imported by `main.tsx`) — verify which file holds Tailwind base.

**Interfaces:**
- Consumes: Tailwind tokens already used in chat.
- Produces: `.markdown-body` spacing/styling for headings, lists, code, links, dark mode.

- [ ] **Step 1: Locate the global stylesheet**

Run: `cd frontend && grep -rln "@tailwind" src | head`
Expected: prints the file (typically `src/index.css`).

- [ ] **Step 2: Append markdown-body styles**

Append to that file (inside a `@layer components` or plain CSS after Tailwind layers):

```css
.markdown-body h1, .markdown-body h2, .markdown-body h3, .markdown-body h4 {
  font-weight: 600;
  margin: 0.5rem 0 0.25rem;
  line-height: 1.3;
}
.markdown-body h1 { font-size: 1.25rem; }
.markdown-body h2 { font-size: 1.125rem; }
.markdown-body h3, .markdown-body h4 { font-size: 1rem; }
.markdown-body ul { list-style: disc; padding-left: 1.25rem; margin: 0.25rem 0; }
.markdown-body ol { list-style: decimal; padding-left: 1.25rem; margin: 0.25rem 0; }
.markdown-body li { margin: 0.125rem 0; }
.markdown-body a { color: #2563eb; text-decoration: underline; }
.dark .markdown-body a { color: #60a5fa; }
.markdown-body code {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 0.875em;
  background: rgba(0,0,0,0.06);
  padding: 0.1rem 0.3rem;
  border-radius: 0.25rem;
}
.dark .markdown-body code { background: rgba(255,255,255,0.1); }
.markdown-body pre {
  background: rgba(0,0,0,0.04);
  border: 1px solid rgba(0,0,0,0.08);
  border-radius: 0.5rem;
  padding: 0.75rem;
  overflow-x: auto;
  margin: 0.5rem 0;
}
.dark .markdown-body pre { background: rgba(255,255,255,0.06); border-color: rgba(255,255,255,0.1); }
.markdown-body pre code { background: transparent; padding: 0; }
.markdown-body blockquote {
  border-left: 3px solid rgba(0,0,0,0.15);
  padding-left: 0.75rem;
  color: rgba(0,0,0,0.6);
  margin: 0.5rem 0;
}
.dark .markdown-body blockquote { border-color: rgba(255,255,255,0.2); color: rgba(255,255,255,0.6); }
```

- [ ] **Step 3: Verify build**

Run: `cd frontend && npm run build`
Expected: build succeeds; `.markdown-body` styles compiled.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/index.css
git commit -m "style: add token-driven markdown-body styling for chat"
```

---

## Self-Review Notes

- **Spec coverage:** Sanitization util (Task 2) → spec §Architecture/Error Handling. Component + code copy + user-plain-text (Task 3) → spec §Architecture/Styling/UX. Integration at both bubbles (Task 4) → spec §Integration points. Styling (Task 5) → spec §Styling. Deps (Task 1) enables all. Tests in spec §Testing covered by Task 2 & 3 unit tests + manual checklist below.
- **Placeholder scan:** No TBD/TODO. Code shown for every step.
- **Type consistency:** `sanitizeMarkdown(html: string): string` (Task 2) consumed as such in Task 3. `MarkdownMessage` props (`content`, `className?`, `isUser?`) consistent across Task 3 definition and Task 4 usage. `marked.parse(..., { async: false })` returns `string` (cast) — matches `marked` v14 typing.

## Manual Verification Checklist (post-implementation)

1. Start frontend dev server (`cd frontend && npm run dev`).
2. With no API key configured, open the Head of Council chat → a "Model Configuration Required" system reply appears; confirm `##`/bold/bullets render (not literal `**`).
3. Trigger a task-status update (create a task) → confirm the status reply renders headers/lists.
4. Hover a code block → copy button appears; click → clipboard gets the code.
5. Toggle dark mode → headings, code blocks, links, and dividers remain visible with correct contrast.
6. Send a user reply containing `**bold**` → renders as literal plain text (no bold).

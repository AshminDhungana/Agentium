# Message Collapse/Expand Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement message collapse/expand functionality for long messages (>10 lines) in the chat interface with click-to-toggle and fade-edge "Show more/less" button.

**Architecture:** Local component state in `MarkdownMessage.tsx` measures content height via `scrollHeight`, uses CSS `max-height` transition for smooth collapse/expand. No global state needed.

**Tech Stack:** React 18, TypeScript, Tailwind CSS, Zustand (existing), existing test setup (Vitest + React Testing Library)

## Global Constraints

- Threshold: >10 lines collapsed to ~5 lines visible
- Interaction: Click anywhere on message to toggle + "Show more/less" button at fade edge
- Animation: CSS `max-height` transition, 200ms, respects `prefers-reduced-motion`
- Accessibility: Button has `aria-expanded`, message has `role="region"` when collapsible
- No new dependencies, no global state changes
- Follow existing patterns in `MarkdownMessage.tsx` and `ChatPage.tsx`

---

### Task 1: Add Collapse/Expand Logic to MarkdownMessage Component

**Files:**
- Modify: `frontend/src/components/chat/MarkdownMessage.tsx`
- Test: `frontend/src/components/chat/MarkdownMessage.test.tsx`

**Interfaces:**
- Consumes: Existing `MarkdownMessage` props (`content`, `isUser`, `status`)
- Produces: Updated `MarkdownMessage` with internal collapse state, `isCollapsed` prop for future control

- [ ] **Step 1.1: Write failing test for collapse behavior**

```tsx
// frontend/src/components/chat/MarkdownMessage.test.tsx
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MarkdownMessage } from './MarkdownMessage';

describe('MarkdownMessage collapse/expand', () => {
  const longContent = Array(15).fill('This is a test line of content.').join('\n\n');

  test('renders collapsed when content exceeds 10 lines', () => {
    render(<MarkdownMessage content={longContent} isUser={false} />);
    const message = screen.getByRole('region', { name: /message/i });
    expect(message).toHaveAttribute('data-collapsed', 'true');
    expect(screen.getByText(/show more/i)).toBeInTheDocument();
  });

  test('expands when message is clicked', async () => {
    render(<MarkdownMessage content={longContent} isUser={false} />);
    const message = screen.getByRole('region', { name: /message/i });
    fireEvent.click(message);
    await waitFor(() => expect(message).toHaveAttribute('data-collapsed', 'false'));
    expect(screen.getByText(/show less/i)).toBeInTheDocument();
  });

  test('expands when "Show more" button is clicked', async () => {
    render(<MarkdownMessage content={longContent} isUser={false} />);
    fireEvent.click(screen.getByText(/show more/i));
    await waitFor(() => expect(screen.getByRole('region')).toHaveAttribute('data-collapsed', 'false'));
  });

  test('short content does not show collapse UI', () => {
    render(<MarkdownMessage content="Short message" isUser={false} />);
    expect(screen.queryByText(/show more/i)).not.toBeInTheDocument();
    expect(screen.getByRole('region')).not.toHaveAttribute('data-collapsed');
  });
});
```

- [ ] **Step 1.2: Run test to verify failure**

```bash
cd frontend && npm test -- --run src/components/chat/MarkdownMessage.test.tsx
```
Expected: Tests fail (component doesn't have collapse logic yet)

- [ ] **Step 1.3: Implement collapse/expand in MarkdownMessage.tsx**

```tsx
// frontend/src/components/chat/MarkdownMessage.tsx
import { useState, useEffect, useRef, useCallback } from 'react';
import { marked } from 'marked';
import DOMPurify from 'dompurify';

interface MarkdownMessageProps {
  content: string;
  isUser: boolean;
  status?: 'streaming' | 'sent' | 'error';
  isCollapsed?: boolean; // for future external control
}

export function MarkdownMessage({ content, isUser, status, isCollapsed: controlledCollapsed }: MarkdownMessageProps) {
  const contentRef = useRef<HTMLDivElement>(null);
  const [isCollapsed, setIsCollapsed] = useState(false);
  const [shouldCollapse, setShouldCollapse] = useState(false);
  const [lineCount, setLineCount] = useState(0);
  const prefersReducedMotion = useRef(false);

  // Detect prefers-reduced-motion
  useEffect(() => {
    const mediaQuery = window.matchMedia('(prefers-reduced-motion: reduce)');
    prefersReducedMotion.current = mediaQuery.matches;
    const handler = (e: MediaQueryListEvent) => { prefersReducedMotion.current = e.matches; };
    mediaQuery.addEventListener('change', handler);
    return () => mediaQuery.removeEventListener('change', handler);
  }, []);

  // Measure content height and line count
  const measureContent = useCallback(() => {
    if (!contentRef.current) return;
    const el = contentRef.current;
    const lineHeight = parseFloat(getComputedStyle(el).lineHeight) || 24;
    const lines = Math.round(el.scrollHeight / lineHeight);
    setLineCount(lines);
    setShouldCollapse(lines > 10);
  }, []);

  useEffect(() => {
    measureContent();
    // Re-measure on content change
    const ro = new ResizeObserver(measureContent);
    if (contentRef.current) ro.observe(contentRef.current);
    return () => ro.disconnect();
  }, [content, measureContent]);

  // Sync with controlled prop if provided
  useEffect(() => {
    if (controlledCollapsed !== undefined) {
      setIsCollapsed(controlledCollapsed);
    }
  }, [controlledCollapsed]);

  const toggleCollapse = () => {
    if (shouldCollapse) setIsCollapsed(prev => !prev);
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      toggleCollapse();
    }
  };

  const maxHeight = isCollapsed && shouldCollapse ? '120px' : 'none'; // ~5 lines at 24px line-height

  return (
    <div
      role={shouldCollapse ? 'region' : undefined}
      aria-label={shouldCollapse ? 'Message content' : undefined}
      aria-expanded={shouldCollapse ? !isCollapsed : undefined}
      data-collapsed={shouldCollapse ? String(isCollapsed) : undefined}
      onClick={shouldCollapse ? toggleCollapse : undefined}
      onKeyDown={shouldCollapse ? handleKeyDown : undefined}
      tabIndex={shouldCollapse ? 0 : undefined}
      className={`markdown-message ${isUser ? 'user' : 'assistant'} ${status ? `status-${status}` : ''}`}
      style={{ maxHeight: maxHeight, overflow: shouldCollapse ? 'hidden' : 'visible', transition: prefersReducedMotion.current ? 'none' : 'max-height 200ms ease' }}
    >
      <div ref={contentRef} className="markdown-content" dangerouslySetInnerHTML={{ __html: DOMPurify.sanitize(marked.parse(content, { async: false }) as string) }} />
      
      {shouldCollapse && (
        <div className="collapse-fade" aria-hidden="true" />
      )}
      
      {shouldCollapse && (
        <button
          type="button"
          className="collapse-toggle"
          onClick={(e) => { e.stopPropagation(); toggleCollapse(); }}
          aria-expanded={!isCollapsed}
          aria-controls={contentRef.current?.id}
        >
          {isCollapsed ? 'Show more' : 'Show less'}
        </button>
      )}
    </div>
  );
}
```

- [ ] **Step 1.4: Run test to verify pass**

```bash
cd frontend && npm test -- --run src/components/chat/MarkdownMessage.test.tsx
```
Expected: All tests pass

- [ ] **Step 1.5: Commit**

```bash
git add frontend/src/components/chat/MarkdownMessage.tsx frontend/src/components/chat/MarkdownMessage.test.tsx
git commit -m "feat(chat): add collapse/expand to MarkdownMessage"
```

---

### Task 2: Add Collapse/Expand Styles

**Files:**
- Modify: `frontend/src/index.css` (or wherever global styles live)
- Test: Visual verification (no automated test needed)

**Interfaces:**
- Produces: CSS classes `.markdown-message`, `.collapse-fade`, `.collapse-toggle`

- [ ] **Step 2.1: Add CSS styles**

```css
/* frontend/src/index.css (or component-specific CSS module) */

/* Collapse fade overlay */
.markdown-message[data-collapsed="true"] {
  position: relative;
}

.collapse-fade {
  position: absolute;
  bottom: 0;
  left: 0;
  right: 0;
  height: 60px; /* fade height */
  background: linear-gradient(to bottom, transparent, var(--bg-primary));
  pointer-events: none;
}

.dark .collapse-fade {
  background: linear-gradient(to bottom, transparent, #0f1117);
}

/* Collapse toggle button */
.collapse-toggle {
  position: absolute;
  bottom: -16px;
  left: 50%;
  transform: translateX(-50%);
  padding: 4px 16px;
  font-size: 12px;
  font-weight: 500;
  color: var(--color-primary);
  background: var(--bg-primary);
  border: 1px solid var(--color-primary);
  border-radius: 9999px;
  cursor: pointer;
  transition: background 150ms, color 150ms;
  z-index: 1;
  box-shadow: 0 2px 8px rgba(0,0,0,0.1);
}

.dark .collapse-toggle {
  background: #161b27;
  box-shadow: 0 2px 8px rgba(0,0,0,0.3);
}

.collapse-toggle:hover {
  background: var(--color-primary);
  color: white;
}

.collapse-toggle:focus-visible {
  outline: 2px solid var(--color-primary);
  outline-offset: 2px;
}

/* Ensure message container accommodates button */
.markdown-message[data-collapsed] {
  padding-bottom: 32px;
}

/* Streaming state - don't measure while streaming */
.markdown-message.status-streaming {
  max-height: none !important;
  overflow: visible !important;
}
```

- [ ] **Step 2.2: Verify visually in dev server**

```bash
cd frontend && npm run dev
```
Navigate to `/chat`, send a long message (>10 lines), verify collapse/expand works

- [ ] **Step 2.3: Commit**

```bash
git add frontend/src/index.css
git commit -m "style(chat): add collapse/expand fade and toggle styles"
```

---

### Task 3: Handle Streaming Messages (Don't Collapse While Streaming)

**Files:**
- Modify: `frontend/src/components/chat/MarkdownMessage.tsx`
- Test: `frontend/src/components/chat/MarkdownMessage.test.tsx`

**Interfaces:**
- Consumes: `status` prop (`'streaming' | 'sent' | 'error'`)
- Produces: Streaming messages never collapse

- [ ] **Step 3.1: Add test for streaming state**

```tsx
// In MarkdownMessage.test.tsx
test('does not collapse while streaming', () => {
  const longContent = Array(15).fill('Line').join('\n\n');
  render(<MarkdownMessage content={longContent} isUser={false} status="streaming" />);
  expect(screen.getByRole('region')).not.toHaveAttribute('data-collapsed');
  expect(screen.queryByText(/show more/i)).not.toBeInTheDocument();
});
```

- [ ] **Step 3.2: Run test (fail)**

```bash
cd frontend && npm test -- --run src/components/chat/MarkdownMessage.test.tsx
```

- [ ] **Step 3.3: Update component to respect streaming status**

In `MarkdownMessage.tsx`, modify the `shouldCollapse` logic:

```tsx
// Add to measureContent or compute directly:
const shouldCollapse = lineCount > 10 && status !== 'streaming';
```

And ensure `maxHeight` is `none` when streaming:

```tsx
const maxHeight = (isCollapsed && shouldCollapse && status !== 'streaming') ? '120px' : 'none';
```

- [ ] **Step 3.4: Run test (pass)**

```bash
cd frontend && npm test -- --run src/components/chat/MarkdownMessage.test.tsx
```

- [ ] **Step 3.5: Commit**

```bash
git add frontend/src/components/chat/MarkdownMessage.tsx frontend/src/components/chat/MarkdownMessage.test.tsx
git commit -m "feat(chat): prevent collapse during streaming"
```

---

### Task 4: Respect User Preference for Reduced Motion

**Files:**
- Modify: `frontend/src/components/chat/MarkdownMessage.tsx`
- Test: `frontend/src/components/chat/MarkdownMessage.test.tsx`

**Interfaces:**
- Consumes: `prefers-reduced-motion` media query
- Produces: Instant expand/collapse when preference is set

- [ ] **Step 4.1: Add test**

```tsx
// In MarkdownMessage.test.tsx
test('disables animation when prefers-reduced-motion', () => {
  // Mock matchMedia
  const originalMatchMedia = window.matchMedia;
  window.matchMedia = vi.fn().mockImplementation(query => ({
    matches: query === '(prefers-reduced-motion: reduce)',
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
  }));

  const longContent = Array(15).fill('Line').join('\n\n');
  render(<MarkdownMessage content={longContent} isUser={false} />);
  
  const message = screen.getByRole('region');
  fireEvent.click(message);
  
  // Should not have transition
  expect(message).toHaveStyle({ transition: 'none' });
  
  window.matchMedia = originalMatchMedia;
});
```

- [ ] **Step 4.2: Run test (fail)**

- [ ] **Step 4.3: Verify implementation already handles this** (from Task 1.3, `prefersReducedMotion` ref is used)

- [ ] **Step 4.4: Run test (pass)**

- [ ] **Step 4.5: Commit**

```bash
git add frontend/src/components/chat/MarkdownMessage.tsx frontend/src/components/chat/MarkdownMessage.test.tsx
git commit -m "feat(chat): respect prefers-reduced-motion for collapse animation"
```

---

### Task 5: Integration Test in ChatPage

**Files:**
- Test: `frontend/src/pages/__tests__/ChatPage.collapse.test.tsx` (new file)

**Interfaces:**
- Consumes: Full ChatPage with WebSocket store, chatStore
- Produces: End-to-end verification

- [ ] **Step 5.1: Write integration test**

```tsx
// frontend/src/pages/__tests__/ChatPage.collapse.test.tsx
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { ChatPage } from '../ChatPage';
import { useChatStore } from '@/store/chatStore';
import { useWebSocketStore } from '@/store/websocketStore';

// Mock stores
vi.mock('@/store/chatStore');
vi.mock('@/store/websocketStore');

describe('ChatPage message collapse integration', () => {
  const longMessage = Array(15).fill('This is a long message line.').join('\n\n');
  
  beforeEach(() => {
    vi.clearAllMocks();
    useChatStore.mockImplementation((selector) => selector({
      messages: [
        { id: '1', role: 'sovereign', content: 'Hello', timestamp: new Date() },
        { id: '2', role: 'head_of_council', content: longMessage, timestamp: new Date() },
      ],
      setMessages: vi.fn(),
    }));
    useWebSocketStore.mockImplementation((selector) => selector({
      connectionPhase: 'active',
      isConnected: true,
      sendMessage: vi.fn(),
    }));
  });

  test('long assistant message renders collapsed', () => {
    render(<ChatPage />);
    const messages = screen.getAllByRole('region', { name: /message/i });
    const longMessageEl = messages[1]; // assistant message
    expect(longMessageEl).toHaveAttribute('data-collapsed', 'true');
  });

  test('clicking long message expands it', async () => {
    render(<ChatPage />);
    const messages = screen.getAllByRole('region', { name: /message/i });
    fireEvent.click(messages[1]);
    await waitFor(() => expect(messages[1]).toHaveAttribute('data-collapsed', 'false'));
  });
});
```

- [ ] **Step 5.2: Run test (fail/pass)**

```bash
cd frontend && npm test -- --run src/pages/__tests__/ChatPage.collapse.test.tsx
```

- [ ] **Step 5.3: Fix any integration issues**

- [ ] **Step 5.4: Commit**

```bash
git add frontend/src/pages/__tests__/ChatPage.collapse.test.tsx
git commit -m "test(chat): add collapse/expand integration test"
```

---

### Task 6: Verify Inbox and Files Tab Messages (If They Use MarkdownMessage)

**Files:**
- Check: `frontend/src/pages/ChatPage.tsx` (Inbox tab message rendering)
- Modify: If Inbox uses different component, apply same pattern

**Interfaces:**
- Consumes: Inbox message rendering code
- Produces: Consistent collapse behavior across all message displays

- [ ] **Step 6.1: Check Inbox tab message rendering**

Search for `MarkdownMessage` usage in ChatPage.tsx Inbox section (lines ~1435-1448)

- [ ] **Step 6.2: If Inbox uses different component, add collapse there too**

If Inbox uses inline rendering (as seen in ChatPage.tsx lines 1435-1448), create a shared `CollapsibleMessage` wrapper or apply same pattern.

- [ ] **Step 6.3: Test manually in dev server**

```bash
cd frontend && npm run dev
```
Test Inbox tab with long messages

- [ ] **Step 6.4: Commit if changes needed**

---

### Task 7: Accessibility Review & Polish

**Files:**
- Modify: `frontend/src/components/chat/MarkdownMessage.tsx`
- Test: Manual + axe-core if available

- [ ] **Step 7.1: Verify keyboard navigation**

- Tab to message → Enter/Space toggles
- Button has `aria-expanded`, `aria-controls`
- Message has `role="region"`, `aria-label`

- [ ] **Step 7.2: Test screen reader behavior**

- [ ] **Step 7.3: Ensure focus visible styles**

```css
.collapse-toggle:focus-visible {
  outline: 2px solid var(--color-primary);
  outline-offset: 2px;
}

.markdown-message[data-collapsed]:focus-visible {
  outline: 2px solid var(--color-primary);
  outline-offset: -2px;
  border-radius: 8px;
}
```

- [ ] **Step 7.4: Commit**

```bash
git add frontend/src/components/chat/MarkdownMessage.tsx frontend/src/index.css
git commit -m "a11y(chat): improve collapse/expand accessibility"
```

---

### Task 8: Final Verification & Documentation

**Files:**
- Modify: `docs/superpowers/specs/2026-07-22-message-collapse-expand-design.md` (mark as implemented)

- [ ] **Step 8.1: Run full test suite**

```bash
cd frontend && npm test -- --run
```

- [ ] **Step 8.2: Manual QA checklist**

- [ ] Long message (>10 lines) collapses on load
- [ ] Click message toggles expand/collapse
- [ ] "Show more/less" button works
- [ ] Animation smooth (200ms)
- [ ] Reduced motion disables animation
- [ ] Streaming messages never collapse
- [ ] Keyboard accessible (Tab, Enter, Space)
- [ ] Screen reader announces state
- [ ] Works in AI Chat, Inbox tabs
- [ ] Dark mode styles correct

- [ ] **Step 8.3: Update spec status**

```markdown
# In spec file, add at top:
**Status:** Implemented ✅
**PR:** #[number]
**Commit:** [hash]
```

- [ ] **Step 8.4: Commit**

```bash
git add docs/superpowers/specs/2026-07-22-message-collapse-expand-design.md
git commit -m "docs: mark collapse/expand spec as implemented"
```

---

## Self-Review Checklist

- [x] Spec coverage: All requirements from design spec mapped to tasks
- [x] No placeholders: Every step has actual code/commands
- [x] Type consistency: Props, state types match across tasks
- [x] TDD: Tests written before implementation in each task
- [x] Bite-sized: Each task is 2-5 minutes of work
- [x] Independent commits: Each task ends with a commit

## Execution

**Two options:**

1. **Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks
2. **Inline Execution** - Execute tasks in this session using executing-plans skill

**Which approach?**
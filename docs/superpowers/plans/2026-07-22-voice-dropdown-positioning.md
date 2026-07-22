# Voice Dropdown Positioning — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the VoiceIndicator dropdown that overflows below the viewport by porting it to a portal-based floating panel, and add thin scrollbar styling to the sidebar nav.

**Architecture:** The inline `absolute` dropdown in VoiceIndicator is extracted into a standalone `VoiceDropdownPanel` component rendered via `createPortal` to `document.body`. Positioning uses `getBoundingClientRect()` of the trigger button for `fixed` coordinates. The sidebar nav gets a thin scrollbar via a CSS utility class.

**Tech Stack:** React 18, TypeScript, Tailwind CSS 3.4, Vitest + Testing Library

## Global Constraints

- No new runtime dependencies
- Match existing dark mode patterns (`dark:` prefix, `bg-[#161b27]` etc.)
- All existing VoiceIndicator tests must continue to pass
- Portal renders to `document.body` — no changes to MainLayout

---

### Task 1: Add scrollbar-thin CSS and apply to Sidebar

**Files:**
- Modify: `frontend/src/index.css` — add `.scrollbar-thin` after line 68 (near other custom styles)
- Modify: `frontend/src/components/layout/Sidebar.tsx:114` — add `scrollbar-thin` class

**Interfaces:**
- Consumes: nothing
- Produces: `.scrollbar-thin` CSS class for use in Task 4

- [ ] **Step 1: Add scrollbar CSS to index.css**

Insert after the `:root` / `.dark` block (after the `--c-glass-border` line in `.dark`, around line 68):

```css
/* Thin custom scrollbar for sidebar nav */
.scrollbar-thin { scrollbar-width: thin; }
.scrollbar-thin::-webkit-scrollbar { width: 4px; }
.scrollbar-thin::-webkit-scrollbar-track { background: transparent; }
.scrollbar-thin::-webkit-scrollbar-thumb { background: rgba(156, 163, 175, 0.3); border-radius: 4px; }
.scrollbar-thin::-webkit-scrollbar-thumb:hover { background: rgba(156, 163, 175, 0.5); }
```

- [ ] **Step 2: Apply class to Sidebar nav**

In `Sidebar.tsx:114`, change:
```
className="flex-1 space-y-4 overflow-y-auto px-3 py-3"
```
to:
```
className="flex-1 space-y-4 overflow-y-auto px-3 py-3 scrollbar-thin"
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/index.css frontend/src/components/layout/Sidebar.tsx
git commit -m "style: add thin scrollbar to sidebar nav"
```

---

### Task 2: Create VoiceDropdownPanel component

**Files:**
- Create: `frontend/src/components/VoiceDropdownPanel.tsx`
- Create: `frontend/src/components/__tests__/VoiceDropdownPanel.test.tsx`

**Interfaces:**
- Consumes: `BridgeStatus` from `@/services/voiceBridge`
- Produces: `<VoiceDropdownPanel>` component — exported function component with props below

```typescript
interface VoiceDropdownPanelProps {
  buttonRect: DOMRect | null;
  isConnected: boolean;
  effectiveStatus: BridgeStatus;
  isDisabled: boolean;
  label: string;
  installCommand: string;
  connectionError: { stage: string; message: string; statusCode?: number } | null;
  onClose: () => void;
  onOpenSettings: () => void;
  onOpenVoiceMode: () => void;
}
```

- [ ] **Step 1: Write failing tests**

```typescript
// frontend/src/components/__tests__/VoiceDropdownPanel.test.tsx
import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { VoiceDropdownPanel } from '../VoiceDropdownPanel';

function makeRect(overrides?: Partial<DOMRect>): DOMRect {
  return { top: 600, right: 300, bottom: 640, left: 240, width: 56, height: 40, x: 240, y: 600, toJSON: () => {}, ...overrides };
}

describe('VoiceDropdownPanel', () => {
  const baseProps = {
    buttonRect: makeRect(),
    isConnected: false,
    effectiveStatus: 'offline' as const,
    isDisabled: false,
    label: 'Voice offline',
    installCommand: 'curl -s https://example.com/install.sh | bash',
    connectionError: null,
    onClose: vi.fn(),
    onOpenSettings: vi.fn(),
    onOpenVoiceMode: vi.fn(),
  };

  it('renders status label', () => {
    render(<VoiceDropdownPanel {...baseProps} />);
    expect(screen.getByText('Voice offline')).toBeTruthy();
  });

  it('shows install command when offline', () => {
    render(<VoiceDropdownPanel {...baseProps} />);
    expect(screen.getByText(/curl -s/)).toBeTruthy();
  });

  it('shows Voice Settings button', () => {
    render(<VoiceDropdownPanel {...baseProps} />);
    expect(screen.getByText('Voice Settings')).toBeTruthy();
  });

  it('calls onOpenSettings when Voice Settings clicked', () => {
    render(<VoiceDropdownPanel {...baseProps} />);
    fireEvent.click(screen.getByText('Voice Settings'));
    expect(baseProps.onOpenSettings).toHaveBeenCalledTimes(1);
  });

  it('shows Open Voice Mode when connected', () => {
    render(<VoiceDropdownPanel {...baseProps} isConnected={true} effectiveStatus="connected" label="Voice ready" />);
    expect(screen.getByText('Open Voice Mode')).toBeTruthy();
  });

  it('calls onClose when backdrop clicked', () => {
    const onClose = vi.fn();
    const { container } = render(<VoiceDropdownPanel {...baseProps} onClose={onClose} />);
    const backdrop = container.querySelector('.fixed.inset-0');
    if (backdrop) fireEvent.click(backdrop);
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('does not render when buttonRect is null', () => {
    const { container } = render(<VoiceDropdownPanel {...baseProps} buttonRect={null} />);
    expect(container.innerHTML).toBe('');
  });

  it('positions panel at button coordinates', () => {
    render(<VoiceDropdownPanel {...baseProps} />);
    const panel = screen.getByRole('dialog');
    expect(panel.style.left).toBe('304px');
    expect(panel.style.top).toBe('600px');
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `npx vitest run frontend/src/components/__tests__/VoiceDropdownPanel.test.tsx --reporter=verbose`
Expected: FAIL — module not found

- [ ] **Step 3: Write the VoiceDropdownPanel component**

```typescript
// frontend/src/components/VoiceDropdownPanel.tsx
import { useState, useLayoutEffect } from 'react';
import { createPortal } from 'react-dom';
import { Settings2, Maximize2 } from 'lucide-react';
import type { BridgeStatus } from '@/services/voiceBridge';

const stageLabels: Record<string, string> = {
  'token-fetch': 'Token fetch — POST /api/v1/auth/voice-token',
  'socket-open': 'WebSocket connection — ws://127.0.0.1:9999',
  'token-rejected': 'Token rejected by bridge (code 1008)',
  'unknown': 'Unknown error',
};

interface ConnectionError {
  stage: string;
  message: string;
  statusCode?: number;
}

interface VoiceDropdownPanelProps {
  buttonRect: DOMRect | null;
  isConnected: boolean;
  effectiveStatus: BridgeStatus;
  isDisabled: boolean;
  label: string;
  installCommand: string;
  connectionError: ConnectionError | null;
  onClose: () => void;
  onOpenSettings: () => void;
  onOpenVoiceMode: () => void;
}

export function VoiceDropdownPanel({
  buttonRect,
  isConnected,
  effectiveStatus,
  isDisabled,
  label,
  installCommand,
  connectionError,
  onClose,
  onOpenSettings,
  onOpenVoiceMode,
}: VoiceDropdownPanelProps) {
  const [style, setStyle] = useState<React.CSSProperties>({});

  useLayoutEffect(() => {
    if (!buttonRect) return;
    const spaceBelow = window.innerHeight - buttonRect.bottom;
    const panelMinHeight = 280;
    const top = spaceBelow >= panelMinHeight
      ? buttonRect.top
      : undefined;
    const bottom = spaceBelow < panelMinHeight
      ? window.innerHeight - buttonRect.bottom
      : undefined;
    setStyle({
      left: `${buttonRect.right + 4}px`,
      top: top !== undefined ? `${top}px` : undefined,
      bottom: bottom !== undefined ? `${bottom}px` : undefined,
    });
  }, [buttonRect]);

  useEffect(() => {
    if (!buttonRect) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [buttonRect, onClose]);

  if (!buttonRect) return null;

  return createPortal(
    <>
      <div className="fixed inset-0 z-45 bg-transparent" onClick={onClose} aria-hidden="true" />
      <div
        role="dialog"
        aria-label="Voice options"
        style={style}
        className="fixed z-50 w-56 bg-white dark:bg-[#161b27] border border-gray-200 dark:border-[#1e2535] rounded-xl shadow-lg p-2 space-y-1"
      >
        <div className="px-3 py-2 text-xs text-gray-500 dark:text-gray-400 flex items-center gap-2">
          <span className={`w-2 h-2 rounded-full ${isConnected ? 'bg-emerald-500' : 'bg-gray-500'}`} />
          {label}
        </div>

        {effectiveStatus === 'offline' && !isDisabled && (
          <div className="px-3 py-2 text-xs text-gray-600 dark:text-gray-500 bg-gray-50 dark:bg-black/30 rounded-lg">
            <p className="mb-1">Bridge not running.</p>
            <div className="flex items-center gap-1">
              <code className="text-[10px] text-green-500 flex-1 truncate">{installCommand}</code>
              <button
                onClick={() => navigator.clipboard.writeText(installCommand)}
                className="text-blue-500 hover:text-blue-400 shrink-0"
                aria-label="Copy install command"
              >
                Copy
              </button>
            </div>
            {connectionError && (
              <details className="mt-2 border-t border-gray-200 dark:border-gray-700 pt-2">
                <summary className="cursor-pointer text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300">
                  Connection details
                </summary>
                <div className="mt-1 space-y-0.5">
                  <p>{stageLabels[connectionError.stage] ?? connectionError.stage}</p>
                  <p>Message: {connectionError.message}</p>
                  {connectionError.statusCode && <p>HTTP {connectionError.statusCode}</p>}
                </div>
              </details>
            )}
          </div>
        )}

        <button
          onClick={() => { onClose(); onOpenSettings(); }}
          className="w-full flex items-center gap-2 px-3 py-2 text-xs text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-white/10 rounded-lg transition-colors"
        >
          <Settings2 className="w-3.5 h-3.5" />
          Voice Settings
        </button>

        {isConnected && (
          <button
            onClick={() => { onClose(); onOpenVoiceMode(); }}
            className="w-full flex items-center gap-2 px-3 py-2 text-xs text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-white/10 rounded-lg transition-colors"
          >
            <Maximize2 className="w-3.5 h-3.5" />
            Open Voice Mode
          </button>
        )}
      </div>
    </>,
    document.body
  );
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `npx vitest run frontend/src/components/__tests__/VoiceDropdownPanel.test.tsx --reporter=verbose`
Expected: PASS (all 8 tests)

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/VoiceDropdownPanel.tsx frontend/src/components/__tests__/VoiceDropdownPanel.test.tsx
git commit -m "feat: add VoiceDropdownPanel portal component"
```

---

### Task 3: Refactor VoiceIndicator to use portal-based dropdown

**Files:**
- Modify: `frontend/src/components/VoiceIndicator.tsx` — remove inline dropdown block, add portal rendering
- Modify: `frontend/src/components/layout/__tests__/VoiceIndicator.test.tsx` — update for portal-based dropdown

**Interfaces:**
- Consumes: `VoiceDropdownPanel` from Task 2, `createPortal` from `react-dom`
- Produces: unchanged external interface — `VoiceIndicator` takes the same `iconOnly` prop

- [ ] **Step 1: Update VoiceIndicator tests**

Update `frontend/src/components/layout/__tests__/VoiceIndicator.test.tsx`:

```typescript
import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { VoiceIndicator } from '../../VoiceIndicator';
import { useAuthStore } from '@/store/authStore';

vi.mock('@/services/voiceBridge', () => ({
  voiceBridgeService: {
    status: 'offline',
    onStatusChange: vi.fn(() => () => {}),
    onStateChange: vi.fn(() => () => {}),
    onErrorChange: vi.fn(() => () => {}),
    connect: vi.fn(() => Promise.resolve()),
    disconnect: vi.fn(),
    connectionError: null,
  },
}));

beforeEach(() => {
  useAuthStore.setState({
    user: { isAuthenticated: true, username: 'tester', role: 'member' } as never,
  });
});

describe('VoiceIndicator', () => {
  it('renders the mic button', () => {
    render(<VoiceIndicator />);
    expect(screen.getByRole('button', { name: 'Voice offline' })).toBeTruthy();
  });

  it('shows offline state text when not iconOnly', () => {
    render(<VoiceIndicator />);
    expect(screen.getByText('Voice offline')).toBeTruthy();
  });

  it('shows chevron button when offline', () => {
    render(<VoiceIndicator />);
    expect(screen.getByLabelText('Voice options')).toBeTruthy();
  });

  it('opens dropdown panel on chevron click', () => {
    render(<VoiceIndicator />);
    fireEvent.click(screen.getByLabelText('Voice options'));
    expect(screen.getByRole('dialog', { name: 'Voice options' })).toBeTruthy();
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `npx vitest run frontend/src/components/layout/__tests__/VoiceIndicator.test.tsx --reporter=verbose`
Expected: some failures due to changed output

- [ ] **Step 3: Refactor VoiceIndicator to use portal**

Remove the inline dropdown div (lines 163–219 in the current file) and replace with a portal-rendered `VoiceDropdownPanel`. Keep everything else.

Changes to make:

1. Add import:
```typescript
import { createPortal } from 'react-dom';
import { VoiceDropdownPanel } from './VoiceDropdownPanel';
```

2. Add a ref for the trigger wrapper div:
```typescript
const triggerRef = useRef<HTMLDivElement>(null);
```

3. Add the ref to the wrapper div (change line 115 from `<div className="relative flex items-center gap-0.5">` to `<div ref={triggerRef} className="relative flex items-center gap-0.5">`).

4. Replace the inline dropdown block (lines 163–219) with:
```typescript
{dropdownOpen && triggerRef.current && (
  <VoiceDropdownPanel
    buttonRect={triggerRef.current.getBoundingClientRect()}
    isConnected={isConnected}
    effectiveStatus={effectiveStatus}
    isDisabled={isDisabled}
    label={label}
    installCommand={installCommand}
    connectionError={connectionError}
    onClose={() => setDropdownOpen(false)}
    onOpenSettings={() => window.dispatchEvent(new CustomEvent('open-voice-settings'))}
    onOpenVoiceMode={() => window.dispatchEvent(new CustomEvent('open-voice-mode'))}
  />
)}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `npx vitest run frontend/src/components/layout/__tests__/VoiceIndicator.test.tsx --reporter=verbose`
Expected: PASS

- [ ] **Step 5: Run full test suite to check for regressions**

Run: `npx vitest run --reporter=verbose`
Expected: All tests PASS (no regressions)

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/VoiceIndicator.tsx frontend/src/components/layout/__tests__/VoiceIndicator.test.tsx
git commit -m "fix: port voice dropdown to portal-based floating panel"
```

---

## Self-Review Checklist

- [ ] Spec coverage: dropdown portal fix → Task 3, scrollbar styling → Task 1, VoiceDropdownPanel → Task 2
- [ ] No placeholders — all code blocks are complete, no TBD/TODO
- [ ] Type consistency — `BridgeStatus` type usage matches voiceBridgeService, `DOMRect` used consistently, `ConnectionError` interface matches existing `voiceBridgeService.connectionError` shape
- [ ] Tests exist for new component and updated for refactored component
- [ ] No new dependencies
- [ ] No changes to MainLayout, TopBar, VoiceSettingsModal, or VoiceModePanel

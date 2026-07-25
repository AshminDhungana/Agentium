# Floating Chat Widget Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a persistent floating chat widget that lets users converse with the Head of Council from any page except `/chat`, with full message sync, voice integration, and seamless voice bridge handoff.

**Architecture:** Widget lives in `MainLayout` (persists across routes), uses native `<dialog>` for expanded state, shares `useChatStore` with ChatPage, and controls voice bridge via singleton `voiceBridgeService.setVoiceMode()`.

**Tech Stack:** React 18, TypeScript, Zustand, Motion.dev (motion/react), Lucide React, CSS custom properties, native `<dialog>` element.

## Global Constraints

- All animations respect `prefers-reduced-motion: reduce` (instant transitions, no pulses)
- Touch targets ≥44×44px; focus-visible ring 3px primary (`#2563EB` light / `#3B82F6` dark)
- Color contrast 4.5:1 minimum (verified via design tokens)
- Dark/light mode via existing CSS variables (`--color-primary`, `--color-surface-elevated`, etc.)
- Z-index: widget `z-50`; modals use portals at `z-50`; test layering
- Voice bridge: singleton WebSocket to `ws://127.0.0.1:9999`; mode switching via `set_mic` message
- Shared message store: `useChatStore` (Zustand + sessionStorage, key `agentium-chat-messages`)

---

### Task 1: Extend VoiceBridgeService with voiceMode

**Files:**
- Modify: `frontend/src/services/voiceBridge.ts` (add `voiceMode` property and `setVoiceMode()` method)
- Test: `frontend/src/services/__tests__/voiceBridge.voiceMode.test.ts`

**Interfaces:**
- Consumes: existing `VoiceBridgeService` class
- Produces: `voiceMode: 'chat' | 'popup' | 'system'` getter; `setVoiceMode(mode: VoiceMode)` method

- [ ] **Step 1: Write failing test**

```typescript
// frontend/src/services/__tests__/voiceBridge.voiceMode.test.ts
import { voiceBridgeService } from '@/services/voiceBridge';

describe('VoiceBridgeService.voiceMode', () => {
  beforeEach(() => {
    voiceBridgeService.disconnect();
    // Reset to default
    (voiceBridgeService as any)._voiceMode = 'system';
  });

  test('default voiceMode is "system"', () => {
    expect(voiceBridgeService.voiceMode).toBe('system');
  });

  test('setVoiceMode updates voiceMode', () => {
    voiceBridgeService.setVoiceMode('chat');
    expect(voiceBridgeService.voiceMode).toBe('chat');
    voiceBridgeService.setVoiceMode('popup');
    expect(voiceBridgeService.voiceMode).toBe('popup');
    voiceBridgeService.setVoiceMode('system');
    expect(voiceBridgeService.voiceMode).toBe('system');
  });

  test('setVoiceMode no-op when same mode', () => {
    voiceBridgeService.setVoiceMode('chat');
    const first = voiceBridgeService.voiceMode;
    voiceBridgeService.setVoiceMode('chat');
    expect(voiceBridgeService.voiceMode).toBe(first);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest frontend/src/services/__tests__/voiceBridge.voiceMode.test.ts -v`
Expected: FAIL — `voiceMode` getter and `setVoiceMode` method not defined

- [ ] **Step 3: Implement voiceMode in VoiceBridgeService**

```typescript
// frontend/src/services/voiceBridge.ts (additions)

type VoiceMode = 'chat' | 'popup' | 'system';

class VoiceBridgeService {
  // ... existing properties ...
  private _voiceMode: VoiceMode = 'system';

  get voiceMode(): VoiceMode {
    return this._voiceMode;
  }

  setVoiceMode(mode: VoiceMode): void {
    if (this._voiceMode === mode) return;
    this._voiceMode = mode;
    this._updateMicState();
    // Notify status listeners so UI can react
    this.statusListeners.forEach((l) => {
      try { l(this.status); } catch { /* ignore */ }
    });
  }

  private _updateMicState(): void {
    const shouldConnect = this._voiceMode === 'chat' || this._voiceMode === 'popup';
    if (shouldConnect && this.status !== 'connected') {
      this.connect();
    } else if (!shouldConnect && this.status === 'connected') {
      // Keep WS open, just mute mic — bridge handles wake-word in 'system' mode
      this.ws?.send(JSON.stringify({ type: 'set_mic', enabled: false }));
    }
  }
  // ... rest of class unchanged ...
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest frontend/src/services/__tests__/voiceBridge.voiceMode.test.ts -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/services/voiceBridge.ts frontend/src/services/__tests__/voiceBridge.voiceMode.test.ts
git commit -m "feat(voice): add voiceMode to VoiceBridgeService for widget handoff"
```

---

### Task 2: Create FloatingChatWidget Component (State Machine)

**Files:**
- Create: `frontend/src/components/chat/FloatingChatWidget.tsx`
- Create: `frontend/src/components/chat/FloatingChatWidget.styles.css`
- Create: `frontend/src/components/chat/index.ts` (barrel export)
- Test: `frontend/src/components/chat/__tests__/FloatingChatWidget.test.tsx`

**Interfaces:**
- Consumes: `useChatStore` (messages), `useWebSocketStore` (unreadCount), `useAuthStore` (auth), `voiceBridgeService` (voiceMode)
- Produces: Widget mounted in MainLayout; no external API

- [ ] **Step 1: Write failing test**

```tsx
// frontend/src/components/chat/__tests__/FloatingChatWidget.test.tsx
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { FloatingChatWidget } from '@/components/chat';
import { useChatStore } from '@/store/chatStore';
import { useWebSocketStore } from '@/store/websocketStore';
import { useAuthStore } from '@/store/authStore';
import { useLocation } from 'react-router-dom';
import { voiceBridgeService } from '@/services/voiceBridge';

// Mock stores and router
vi.mock('@/store/chatStore');
vi.mock('@/store/websocketStore');
vi.mock('@/store/authStore');
vi.mock('react-router-dom', () => ({
  useLocation: vi.fn(),
}));
vi.mock('@/services/voiceBridge', () => ({
  voiceBridgeService: {
    status: 'connected',
    voiceMode: 'system',
    setVoiceMode: vi.fn(),
    onStatusChange: vi.fn(() => vi.fn()),
  },
}));

const mockUseChatStore = useChatStore as vi.Mock;
const mockUseWebSocketStore = useWebSocketStore as vi.Mock;
const mockUseAuthStore = useAuthStore as vi.Mock;
const mockUseLocation = useLocation as vi.Mock;

beforeEach(() => {
  mockUseChatStore.mockReturnValue({ messages: [], setMessages: vi.fn() });
  mockUseWebSocketStore.mockReturnValue({ unreadCount: 0 });
  mockUseAuthStore.mockReturnValue({ user: { isAuthenticated: true } });
  mockUseLocation.mockReturnValue({ pathname: '/dashboard' });
});

describe('FloatingChatWidget', () => {
  test('renders collapsed dot when not on /chat', () => {
    render(<FloatingChatWidget />);
    const dot = screen.getByRole('button', { name: /open chat/i });
    expect(dot).toBeInTheDocument();
    expect(dot).toHaveStyle({ width: '8px', height: '8px' });
  });

  test('hidden on /chat route', () => {
    mockUseLocation.mockReturnValue({ pathname: '/chat' });
    render(<FloatingChatWidget />);
    expect(screen.queryByRole('button', { name: /open chat/i })).not.toBeInTheDocument();
  });

  test('hover dot → hovered icon', async () => {
    render(<FloatingChatWidget />);
    const dot = screen.getByRole('button', { name: /open chat/i });
    fireEvent.mouseEnter(dot);
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /open chat/i })).toHaveStyle({ width: '32px', height: '32px' });
    });
  });

  test('click hovered → expanded dialog', async () => {
    render(<FloatingChatWidget />);
    const dot = screen.getByRole('button', { name: /open chat/i });
    fireEvent.mouseEnter(dot);
    fireEvent.click(screen.getByRole('button', { name: /open chat/i }));
    await waitFor(() => {
      expect(screen.getByRole('dialog', { name: /agentium chat/i })).toBeInTheDocument();
    });
  });

  test('minimize button → minimized pill', async () => {
    render(<FloatingChatWidget />);
    fireEvent.mouseEnter(screen.getByRole('button', { name: /open chat/i }));
    fireEvent.click(screen.getByRole('button', { name: /open chat/i }));
    fireEvent.click(screen.getByRole('button', { name: /minimize/i }));
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /open chat/i })).toHaveStyle({ width: '48px', height: '48px' });
    });
  });

  test('close button → collapsed dot', async () => {
    render(<FloatingChatWidget />);
    fireEvent.mouseEnter(screen.getByRole('button', { name: /open chat/i }));
    fireEvent.click(screen.getByRole('button', { name: /open chat/i }));
    fireEvent.click(screen.getByRole('button', { name: /close/i }));
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /open chat/i })).toHaveStyle({ width: '8px', height: '8px' });
    });
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm test -- frontend/src/components/chat/__tests__/FloatingChatWidget.test.tsx`
Expected: FAIL — component doesn't exist

- [ ] **Step 3: Implement FloatingChatWidget**

```tsx
// frontend/src/components/chat/FloatingChatWidget.tsx
import { useState, useEffect, useRef, useCallback } from 'react';
import { useLocation } from 'react-router-dom';
import { motion, useReducedMotion, AnimatePresence } from 'motion/react';
import { useShallow } from 'zustand/react/shallow';
import { MessageCircle, Minimize, Maximize, X, Bot, Mic } from 'lucide-react';
import { useChatStore } from '@/store/chatStore';
import { useWebSocketStore } from '@/store/websocketStore';
import { useAuthStore } from '@/store/authStore';
import { voiceBridgeService, VoiceMode } from '@/services/voiceBridge';
import { ChatHeader } from './ChatHeader';
import { MessageList } from './MessageList';
import { ChatInput } from './ChatInput';
import { MinimizedWidget } from './MinimizedWidget';
import './FloatingChatWidget.styles.css';

type WidgetState = 'collapsed' | 'hovered' | 'expanded' | 'minimized';

export function FloatingChatWidget() {
  const location = useLocation();
  const isChatPage = location.pathname === '/chat';
  const isAuthenticated = useAuthStore(useShallow((s) => s.user?.isAuthenticated));

  if (!isAuthenticated || isChatPage) return null;

  const messages = useChatStore(useShallow((s) => s.messages));
  const unreadCount = useWebSocketStore(useShallow((s) => s.unreadCount));

  const [state, setState] = useState<WidgetState>('collapsed');
  const [voiceMode, setVoiceMode] = useState<VoiceMode>('system');
  const dialogRef = useRef<HTMLDialogElement>(null);
  const reduceMotion = useReducedMotion();

  // Sync voiceMode with bridge
  const syncVoiceMode = useCallback((mode: VoiceMode) => {
    setVoiceMode(mode);
    voiceBridgeService.setVoiceMode(mode);
  }, []);

  // Voice mode transitions
  useEffect(() => {
    if (state === 'expanded') syncVoiceMode('popup');
    else if (state === 'minimized' || state === 'collapsed') syncVoiceMode('system');
  }, [state, syncVoiceMode]);

  // Route change handling
  useEffect(() => {
    if (isChatPage) {
      setState('collapsed');
      syncVoiceMode('chat');
    } else if (state === 'collapsed') {
      // Already collapsed, ensure voice mode is system
      syncVoiceMode('system');
    }
  }, [isChatPage, state, syncVoiceMode]);

  // Handle Escape key on dialog
  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Escape' && state === 'expanded') {
      setState('collapsed');
    }
  };

  // Collapsed: 8px pulsing dot
  if (state === 'collapsed') {
    return (
      <motion.button
        className="floating-chat-collapsed"
        role="button"
        tabIndex={0}
        aria-label="Open Agentium Chat"
        onMouseEnter={() => setState('hovered')}
        onClick={() => setState('expanded')}
        whileHover={{ scale: 1.1 }}
        whileTap={{ scale: 0.9 }}
        style={{ '--dot-size': '8px' }}
      >
        <motion.span
          className="floating-chat-dot"
          animate={reduceMotion ? {} : { scale: [1, 1.3, 1], opacity: [0.6, 1, 0.6] }}
          transition={{ duration: 2, repeat: Infinity, ease: 'easeInOut' }}
        />
      </motion.button>
    );
  }

  // Hovered: 32px chat icon with magnetic follow
  if (state === 'hovered') {
    return (
      <motion.button
        className="floating-chat-hovered"
        role="button"
        tabIndex={0}
        aria-label="Open Agentium Chat"
        onMouseLeave={() => setState('collapsed')}
        onClick={() => setState('expanded')}
        whileHover={{ scale: 1.05 }}
        whileTap={{ scale: 0.92 }}
      >
        <MessageCircle className="w-5 h-5" aria-hidden="true" />
      </motion.button>
    );
  }

  // Minimized: 48x48 pill with unread badge
  if (state === 'minimized') {
    return (
      <MinimizedWidget
        unreadCount={unreadCount}
        onClick={() => setState('expanded')}
        reduceMotion={reduceMotion}
      />
    );
  }

  // Expanded: native <dialog>
  return (
    <AnimatePresence mode="wait">
      <dialog
        ref={dialogRef}
        className="floating-chat-dialog"
        aria-label="Agentium Chat"
        aria-describedby="chat-desc"
        onKeyDown={handleKeyDown}
        open={state === 'expanded'}
        onClose={() => setState('collapsed')}
      >
        <p id="chat-desc" className="sr-only">
          Chat with Agentium Head of Council. Messages sync across pages.
        </p>

        <ChatHeader
          voiceStatus={voiceBridgeService.status}
          onMinimize={() => setState('minimized')}
          onClose={() => setState('collapsed')}
        />

        <MessageList messages={messages} reduceMotion={reduceMotion} />

        <ChatInput
          onSend={(content, attachments) => {
            // Delegate to ChatPage's sendWsMessage via websocketStore
            const wsStore = useWebSocketStore.getState();
            wsStore.sendMessage(content, attachments);
          }}
          reduceMotion={reduceMotion}
        />
      </dialog>
    </AnimatePresence>
  );
}
```

```css
/* frontend/src/components/chat/FloatingChatWidget.styles.css */
.floating-chat-collapsed {
  position: fixed;
  bottom: 1rem;
  right: 1rem;
  z-index: 50;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--color-primary);
  border: none;
  padding: 0;
  cursor: pointer;
  transition: transform 200ms var(--motion-spring-gentle);
}

.floating-chat-collapsed:focus-visible {
  outline: none;
  box-shadow: 0 0 0 3px var(--color-primary);
}

.floating-chat-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--color-primary);
  display: block;
}

.floating-chat-hovered {
  position: fixed;
  bottom: 1rem;
  right: 1rem;
  z-index: 50;
  width: 32px;
  height: 32px;
  border-radius: 50%;
  background: var(--color-primary);
  border: none;
  color: white;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  box-shadow: 0 10px 25px rgba(0, 0, 0, 0.15);
  transition: transform 200ms var(--motion-spring-gentle), box-shadow 200ms ease;
}

.floating-chat-hovered:focus-visible {
  outline: none;
  box-shadow: 0 0 0 3px var(--color-primary), 0 10px 25px rgba(0, 0, 0, 0.15);
}

.floating-chat-dialog {
  position: fixed;
  bottom: 1rem;
  right: 1rem;
  z-index: 50;
  width: 360px;
  max-height: 520px;
  border: none;
  border-radius: 1rem;
  box-shadow: var(--shadow-2xl);
  background: var(--color-surface-elevated);
  color: var(--color-text-primary);
  padding: 0;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

/* Native <dialog> animations via @starting-style */
@media (prefers-reduced-motion: no-preference) {
  .floating-chat-dialog {
    opacity: 0;
    transform: scale(0.95) translateY(20px);
    transition:
      opacity 300ms var(--motion-spring-gentle),
      transform 300ms var(--motion-spring-gentle),
      overlay 300ms allow-discrete,
      display 300ms allow-discrete;
  }

  .floating-chat-dialog:open {
    opacity: 1;
    transform: scale(1) translateY(0);
  }

  @starting-style {
    .floating-chat-dialog:open {
      opacity: 0;
      transform: scale(0.95) translateY(20px);
    }
  }
}

@media (prefers-reduced-motion: reduce) {
  .floating-chat-dialog {
    transition: none;
  }
}

/* No backdrop for non-modal dialog */
.floating-chat-dialog::backdrop {
  display: none;
}

/* Mobile responsiveness */
@media (max-width: 480px) {
  .floating-chat-dialog {
    width: calc(100vw - 2rem);
    max-height: 80vh;
    left: 1rem;
    right: 1rem;
    bottom: 1rem;
  }

  .floating-chat-collapsed,
  .floating-chat-hovered {
    left: auto;
    right: 1rem;
  }
}

@media (max-width: 480px) and (orientation: landscape) {
  .floating-chat-dialog {
    max-height: 85vh;
  }
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npm test -- frontend/src/components/chat/__tests__/FloatingChatWidget.test.tsx`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/chat/FloatingChatWidget.tsx frontend/src/components/chat/FloatingChatWidget.styles.css frontend/src/components/chat/index.ts frontend/src/components/chat/__tests__/FloatingChatWidget.test.tsx
git commit -m "feat(chat): add FloatingChatWidget with state machine (collapsed/hovered/expanded/minimized)"
```

---

### Task 3: Create Sub-Components (ChatHeader, MessageList, ChatInput, MinimizedWidget)

**Files:**
- Create: `frontend/src/components/chat/ChatHeader.tsx`
- Create: `frontend/src/components/chat/MessageList.tsx`
- Create: `frontend/src/components/chat/ChatInput.tsx`
- Create: `frontend/src/components/chat/MinimizedWidget.tsx`
- Test: `frontend/src/components/chat/__tests__/subcomponents.test.tsx`

**Interfaces:**
- Consumes: `messages` from chatStore, `voiceBridgeService.status`
- Produces: UI elements used by FloatingChatWidget

- [ ] **Step 1: Write failing tests for each sub-component**

```tsx
// frontend/src/components/chat/__tests__/subcomponents.test.tsx
import { render, screen, fireEvent } from '@testing-library/react';
import { ChatHeader, MessageList, ChatInput, MinimizedWidget } from '@/components/chat';
import { useChatStore } from '@/store/chatStore';
import { voiceBridgeService } from '@/services/voiceBridge';
import { motion } from 'motion/react';

vi.mock('@/store/chatStore');
vi.mock('@/services/voiceBridge', () => ({
  voiceBridgeService: { status: 'connected' },
}));

describe('ChatHeader', () => {
  test('renders title, voice status, minimize, close', () => {
    render(<ChatHeader voiceStatus="connected" onMinimize={vi.fn()} onClose={vi.fn()} />);
    expect(screen.getByText('Agentium')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /minimize/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /close/i })).toBeInTheDocument();
    // Voice status dot should be green when connected
    const dot = screen.getByTestId('voice-status-dot');
    expect(dot).toHaveStyle({ backgroundColor: 'var(--color-accent)' });
  });
});

describe('MessageList', () => {
  test('renders messages with MarkdownMessage', () => {
    const mockMessages = [
      { id: '1', role: 'sovereign', content: 'Hello', timestamp: new Date() },
      { id: '2', role: 'head_of_council', content: 'Hi there!', timestamp: new Date() },
    ];
    render(<MessageList messages={mockMessages} reduceMotion={true} />);
    expect(screen.getByText('Hello')).toBeInTheDocument();
    expect(screen.getByText('Hi there!')).toBeInTheDocument();
  });

  test('shows empty state when no messages', () => {
    render(<MessageList messages={[]} reduceMotion={true} />);
    expect(screen.getByText(/no messages yet/i)).toBeInTheDocument();
  });
});

describe('ChatInput', () => {
  test('renders textarea, file, mic, send buttons', () => {
    const onSend = vi.fn();
    render(<ChatInput onSend={onSend} reduceMotion={true} />);
    expect(screen.getByPlaceholderText(/type a message/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /attach file/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /voice/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /send/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /send/i })).toBeDisabled();
  });

  test('enables send when text entered', async () => {
    const onSend = vi.fn();
    render(<ChatInput onSend={onSend} reduceMotion={true} />);
    const textarea = screen.getByPlaceholderText(/type a message/i);
    fireEvent.change(textarea, { target: { value: 'Hello' } });
    expect(screen.getByRole('button', { name: /send/i })).not.toBeDisabled();
  });
});

describe('MinimizedWidget', () => {
  test('renders 48x48 pill with MessageCircle icon', () => {
    render(<MinimizedWidget unreadCount={0} onClick={vi.fn()} reduceMotion={true} />);
    const btn = screen.getByRole('button', { name: /open chat/i });
    expect(btn).toHaveStyle({ width: '48px', height: '48px' });
  });

  test('shows unread badge when count > 0', () => {
    render(<MinimizedWidget unreadCount={3} onClick={vi.fn()} reduceMotion={true} />);
    expect(screen.getByText('3')).toBeInTheDocument();
  });

  test('shows 9+ for counts > 9', () => {
    render(<MinimizedWidget unreadCount={15} onClick={vi.fn()} reduceMotion={true} />);
    expect(screen.getByText('9+')).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `npm test -- frontend/src/components/chat/__tests__/subcomponents.test.tsx`
Expected: FAIL — components don't exist

- [ ] **Step 3: Implement ChatHeader**

```tsx
// frontend/src/components/chat/ChatHeader.tsx
import { motion } from 'motion/react';
import { Bot, Minimize, Maximize, X, Wifi, WifiOff, Loader2 } from 'lucide-react';

interface ChatHeaderProps {
  voiceStatus: 'offline' | 'connecting' | 'connected' | 'error';
  onMinimize: () => void;
  onClose: () => void;
}

export function ChatHeader({ voiceStatus, onMinimize, onClose }: ChatHeaderProps) {
  const statusConfig = {
    connected: { color: 'var(--color-accent)', Icon: Wifi, pulse: true },
    connecting: { color: 'var(--color-warning)', Icon: Loader2, pulse: false },
    offline: { color: 'var(--color-text-muted)', Icon: WifiOff, pulse: false },
    error: { color: 'var(--color-destructive)', Icon: WifiOff, pulse: false },
  } as const;

  const { color, Icon, pulse } = statusConfig[voiceStatus];

  return (
    <header className="floating-chat-header">
      <div className="floating-chat-header-left">
        <div className="floating-chat-bot-icon">
          <Bot className="w-4 h-4" aria-hidden="true" />
        </div>
        <span className="floating-chat-title">Agentium</span>
      </div>

      <div className="floating-chat-header-right">
        <motion.span
          className="floating-chat-voice-dot"
          data-testid="voice-status-dot"
          style={{ backgroundColor: color }}
          animate={pulse ? { scale: [1, 1.3, 1] } : {}}
          transition={{ duration: 1.5, repeat: Infinity, ease: 'easeInOut' }}
        >
          <Icon className="w-3 h-3" aria-hidden="true" />
        </motion.span>

        <motion.button
          className="floating-chat-header-btn"
          onClick={onMinimize}
          aria-label="Minimize chat"
          whileTap={{ scale: 0.9 }}
        >
          <Minimize className="w-4 h-4" aria-hidden="true" />
        </motion.button>

        <motion.button
          className="floating-chat-header-btn"
          onClick={onClose}
          aria-label="Close chat"
          whileTap={{ scale: 0.9 }}
        >
          <X className="w-4 h-4" aria-hidden="true" />
        </motion.button>
      </div>
    </header>
  );
}
```

- [ ] **Step 4: Implement MessageList**

```tsx
// frontend/src/components/chat/MessageList.tsx
import { motion, useReducedMotion } from 'motion/react';
import { useRef, useEffect } from 'react';
import { MarkdownMessage } from '@/components/chat/MarkdownMessage';
import { TypingIndicator } from '@/components/chat/TypingIndicator';

interface MessageListProps {
  messages: Array<{
    id: string;
    role: 'sovereign' | 'head_of_council' | 'system';
    content: string;
    timestamp: Date;
    metadata?: Record<string, unknown>;
    attachments?: Array<{ name: string; type: string; size: number; url?: string; data?: string }>;
  }>;
  reduceMotion: boolean;
}

export function MessageList({ messages, reduceMotion }: MessageListProps) {
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const messagesContainerRef = useRef<HTMLDivElement>(null);
  const reduceMotionPref = useReducedMotion();

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: reduceMotion || reduceMotionPref ? 'auto' : 'smooth' });
  };

  // Auto-scroll on new messages (unless user scrolled up)
  useEffect(() => {
    const container = messagesContainerRef.current;
    if (!container) return;
    const nearBottom = container.scrollHeight - container.scrollTop - container.clientHeight < 80;
    if (nearBottom) scrollToBottom();
  }, [messages]);

  if (messages.length === 0) {
    return (
      <div className="floating-chat-empty">
        <p>No messages yet. Start a conversation!</p>
      </div>
    );
  }

  return (
    <div
      ref={messagesContainerRef}
      className="floating-chat-messages"
      role="log"
      aria-live="polite"
      aria-label="Chat messages"
    >
      <motion.div
        initial={false}
        animate={{ opacity: 1 }}
        transition={{ staggerChildren: reduceMotion || reduceMotionPref ? 0 : 0.05 }}
      >
        {messages.map((msg, index) => (
          <motion.div
            key={msg.id}
            className={`floating-chat-message ${msg.role}`}
            variants={{
              hidden: { opacity: 0, y: 20 },
              visible: { opacity: 1, y: 0 },
            }}
            initial="hidden"
            animate="visible"
          >
            <MarkdownMessage message={msg} />
          </motion.div>
        ))}
      </motion.div>
      <div ref={messagesEndRef} />
    </div>
  );
}
```

- [ ] **Step 5: Implement ChatInput**

```tsx
// frontend/src/components/chat/ChatInput.tsx
import { useState, useRef, useEffect } from 'react';
import { motion } from 'motion/react';
import { Paperclip, Mic, Send, X } from 'lucide-react';
import { useVoiceBridge } from '@/hooks/useVoiceBridge';

interface ChatInputProps {
  onSend: (content: string, attachments?: Array<{ name: string; type: string; size: number; url?: string; data?: string }>) => void;
  reduceMotion: boolean;
}

export function ChatInput({ onSend, reduceMotion }: ChatInputProps) {
  const [input, setInput] = useState('');
  const [uploadedFiles, setUploadedFiles] = useState<Array<{ name: string; type: string; size: number; url?: string; data?: string }>>([]);
  const [isRecording, setIsRecording] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const { status: voiceStatus } = useVoiceBridge();

  // Auto-resize textarea
  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
      textareaRef.current.style.height = `${Math.min(textareaRef.current.scrollHeight, 150)}px`;
    }
  }, [input]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim() && uploadedFiles.length === 0) return;
    onSend(input.trim(), uploadedFiles.length > 0 ? uploadedFiles : undefined);
    setInput('');
    setUploadedFiles([]);
  };

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (!files) return;
    // Simplified: just store file info; real impl uploads via fileApi
    Array.from(files).forEach((file) => {
      const url = URL.createObjectURL(file);
      setUploadedFiles((prev) => [...prev, { name: file.name, type: file.type, size: file.size, url }]);
    });
    e.target.value = '';
  };

  const handleVoiceClick = () => {
    if (isRecording) {
      setIsRecording(false);
      // Stop recording logic here
    } else if (voiceStatus === 'connected') {
      setIsRecording(true);
      // Start recording logic here
    }
  };

  return (
    <form className="floating-chat-input" onSubmit={handleSubmit}>
      {uploadedFiles.length > 0 && (
        <div className="floating-chat-attachments">
          {uploadedFiles.map((file, i) => (
            <span key={i} className="floating-chat-attachment">
              {file.name}
              <button type="button" onClick={() => setUploadedFiles((prev) => prev.filter((_, idx) => idx !== i))} aria-label="Remove attachment">
                <X className="w-3 h-3" />
              </button>
            </span>
          ))}
        </div>
      )}

      <div className="floating-chat-input-row">
        <button
          type="button"
          className="floating-chat-input-btn"
          onClick={() => fileInputRef.current?.click()}
          aria-label="Attach file"
          disabled={isRecording}
        >
          <Paperclip className="w-5 h-5" />
        </button>
        <input type="file" ref={fileInputRef} onChange={handleFileSelect} className="sr-only" multiple />

        <textarea
          ref={textareaRef}
          placeholder="Type a message..."
          value={input}
          onChange={(e) => setInput(e.target.value)}
          className="floating-chat-textarea"
          rows={1}
          disabled={isRecording}
          aria-label="Chat message"
        />

        <button
          type="button"
          className="floating-chat-input-btn"
          onClick={handleVoiceClick}
          aria-label={isRecording ? 'Stop voice recording' : 'Start voice recording'}
          disabled={voiceStatus !== 'connected'}
        >
          <Mic className={`w-5 h-5 ${isRecording ? 'text-red-500' : ''}`} />
        </button>

        <motion.button
          type="submit"
          className="floating-chat-send-btn"
          disabled={!input.trim() && uploadedFiles.length === 0}
          whileTap={{ scale: 0.9 }}
          aria-label="Send message"
        >
          <Send className="w-5 h-5" />
        </motion.button>
      </div>
      <input type="file" ref={fileInputRef} onChange={handleFileSelect} className="sr-only" multiple />
    </form>
  );
}
```

- [ ] **Step 6: Implement MinimizedWidget**

```tsx
// frontend/src/components/chat/MinimizedWidget.tsx
import { motion, useReducedMotion } from 'motion/react';
import { MessageCircle } from 'lucide-react';

interface MinimizedWidgetProps {
  unreadCount: number;
  onClick: () => void;
  reduceMotion: boolean;
}

export function MinimizedWidget({ unreadCount, onClick, reduceMotion }: MinimizedWidgetProps) {
  const reduceMotionPref = useReducedMotion();
  const shouldReduce = reduceMotion || reduceMotionPref;

  return (
    <motion.button
      className="floating-chat-minimized"
      role="button"
      tabIndex={0}
      aria-label="Open Agentium Chat"
      onClick={onClick}
      whileHover={{ scale: 1.05 }}
      whileTap={{ scale: 0.95 }}
      initial={shouldReduce ? undefined : { scale: 0, rotate: -90 }}
      animate={shouldReduce ? undefined : { scale: 1, rotate: 0 }}
      transition={{ type: 'spring', stiffness: 250, damping: 25 }}
    >
      <MessageCircle className="w-6 h-6" aria-hidden="true" />

      {unreadCount > 0 && (
        <motion.span
          className="floating-chat-badge"
          animate={shouldReduce ? {} : { scale: [1, 1.2, 1] }}
          transition={{ duration: 1, repeat: Infinity, ease: 'easeInOut' }}
        >
          {unreadCount > 9 ? '9+' : unreadCount}
        </motion.span>
      )}
    </motion.button>
  );
}
```

- [ ] **Step 7: Add CSS for sub-components**

```css
/* Append to FloatingChatWidget.styles.css or create separate files */

/* ChatHeader */
.floating-chat-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0.75rem 1rem;
  border-bottom: 1px solid var(--color-border);
  background: var(--color-surface);
}

.floating-chat-header-left {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.floating-chat-bot-icon {
  width: 32px;
  height: 32px;
  border-radius: 0.75rem;
  background: linear-gradient(135deg, var(--color-primary), var(--color-secondary));
  display: flex;
  align-items: center;
  justify-content: center;
  color: white;
}

.floating-chat-title {
  font-family: var(--font-heading);
  font-weight: 600;
  font-size: 0.875rem;
  color: var(--color-text-primary);
}

.floating-chat-header-right {
  display: flex;
  align-items: center;
  gap: 0.375rem;
}

.floating-chat-voice-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
}

.floating-chat-header-btn {
  width: 32px;
  height: 32px;
  border-radius: 0.5rem;
  border: none;
  background: transparent;
  color: var(--color-text-muted);
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: background-color 150ms ease, color 150ms ease;
}

.floating-chat-header-btn:hover {
  background: var(--color-muted);
  color: var(--color-text-primary);
}

.floating-chat-header-btn:focus-visible {
  outline: none;
  box-shadow: 0 0 0 3px var(--color-primary);
}

/* MessageList */
.floating-chat-messages {
  flex: 1;
  overflow-y: auto;
  padding: 1rem;
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.floating-chat-message.sovereign {
  align-self: flex-end;
}

.floating-chat-message.head_of_council {
  align-self: flex-start;
}

.floating-chat-empty {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--color-text-muted);
  font-size: 0.875rem;
  padding: 1rem;
  text-align: center;
}

/* ChatInput */
.floating-chat-input {
  padding: 0.75rem 1rem;
  border-top: 1px solid var(--color-border);
  background: var(--color-surface);
}

.floating-chat-attachments {
  display: flex;
  flex-wrap: wrap;
  gap: 0.375rem;
  margin-bottom: 0.5rem;
}

.floating-chat-attachment {
  display: inline-flex;
  align-items: center;
  gap: 0.25rem;
  padding: 0.125rem 0.5rem;
  background: var(--color-muted);
  border-radius: 0.375rem;
  font-size: 0.75rem;
  color: var(--color-text-primary);
}

.floating-chat-attachment button {
  padding: 0;
  margin: 0;
  line-height: 1;
  color: var(--color-text-muted);
}

.floating-chat-attachment button:hover {
  color: var(--color-destructive);
}

.floating-chat-input-row {
  display: flex;
  align-items: flex-end;
  gap: 0.375rem;
}

.floating-chat-input-btn {
  width: 36px;
  height: 36px;
  border-radius: 0.5rem;
  border: none;
  background: transparent;
  color: var(--color-text-muted);
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: background-color 150ms ease, color 150ms ease;
  flex-shrink: 0;
}

.floating-chat-input-btn:hover:not(:disabled) {
  background: var(--color-muted);
  color: var(--color-text-primary);
}

.floating-chat-input-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.floating-chat-input-btn:focus-visible {
  outline: none;
  box-shadow: 0 0 0 3px var(--color-primary);
}

.floating-chat-textarea {
  flex: 1;
  min-height: 40px;
  max-height: 150px;
  padding: 0.5rem 0.75rem;
  border: 1px solid var(--color-border);
  border-radius: 1rem;
  background: var(--color-background);
  color: var(--color-text-primary);
  font-size: 0.875rem;
  line-height: 1.4;
  resize: none;
  outline: none;
  transition: border-color 150ms ease, box-shadow 150ms ease;
}

.floating-chat-textarea:focus {
  border-color: var(--color-primary);
  box-shadow: 0 0 0 3px var(--color-ring);
}

.floating-chat-textarea::placeholder {
  color: var(--color-text-muted);
}

.floating-chat-send-btn {
  width: 36px;
  height: 36px;
  border-radius: 50%;
  border: none;
  background: var(--color-primary);
  color: white;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: background-color 150ms ease, transform 150ms ease;
  flex-shrink: 0;
}

.floating-chat-send-btn:hover:not(:disabled) {
  background: var(--color-primary-hover);
}

.floating-chat-send-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.floating-chat-send-btn:focus-visible {
  outline: none;
  box-shadow: 0 0 0 3px var(--color-primary);
}

/* MinimizedWidget */
.floating-chat-minimized {
  position: fixed;
  bottom: 1rem;
  right: 1rem;
  z-index: 50;
  width: 48px;
  height: 48px;
  border-radius: 0.75rem;
  background: var(--color-primary);
  border: none;
  color: white;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  box-shadow: 0 10px 25px rgba(0, 0, 0, 0.15);
  transition: transform 200ms var(--motion-spring-gentle);
}

.floating-chat-minimized:focus-visible {
  outline: none;
  box-shadow: 0 0 0 3px var(--color-primary), 0 10px 25px rgba(0, 0, 0, 0.15);
}

.floating-chat-badge {
  position: absolute;
  top: -4px;
  right: -4px;
  min-width: 20px;
  height: 20px;
  border-radius: 9999px;
  background: var(--color-destructive);
  color: white;
  font-size: 0.625rem;
  font-weight: 700;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 0 0.375rem;
}

/* Scrollbar styling */
.floating-chat-messages::-webkit-scrollbar {
  width: 6px;
}

.floating-chat-messages::-webkit-scrollbar-track {
  background: transparent;
}

.floating-chat-messages::-webkit-scrollbar-thumb {
  background: var(--color-border);
  border-radius: 3px;
}

.floating-chat-messages::-webkit-scrollbar-thumb:hover {
  background: var(--color-text-muted);
}
```

- [ ] **Step 8: Run tests to verify they pass**

Run: `npm test -- frontend/src/components/chat/__tests__/subcomponents.test.tsx`
Expected: PASS

- [ ] **Step 9: Commit**

```bash
git add frontend/src/components/chat/ChatHeader.tsx frontend/src/components/chat/MessageList.tsx frontend/src/components/chat/ChatInput.tsx frontend/src/components/chat/MinimizedWidget.tsx frontend/src/components/chat/__tests__/subcomponents.test.tsx
git commit -m "feat(chat): add FloatingChatWidget sub-components (ChatHeader, MessageList, ChatInput, MinimizedWidget)"
```

---

### Task 4: Integrate Widget into MainLayout

**Files:**
- Modify: `frontend/src/components/layout/MainLayout.tsx` (import and render FloatingChatWidget)
- Test: `frontend/src/components/layout/__tests__/MainLayout.widget.test.tsx`

**Interfaces:**
- Consumes: `FloatingChatWidget` component
- Produces: Widget rendered on all authenticated routes except `/chat`

- [ ] **Step 1: Write failing test**

```tsx
// frontend/src/components/layout/__tests__/MainLayout.widget.test.tsx
import { render, screen } from '@testing-library/react';
import { MainLayout } from '@/components/layout/MainLayout';
import { useAuthStore } from '@/store/authStore';
import { useLocation } from 'react-router-dom';

vi.mock('@/store/authStore');
vi.mock('react-router-dom', () => ({
  ...vi.importActual('react-router-dom'),
  useLocation: vi.fn(),
  Outlet: () => <div data-testid="outlet">Outlet</div>,
}));

const mockUseAuthStore = useAuthStore as vi.Mock;
const mockUseLocation = useLocation as vi.Mock;

beforeEach(() => {
  mockUseAuthStore.mockReturnValue({ user: { isAuthenticated: true } });
});

describe('MainLayout with FloatingChatWidget', () => {
  test('renders FloatingChatWidget on non-chat routes', () => {
    mockUseLocation.mockReturnValue({ pathname: '/dashboard' });
    render(<MainLayout />);
    expect(screen.getByRole('button', { name: /open agentium chat/i })).toBeInTheDocument();
  });

  test('does NOT render FloatingChatWidget on /chat route', () => {
    mockUseLocation.mockReturnValue({ pathname: '/chat' });
    render(<MainLayout />);
    expect(screen.queryByRole('button', { name: /open agentium chat/i })).not.toBeInTheDocument();
  });

  test('does NOT render FloatingChatWidget when not authenticated', () => {
    mockUseAuthStore.mockReturnValue({ user: null });
    mockUseLocation.mockReturnValue({ pathname: '/dashboard' });
    render(<MainLayout />);
    expect(screen.queryByRole('button', { name: /open agentium chat/i })).not.toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm test -- frontend/src/components/layout/__tests__/MainLayout.widget.test.tsx`
Expected: FAIL — widget not integrated

- [ ] **Step 3: Modify MainLayout**

```tsx
// frontend/src/components/layout/MainLayout.tsx (additions)
import { FloatingChatWidget } from '@/components/chat';
// ... existing imports ...

export function MainLayout() {
  // ... existing code ...

  return (
    <div className="flex h-screen bg-gray-50 dark:bg-[#0f1117]">
      <Sidebar ... />
      {mobileOpen && <div ... />}

      <div className="flex min-w-0 flex-1 flex-col">
        <TopBar ... />
        <main id="main-content" tabIndex={-1} className="relative min-h-0 flex-1 overflow-hidden outline-none">
          <KeepAliveOutlet />
        </main>
      </div>

      {/* Voice modals (existing) */}
      {showVoiceSettings && <VoiceSettingsModal onClose={() => setShowVoiceSettings(false)} />}
      {showVoiceMode && <VoiceModePanel onClose={() => setShowVoiceMode(false)} />}

      {/* NEW: Floating Chat Widget */}
      <FloatingChatWidget />
    </div>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npm test -- frontend/src/components/layout/__tests__/MainLayout.widget.test.tsx`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/layout/MainLayout.tsx frontend/src/components/layout/__tests__/MainLayout.widget.test.tsx
git commit -m "feat(layout): integrate FloatingChatWidget into MainLayout"
```

---

### Task 5: Wire Voice Mode in ChatPage

**Files:**
- Modify: `frontend/src/pages/ChatPage.tsx` (call `voiceBridgeService.setVoiceMode('chat')` on mount)
- Test: `frontend/src/pages/__tests__/ChatPage.voiceMode.test.tsx`

**Interfaces:**
- Consumes: `voiceBridgeService.setVoiceMode()`
- Produces: Voice mode = 'chat' when ChatPage active

- [ ] **Step 1: Write failing test**

```tsx
// frontend/src/pages/__tests__/ChatPage.voiceMode.test.tsx
import { render, screen, waitFor } from '@testing-library/react';
import { ChatPage } from '@/pages/ChatPage';
import { useAuthStore } from '@/store/authStore';
import { useWebSocketStore } from '@/store/websocketStore';
import { voiceBridgeService } from '@/services/voiceBridge';

vi.mock('@/store/authStore');
vi.mock('@/store/websocketStore');
vi.mock('@/services/voiceBridge', () => ({
  voiceBridgeService: {
    status: 'connected',
    voiceMode: 'system',
    setVoiceMode: vi.fn(),
    onStatusChange: vi.fn(() => vi.fn()),
    onStateChange: vi.fn(() => vi.fn()),
  },
}));
vi.mock('@/hooks/useVoiceBridge', () => ({
  useVoiceBridge: () => ({ status: 'connected' }),
}));

const mockUseAuthStore = useAuthStore as vi.Mock;
const mockUseWebSocketStore = useWebSocketStore as vi.Mock;

beforeEach(() => {
  mockUseAuthStore.mockReturnValue({ user: { isAuthenticated: true } });
  mockUseWebSocketStore.mockReturnValue({
    connectionPhase: 'active',
    isConnected: true,
    unreadCount: 0,
    markAsRead: vi.fn(),
    sendMessage: vi.fn(),
    lastMessage: null,
    messageHistory: [],
    genesisJustCompleted: false,
  });
});

describe('ChatPage voice mode', () => {
  test('sets voiceMode to "chat" on mount', () => {
    render(<ChatPage />);
    expect(voiceBridgeService.setVoiceMode).toHaveBeenCalledWith('chat');
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm test -- frontend/src/pages/__tests__/ChatPage.voiceMode.test.tsx`
Expected: FAIL — no setVoiceMode call

- [ ] **Step 3: Modify ChatPage**

```tsx
// frontend/src/pages/ChatPage.tsx (additions)
import { voiceBridgeService } from '@/services/voiceBridge';
import { useEffect } from 'react';
// ... existing imports ...

export function ChatPage() {
  // ... existing code ...

  // Set voice mode to 'chat' when ChatPage mounts
  useEffect(() => {
    voiceBridgeService.setVoiceMode('chat');
    // Cleanup: reset to 'system' when leaving /chat (handled by route listener in MainLayout)
    return () => {
      // Don't reset here — MainLayout handles route changes
    };
  }, []);

  // ... rest of component ...
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npm test -- frontend/src/pages/__tests__/ChatPage.voiceMode.test.tsx`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/ChatPage.tsx frontend/src/pages/__tests__/ChatPage.voiceMode.test.tsx
git commit -m "feat(chat): wire voiceMode='chat' in ChatPage on mount"
```

---

### Task 6: Add Route Listener in MainLayout for Voice Mode

**Files:**
- Modify: `frontend/src/components/layout/MainLayout.tsx` (add route change effect for voice mode)

**Interfaces:**
- Consumes: `useLocation`, `voiceBridgeService.setVoiceMode()`
- Produces: Automatic voice mode switching on route changes

- [ ] **Step 1: Write failing test**

```tsx
// frontend/src/components/layout/__tests__/MainLayout.voiceRoute.test.tsx
import { render, screen, waitFor } from '@testing-library/react';
import { MainLayout } from '@/components/layout/MainLayout';
import { useAuthStore } from '@/store/authStore';
import { useLocation } from 'react-router-dom';
import { voiceBridgeService } from '@/services/voiceBridge';
import { MemoryRouter, Routes, Route } from 'react-router-dom';

vi.mock('@/store/authStore');
vi.mock('@/services/voiceBridge', () => ({
  voiceBridgeService: {
    status: 'connected',
    voiceMode: 'system',
    setVoiceMode: vi.fn(),
    onStatusChange: vi.fn(() => vi.fn()),
    onStateChange: vi.fn(() => vi.fn()),
  },
}));

const mockUseAuthStore = useAuthStore as vi.Mock;

beforeEach(() => {
  mockUseAuthStore.mockReturnValue({ user: { isAuthenticated: true } });
});

function renderWithRouter(pathname: string) {
  return render(
    <MemoryRouter initialEntries={[pathname]}>
      <Routes>
        <Route path="/*" element={<MainLayout />} />
      </Routes>
    </MemoryRouter>
  );
}

describe('MainLayout voice mode on route change', () => {
  test('sets voiceMode to "system" when navigating away from /chat', () => {
    renderWithRouter('/chat');
    // Navigate away
    renderWithRouter('/dashboard');
    expect(voiceBridgeService.setVoiceMode).toHaveBeenCalledWith('system');
  });

  test('sets voiceMode to "chat" when navigating to /chat', () => {
    renderWithRouter('/dashboard');
    renderWithRouter('/chat');
    expect(voiceBridgeService.setVoiceMode).toHaveBeenCalledWith('chat');
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm test -- frontend/src/components/layout/__tests__/MainLayout.voiceRoute.test.tsx`
Expected: FAIL — no route listener

- [ ] **Step 3: Add route listener to MainLayout**

```tsx
// frontend/src/components/layout/MainLayout.tsx (additions)
import { useLocation } from 'react-router-dom';
import { voiceBridgeService } from '@/services/voiceBridge';
import { useEffect } from 'react';
// ... existing imports ...

export function MainLayout() {
  const location = useLocation();
  // ... existing state ...

  // Voice mode sync on route change
  useEffect(() => {
    if (location.pathname === '/chat') {
      voiceBridgeService.setVoiceMode('chat');
    } else {
      // Widget handles its own mode when expanded/minimized
      // Default to 'system' for wake-word
      voiceBridgeService.setVoiceMode('system');
    }
  }, [location.pathname]);

  // ... rest of component ...
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npm test -- frontend/src/components/layout/__tests__/MainLayout.voiceRoute.test.tsx`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/layout/MainLayout.tsx frontend/src/components/layout/__tests__/MainLayout.voiceRoute.test.tsx
git commit -m "feat(layout): add route listener for voiceMode sync"
```

---

### Task 7: Add CSS Variables for Motion Tokens

**Files:**
- Modify: `frontend/src/index.css` (or create `frontend/src/components/chat/motion-tokens.css` and import)

**Interfaces:**
- Consumes: Design tokens from spec
- Produces: CSS custom properties used by widget styles

- [ ] **Step 1: Add motion tokens to global CSS**

```css
/* frontend/src/index.css (append) */
/* Motion tokens for FloatingChatWidget */
:root {
  --motion-spring-gentle: cubic-bezier(0.22, 1, 0.36, 1);
  --motion-spring-snappy: cubic-bezier(0.34, 1.56, 0.64, 1);

  --duration-fast: 150ms;
  --duration-normal: 250ms;
  --duration-slow: 350ms;
}
```

- [ ] **Step 2: Verify no test needed (CSS only)**

- [ ] **Step 3: Commit**

```bash
git add frontend/src/index.css
git commit -m "feat(styles): add motion tokens for FloatingChatWidget animations"
```

---

### Task 8: Accessibility Audit & Polish

**Files:**
- Modify: `frontend/src/components/chat/FloatingChatWidget.tsx` (add focus management, ARIA)
- Test: `frontend/src/components/chat/__tests__/FloatingChatWidget.a11y.test.tsx`

**Interfaces:**
- Consumes: All widget components
- Produces: WCAG 2.1 AA compliant widget

- [ ] **Step 1: Write a11y test**

```tsx
// frontend/src/components/chat/__tests__/FloatingChatWidget.a11y.test.tsx
import { render, screen, fireEvent } from '@testing-library/react';
import { FloatingChatWidget } from '@/components/chat';
import { axe, toHaveNoViolations } from 'jest-axe';

expect.extend(toHaveNoViolations);

vi.mock('@/store/authStore', () => ({
  useAuthStore: () => ({ user: { isAuthenticated: true } }),
}));
vi.mock('@/store/chatStore', () => ({
  useChatStore: () => ({ messages: [], setMessages: vi.fn() }),
}));
vi.mock('@/store/websocketStore', () => ({
  useWebSocketStore: () => ({ unreadCount: 0 }),
}));
vi.mock('@/services/voiceBridge', () => ({
  voiceBridgeService: {
    status: 'connected',
    voiceMode: 'system',
    setVoiceMode: vi.fn(),
    onStatusChange: vi.fn(() => vi.fn()),
  },
}));

describe('FloatingChatWidget accessibility', () => {
  test('no axe violations in collapsed state', async () => {
    const { container } = render(<FloatingChatWidget />);
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });

  test('no axe violations in expanded state', async () => {
    const { container } = render(<FloatingChatWidget />);
    fireEvent.mouseEnter(screen.getByRole('button', { name: /open agentium chat/i }));
    fireEvent.click(screen.getByRole('button', { name: /open agentium chat/i }));
    await screen.findByRole('dialog', { name: /agentium chat/i });
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });

  test('dialog has proper ARIA attributes', async () => {
    render(<FloatingChatWidget />);
    fireEvent.mouseEnter(screen.getByRole('button', { name: /open agentium chat/i }));
    fireEvent.click(screen.getByRole('button', { name: /open agentium chat/i }));
    const dialog = await screen.findByRole('dialog', { name: /agentium chat/i });
    expect(dialog).toHaveAttribute('aria-describedby', 'chat-desc');
    expect(screen.getById('chat-desc')).toBeInTheDocument();
  });

  test('focus moves to close button on expand', async () => {
    render(<FloatingChatWidget />);
    fireEvent.mouseEnter(screen.getByRole('button', { name: /open agentium chat/i }));
    fireEvent.click(screen.getByRole('button', { name: /open agentium chat/i }));
    await screen.findByRole('dialog', { name: /agentium chat/i });
    expect(screen.getByRole('button', { name: /close/i })).toHaveFocus();
  });

  test('Escape key closes dialog', async () => {
    render(<FloatingChatWidget />);
    fireEvent.mouseEnter(screen.getByRole('button', { name: /open agentium chat/i }));
    fireEvent.click(screen.getByRole('button', { name: /open agentium chat/i }));
    await screen.findByRole('dialog', { name: /agentium chat/i });
    fireEvent.keyDown(document, { key: 'Escape' });
    await screen.findByRole('button', { name: /open agentium chat/i }); // back to collapsed
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm test -- frontend/src/components/chat/__tests__/FloatingChatWidget.a11y.test.tsx`
Expected: FAIL — missing focus management, ARIA

- [ ] **Step 3: Add focus management to FloatingChatWidget**

```tsx
// frontend/src/components/chat/FloatingChatWidget.tsx (additions)
import { useEffect, useRef } from 'react';
// ... existing imports ...

export function FloatingChatWidget() {
  // ... existing code ...

  const closeButtonRef = useRef<HTMLButtonElement>(null);
  const previousActiveElement = useRef<HTMLElement | null>(null);

  // Focus management for dialog
  useEffect(() => {
    if (state === 'expanded') {
      previousActiveElement.current = document.activeElement as HTMLElement;
      // Focus close button after dialog opens
      setTimeout(() => closeButtonRef.current?.focus(), 0);
    } else if (previousActiveElement.current && state === 'collapsed') {
      previousActiveElement.current.focus();
      previousActiveElement.current = null;
    }
  }, [state]);

  // ... existing code ...

  // In expanded state JSX, add ref to close button:
  <motion.button
    ref={closeButtonRef}
    className="floating-chat-header-btn"
    onClick={() => setState('collapsed')}
    aria-label="Close chat"
    whileTap={{ scale: 0.9 }}
  >
    <X className="w-4 h-4" aria-hidden="true" />
  </motion.button>

  // ... rest unchanged ...
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npm test -- frontend/src/components/chat/__tests__/FloatingChatWidget.a11y.test.tsx`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/chat/FloatingChatWidget.tsx frontend/src/components/chat/__tests__/FloatingChatWidget.a11y.test.tsx
git commit -m "feat(chat): add accessibility (focus management, ARIA, Escape key)"
```

---

### Task 9: E2E Tests (Playwright)

**Files:**
- Create: `frontend/tests/e2e/floating-chat-widget.spec.ts`

**Interfaces:**
- Consumes: Running dev server with all components
- Produces: End-to-end verification of widget behavior

- [ ] **Step 1: Create E2E test file**

```typescript
// frontend/tests/e2e/floating-chat-widget.spec.ts
import { test, expect } from '@playwright/test';

test.describe('FloatingChatWidget', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/login');
    await page.fill('input[type="email"]', 'test@example.com');
    await page.fill('input[type="password"]', 'password123');
    await page.click('button[type="submit"]');
    await page.waitForURL('/');
  });

  test('widget appears on dashboard, hidden on chat page', async ({ page }) => {
    // On dashboard
    await expect(page.locator('button[aria-label="Open Agentium Chat"]')).toBeVisible();

    // Navigate to chat
    await page.click('a[href="/chat"]');
    await expect(page.locator('button[aria-label="Open Agentium Chat"]')).not.toBeVisible();
  });

  test('state transitions: collapsed → hover → expanded → minimized → expanded → collapsed', async ({ page }) => {
    await page.goto('/dashboard');

    // Collapsed dot visible
    const dot = page.locator('button[aria-label="Open Agentium Chat"]');
    await expect(dot).toBeVisible();
    await expect(dot).toHaveCSS('width', '8px');

    // Hover → hovered icon
    await dot.hover();
    await expect(page.locator('button[aria-label="Open Agentium Chat"] >> visible=true')).toHaveCSS('width', '32px');

    // Click → expanded dialog
    await dot.click();
    const dialog = page.locator('dialog[aria-label="Agentium Chat"]');
    await expect(dialog).toBeVisible();

    // Minimize
    await page.click('button[aria-label="Minimize chat"]');
    await expect(page.locator('button[aria-label="Open Agentium Chat"]')).toHaveCSS('width', '48px');

    // Click minimized → expanded
    await page.click('button[aria-label="Open Agentium Chat"]');
    await expect(dialog).toBeVisible();

    // Close
    await page.click('button[aria-label="Close chat"]');
    await expect(dot).toHaveCSS('width', '8px');
  });

  test('messages sync between widget and ChatPage', async ({ page, context }) => {
    // Send message from widget
    await page.goto('/dashboard');
    await page.locator('button[aria-label="Open Agentium Chat"]').hover();
    await page.locator('button[aria-label="Open Agentium Chat"]').click();
    await page.fill('textarea[placeholder="Type a message..."]', 'Hello from widget');
    await page.click('button[aria-label="Send message"]');
    await expect(page.locator('text=Hello from widget')).toBeVisible();

    // Open ChatPage in new tab
    const page2 = await context.newPage();
    await page2.goto('/chat');
    await expect(page2.locator('text=Hello from widget')).toBeVisible();

    // Reply from ChatPage
    await page2.fill('textarea[placeholder*="message"]', 'Reply from ChatPage');
    await page2.click('button[aria-label="Send"]');
    await expect(page2.locator('text=Reply from ChatPage')).toBeVisible();

    // Check widget receives reply
    await expect(page.locator('text=Reply from ChatPage')).toBeVisible();
  });

  test('voice mode switches correctly', async ({ page }) => {
    await page.goto('/dashboard');
    await page.locator('button[aria-label="Open Agentium Chat"]').hover();
    await page.locator('button[aria-label="Open Agentium Chat"]').click();

    // Voice status should show connected when expanded
    const voiceDot = page.locator('[data-testid="voice-status-dot"]');
    await expect(voiceDot).toHaveAttribute('style', /rgb\(5, 150, 105\)/); // green

    // Minimize → voice status should change (widget no longer owns mic)
    await page.click('button[aria-label="Minimize chat"]');
    // Note: actual voice bridge state change tested in unit tests
  });

  test('reduced motion disables animations', async ({ page }) => {
    await page.emulateMedia({ reducedMotion: 'reduce' });
    await page.goto('/dashboard');

    const dot = page.locator('button[aria-label="Open Agentium Chat"]');
    // No pulse animation when reduced motion
    await expect(dot).toHaveCSS('animation-name', 'none');
  });

  test('mobile viewport responsive', async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 667 });
    await page.goto('/dashboard');

    const dialog = page.locator('dialog[aria-label="Agentium Chat"]');
    await page.locator('button[aria-label="Open Agentium Chat"]').hover();
    await page.locator('button[aria-label="Open Agentium Chat"]').click();

    await expect(dialog).toBeVisible();
    // Should be nearly full width on mobile
    const dialogBox = await dialog.boundingBox();
    expect(dialogBox!.width).toBeGreaterThan(300);
    expect(dialogBox!.width).toBeLessThan(375);
  });
});
```

- [ ] **Step 2: Run E2E tests**

Run: `npx playwright test frontend/tests/e2e/floating-chat-widget.spec.ts`
Expected: PASS (after all previous tasks complete)

- [ ] **Step 3: Commit**

```bash
git add frontend/tests/e2e/floating-chat-widget.spec.ts
git commit -m "test(e2e): add FloatingChatWidget Playwright tests"
```

---

### Task 10: Documentation Update

**Files:**
- Modify: `docs/superpowers/specs/2025-07-25-floating-chat-widget-design.md` (mark as implemented)
- Create: `docs/superpowers/features/floating-chat-widget.md` (user-facing docs)

**Interfaces:**
- Consumes: Completed implementation
- Produces: Updated docs

- [ ] **Step 1: Update spec status**

```markdown
# Floating Chat Widget — Design Specification

**Date:** 2025-07-25  
**Status:** **Implemented**  
**Author:** Agentium Team  
**Related:** #floating-chat-widget
```

- [ ] **Step 2: Create user-facing docs**

```markdown
# Floating Chat Widget

The Floating Chat Widget lets you chat with the Head of Council from any page in Agentium (except the dedicated Chat page).

## Features

- **Always accessible:** Persistent floating button in bottom-right corner
- **Full parity:** Same message history, file uploads, and voice as the Chat page
- **Smart voice handoff:** 
  - On Chat page → page owns voice
  - Widget expanded → widget owns voice
  - Widget minimized/closed → system wake-word ("Hey Agentium")
- **Keyboard accessible:** Full Tab navigation, Escape to close, focus management
- **Respects reduced motion:** All animations disabled when `prefers-reduced-motion: reduce`

## Usage

1. Click the pulsing dot → expands to chat icon
2. Hover chat icon → magnetic follow effect
3. Click → opens full chat dialog
4. Use minimize (⎯) to shrink to pill, close (×) to return to dot

## Voice Commands

When widget is **minimized or closed**, say "Hey Agentium" to activate voice bridge.
When widget is **expanded**, click the mic button for push-to-talk.

## Accessibility

- WCAG 2.1 AA compliant
- Screen reader support via native `<dialog>` and ARIA labels
- Focus visible rings on all interactive elements
- Live region announcements for new messages
- Color contrast ≥ 4.5:1
```

- [ ] **Step 3: Commit**

```bash
git add docs/superpowers/specs/2025-07-25-floating-chat-widget-design.md docs/superpowers/features/floating-chat-widget.md
git commit -m "docs: update floating chat widget spec status and add user docs"
```

---

## Spec Coverage Checklist

| Spec Section | Task(s) |
|--------------|---------|
| 2.1 Component Placement | Task 4 |
| 2.2 State Management | Task 2, 3 |
| 2.3 Voice Ownership Model | Task 1, 5, 6 |
| 3.1 File Structure | Task 2, 3 |
| 3.2 State Machine | Task 2 |
| 3.3 Props & Types | Task 2, 3 |
| 3.4 Native `<dialog>` | Task 2 |
| 4.1 Visual Design | Task 2, 3 (CSS) |
| 4.2 Component Specs | Task 2, 3 |
| 4.3 Mobile/Touch | Task 2 (CSS), Task 9 (E2E) |
| 5.1-5.4 Motion | Task 2 (CSS), Task 7 (tokens) |
| 6.1-6.3 Voice Integration | Task 1, 5, 6 |
| 7 Accessibility | Task 8 |
| 8.1-8.6 Testing | Task 1-9 (unit), Task 9 (E2E) |
| 9 Implementation Order | This plan |
| 10 Risks | Addressed in tasks |

---

## Execution Options

**Plan complete and saved to** `docs/superpowers/plans/2025-07-25-floating-chat-widget.md`

**Two execution options:**

1. **Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration
   - REQUIRED SUB-SKILL: `superpowers:subagent-driven-development`

2. **Inline Execution** - Execute tasks in this session using `executing-plans`, batch execution with checkpoints
   - REQUIRED SUB-SKILL: `superpowers:executing-plans`

**Which approach?**
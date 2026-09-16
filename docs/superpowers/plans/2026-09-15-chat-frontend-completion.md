# Chat Frontend Completion (Section 9.3) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete all remaining TODO items in Section 9.3 (Chat Frontend) by adding conversation management UI (right collapsible sidebar) and enhancing tool call display in typing indicator.

**Architecture:** Reusable RightSidebar shell component with slot-based content; ConversationSidebar as first slot; chatStore extended with conversation state; TypingIndicator enhanced for tool names. All endpoints exist in backend.

**Tech Stack:** React 18, TypeScript, Zustand (state), Socket.io-client (WebSocket), existing UI components

## Global Constraints

- No breaking changes to existing WebSocket protocol — `tool_names` in `tool_progress` is optional/additive
- `currentConversationId` persisted to `sessionStorage` (per-session), sidebar UI state to `localStorage` (persistent)
- Respect `prefers-reduced-motion` for all animations
- Follow existing code patterns in `ChatPage.tsx`, `chatStore.ts`, `MarkdownMessage.tsx`
- Mobile-first responsive: sidebar becomes bottom sheet on <768px viewport
- Accessibility: ARIA roles, keyboard navigation, focus management, screen reader announcements
- Feature flag `ENABLE_CONVERSATION_SIDEBAR` env var for rollback

---

### Task 1: RightSidebar Shell Component

**Files:**
- Create: `frontend/src/components/layout/RightSidebar.tsx`
- Create: `frontend/src/components/layout/RightSidebar.module.css`
- Test: `frontend/src/components/layout/__tests__/RightSidebar.test.tsx`

**Interfaces:**
- Consumes: None (foundation component)
- Produces: `RightSidebar` component with props:
  ```typescript
  interface RightSidebarProps {
    isOpen: boolean;
    onClose: () => void;
    children: React.ReactNode;
    width?: number;           // default 320
    minWidth?: number;        // default 48 (collapsed)
    position?: 'right' | 'bottom'; // default 'right'
    className?: string;
  }
  ```
- Provides context: `RightSidebarContext` for nested components to access collapse/expand

- [ ] **Step 1: Write the failing test**

```tsx
// frontend/src/components/layout/__tests__/RightSidebar.test.tsx
import { render, screen, fireEvent } from '@testing-library/react';
import { RightSidebar } from '../RightSidebar';

describe('RightSidebar', () => {
  const defaultProps = {
    isOpen: true,
    onClose: vi.fn(),
    children: <div data-testid="sidebar-content">Content</div>,
  };

  it('renders children when open', () => {
    render(<RightSidebar {...defaultProps} />);
    expect(screen.getByTestId('sidebar-content')).toBeInTheDocument();
  });

  it('does not render children when closed', () => {
    render(<RightSidebar {...defaultProps} isOpen={false} />);
    expect(screen.queryByTestId('sidebar-content')).not.toBeInTheDocument();
  });

  it('calls onClose when overlay clicked', () => {
    render(<RightSidebar {...defaultProps} />);
    fireEvent.click(screen.getByTestId('sidebar-overlay'));
    expect(defaultProps.onClose).toHaveBeenCalled();
  });

  it('applies correct width style', () => {
    render(<RightSidebar {...defaultProps} width={400} />);
    const sidebar = screen.getByTestId('sidebar-panel');
    expect(sidebar).toHaveStyle('width: 400px');
  });

  it('switches to bottom sheet on mobile', () => {
    // Mock matchMedia for mobile
    Object.defineProperty(window, 'matchMedia', {
      value: vi.fn().mockImplementation(query => ({
        matches: query === '(max-width: 767px)',
        addListener: vi.fn(),
        removeListener: vi.fn(),
      })),
    });
    render(<RightSidebar {...defaultProps} position="bottom" />);
    const panel = screen.getByTestId('sidebar-panel');
    expect(panel).toHaveClass('sidebar-bottom');
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm test -- frontend/src/components/layout/__tests__/RightSidebar.test.tsx`
Expected: FAIL - "Cannot find module '../RightSidebar'"

- [ ] **Step 3: Write minimal implementation**

```tsx
// frontend/src/components/layout/RightSidebar.tsx
import React, { createContext, useContext, useEffect, useState } from 'react';
import styles from './RightSidebar.module.css';

interface RightSidebarContextValue {
  isCollapsed: boolean;
  toggleCollapse: () => void;
}

const RightSidebarContext = createContext<RightSidebarContextValue | null>(null);

export const useRightSidebar = () => {
  const ctx = useContext(RightSidebarContext);
  if (!ctx) throw new Error('useRightSidebar must be used within RightSidebar');
  return ctx;
};

interface RightSidebarProps {
  isOpen: boolean;
  onClose: () => void;
  children: React.ReactNode;
  width?: number;
  minWidth?: number;
  position?: 'right' | 'bottom';
  className?: string;
}

export const RightSidebar: React.FC<RightSidebarProps> = ({
  isOpen,
  onClose,
  children,
  width = 320,
  minWidth = 48,
  position = 'right',
  className = '',
}) => {
  const [isMobile, setIsMobile] = useState(false);
  const [isCollapsed, setIsCollapsed] = useState(false);

  useEffect(() => {
    const mediaQuery = window.matchMedia('(max-width: 767px)');
    const handleChange = (e: MediaQueryListEvent) => setIsMobile(e.matches);
    setIsMobile(mediaQuery.matches);
    mediaQuery.addEventListener('change', handleChange);
    return () => mediaQuery.removeEventListener('change', handleChange);
  }, []);

  useEffect(() => {
    if (!isOpen) setIsCollapsed(false);
  }, [isOpen]);

  const toggleCollapse = () => setIsCollapsed(prev => !prev);

  if (!isOpen && !isMobile) return null;

  const panelStyle: React.CSSProperties = {
    width: isCollapsed ? minWidth : width,
    transform: isMobile ? 'translateY(100%)' : 'translateX(0)',
  };

  return (
    <RightSidebarContext.Provider value={{ isCollapsed, toggleCollapse }}>
      <div
        data-testid="sidebar-overlay"
        className={`${styles.overlay} ${isOpen ? styles.open : ''} ${isMobile ? styles.mobile : ''}`}
        onClick={onClose}
        role="dialog"
        aria-modal="true"
        aria-label="Sidebar"
      >
        <div
          data-testid="sidebar-panel"
          className={`${styles.panel} ${position === 'bottom' ? styles.bottom : ''} ${className}`}
          style={panelStyle}
          onClick={e => e.stopPropagation()}
        >
          <div className={styles.handle} onClick={toggleCollapse} aria-label={isCollapsed ? 'Expand sidebar' : 'Collapse sidebar'}>
            <span className={styles.handleIcon}>{isCollapsed ? '›' : '‹'}</span>
          </div>
          <div className={styles.content}>{children}</div>
        </div>
      </div>
    </RightSidebarContext.Provider>
  );
};
```

```css
/* frontend/src/components/layout/RightSidebar.module.css */
.overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.3);
  z-index: 100;
  opacity: 0;
  visibility: hidden;
  transition: opacity 0.2s ease, visibility 0.2s ease;
}

.overlay.open {
  opacity: 1;
  visibility: visible;
}

.overlay.mobile .panel {
  bottom: 0;
  left: 0;
  right: 0;
  top: auto;
  height: 60vh;
  max-height: 60vh;
  border-radius: 16px 16px 0 0;
  transform: translateY(100%);
  transition: transform 0.3s ease;
}

.overlay.mobile.open .panel {
  transform: translateY(0);
}

.panel {
  position: fixed;
  top: 0;
  right: 0;
  bottom: 0;
  background: var(--bg-secondary, #1e1e1e);
  border-left: 1px solid var(--border-color, #333);
  display: flex;
  flex-direction: column;
  z-index: 101;
  transform: translateX(100%);
  transition: transform 0.3s ease, width 0.2s ease;
}

.overlay.open .panel {
  transform: translateX(0);
}

.panel.bottom {
  border-left: none;
  border-top: 1px solid var(--border-color, #333);
}

.handle {
  position: absolute;
  top: 50%;
  left: -12px;
  transform: translateY(-50%);
  width: 24px;
  height: 48px;
  background: var(--bg-secondary, #1e1e1e);
  border: 1px solid var(--border-color, #333);
  border-right: none;
  border-radius: 8px 0 0 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  z-index: 102;
}

.handleIcon {
  font-size: 14px;
  color: var(--text-muted, #888);
  transition: transform 0.2s ease;
}

.content {
  flex: 1;
  overflow: auto;
  padding: 16px;
}

@media (prefers-reduced-motion: reduce) {
  .overlay,
  .panel,
  .handleIcon {
    transition: none !important;
  }
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npm test -- frontend/src/components/layout/__tests__/RightSidebar.test.tsx`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/layout/RightSidebar.tsx frontend/src/components/layout/RightSidebar.module.css frontend/src/components/layout/__tests__/RightSidebar.test.tsx
git commit -m "feat(layout): add RightSidebar shell component with collapse/expand and mobile bottom sheet"
```

---

### Task 2: chatStore Extensions — Conversation State & Actions

**Files:**
- Modify: `frontend/src/store/chatStore.ts`
- Test: `frontend/src/store/__tests__/chatStore.conversations.test.ts`

**Interfaces:**
- Consumes: `chatApi` (existing), `Conversation` type from `chatApi.ts`
- Produces: Extended `ChatState` with:
  ```typescript
  interface Conversation {
    id: string;
    title: string;
    is_archived: boolean;
    created_at: string;
    updated_at: string;
    message_count: number;
    last_message_preview?: string;
  }

  // New state
  currentConversationId: string | null;
  conversations: Conversation[];
  isSidebarOpen: boolean;
  sidebarWidth: number;

  // New actions
  setConversation: (conversationId: string) => Promise<void>;
  createConversation: (title?: string) => Promise<string>;
  loadConversations: () => Promise<void>;
  deleteConversation: (conversationId: string) => Promise<void>;
  updateConversation: (conversationId: string, updates: { title?: string; is_archived?: boolean }) => Promise<void>;
  toggleSidebar: () => void;
  setSidebarWidth: (width: number) => void;
  ```

- [ ] **Step 1: Write the failing test**

```ts
// frontend/src/store/__tests__/chatStore.conversations.test.ts
import { act } from '@testing-library/react';
import { useChatStore } from '../chatStore';
import { chatApi } from '../../services/chatApi';

vi.mock('../../services/chatApi');

describe('chatStore - conversations', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useChatStore.getState().resetStore();
    localStorage.clear();
    sessionStorage.clear();
  });

  const mockConversation = {
    id: 'conv-1',
    title: 'Test Conversation',
    is_archived: false,
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
    message_count: 5,
    last_message_preview: 'Hello world',
  };

  it('loadConversations fetches and stores conversations', async () => {
    vi.mocked(chatApi.getConversations).mockResolvedValue([mockConversation]);
    
    await act(async () => {
      await useChatStore.getState().loadConversations();
    });

    expect(useChatStore.getState().conversations).toEqual([mockConversation]);
    expect(chatApi.getConversations).toHaveBeenCalled();
  });

  it('setConversation loads messages and sets currentConversationId', async () => {
    const mockMessages = [
      { id: 'msg-1', role: 'user', content: 'Hi', timestamp: new Date().toISOString() },
      { id: 'msg-2', role: 'assistant', content: 'Hello!', timestamp: new Date().toISOString() },
    ];
    vi.mocked(chatApi.getConversation).mockResolvedValue({ ...mockConversation, messages: mockMessages });

    await act(async () => {
      await useChatStore.getState().setConversation('conv-1');
    });

    expect(useChatStore.getState().currentConversationId).toBe('conv-1');
    expect(useChatStore.getState().messages).toEqual(mockMessages);
  });

  it('createConversation creates and switches to new conversation', async () => {
    vi.mocked(chatApi.createConversation).mockResolvedValue(mockConversation);
    vi.mocked(chatApi.getConversation).mockResolvedValue({ ...mockConversation, messages: [] });

    let newId: string;
    await act(async () => {
      newId = await useChatStore.getState().createConversation('New Chat');
    });

    expect(newId).toBe('conv-1');
    expect(useChatStore.getState().currentConversationId).toBe('conv-1');
    expect(chatApi.createConversation).toHaveBeenCalledWith('New Chat');
  });

  it('deleteConversation removes from list and clears current if active', async () => {
    vi.mocked(chatApi.getConversations).mockResolvedValue([mockConversation]);
    await act(async () => {
      await useChatStore.getState().loadConversations();
    });
    vi.mocked(chatApi.deleteConversation).mockResolvedValue(undefined);

    await act(async () => {
      await useChatStore.getState().deleteConversation('conv-1');
    });

    expect(useChatStore.getState().conversations).toEqual([]);
    expect(useChatStore.getState().currentConversationId).toBeNull();
  });

  it('toggleSidebar toggles isSidebarOpen', () => {
    expect(useChatStore.getState().isSidebarOpen).toBe(false);
    act(() => { useChatStore.getState().toggleSidebar(); });
    expect(useChatStore.getState().isSidebarOpen).toBe(true);
  });

  it('persists currentConversationId to sessionStorage', async () => {
    vi.mocked(chatApi.getConversation).mockResolvedValue({ ...mockConversation, messages: [] });
    await act(async () => {
      await useChatStore.getState().setConversation('conv-1');
    });
    expect(sessionStorage.getItem('chat:currentConversationId')).toBe('conv-1');
  });

  it('rehydrates currentConversationId from sessionStorage on init', () => {
    sessionStorage.setItem('chat:currentConversationId', 'conv-1');
    // Re-initialize store (simulated by creating new store instance in test)
    // Note: actual rehydration happens via persist middleware
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm test -- frontend/src/store/__tests__/chatStore.conversations.test.ts`
Expected: FAIL - new actions not implemented

- [ ] **Step 3: Write minimal implementation**

```typescript
// frontend/src/store/chatStore.ts (additions to existing store)

import { create } from 'zustand';
import { persist, createJSONStorage } from 'zustand/middleware';
import { chatApi, type Conversation as ApiConversation } from '../services/chatApi';

// Extend existing Message type with conversation context
export interface Conversation {
  id: string;
  title: string;
  is_archived: boolean;
  created_at: string;
  updated_at: string;
  message_count: number;
  last_message_preview?: string;
}

interface ChatState {
  // ...existing state...
  messages: Message[];
  isAwaitingReply: boolean;
  isThinking: boolean;
  toolCount: number;
  activeStreamId: string | null;
  _streamBuffer: string;
  _streamFlushTimer: ReturnType<typeof setTimeout> | null;

  // NEW: Conversation state
  currentConversationId: string | null;
  conversations: Conversation[];
  isSidebarOpen: boolean;
  sidebarWidth: number;

  // ...existing actions...
  addMessage: (message: Message) => void;
  updateMessage: (id: string, updates: Partial<Message>) => void;
  setAwaitingReply: (awaiting: boolean) => void;
  setThinking: (thinking: boolean) => void;
  setToolCount: (count: number) => void;
  appendStreamToken: (token: string) => void;
  finalizeStream: () => void;
  resetStream: () => void;
  clearMessages: () => void;
  loadChatHistory: () => Promise<void>;

  // NEW: Conversation actions
  setConversation: (conversationId: string) => Promise<void>;
  createConversation: (title?: string) => Promise<string>;
  loadConversations: () => Promise<void>;
  deleteConversation: (conversationId: string) => Promise<void>;
  updateConversation: (conversationId: string, updates: { title?: string; is_archived?: boolean }) => Promise<void>;
  toggleSidebar: () => void;
  setSidebarWidth: (width: number) => void;
}

const STORAGE_KEY = 'agentium-chat-store';
const CONVERSATION_ID_KEY = 'chat:currentConversationId';
const SIDEBAR_WIDTH_KEY = 'chat:sidebar:width';
const SIDEBAR_OPEN_KEY = 'chat:sidebar:open';

export const useChatStore = create<ChatState>()(
  persist(
    (set, get) => ({
      // ...existing initial state...
      messages: [],
      isAwaitingReply: false,
      isThinking: false,
      toolCount: 0,
      activeStreamId: null,
      _streamBuffer: '',
      _streamFlushTimer: null,

      // NEW initial state
      currentConversationId: null,
      conversations: [],
      isSidebarOpen: false,
      sidebarWidth: 320,

      // ...existing actions...
      addMessage: (message) => set(state => ({ messages: [...state.messages, message] })),
      updateMessage: (id, updates) => set(state => ({
        messages: state.messages.map(m => m.id === id ? { ...m, ...updates } : m)
      })),
      setAwaitingReply: (awaiting) => set({ isAwaitingReply: awaiting }),
      setThinking: (thinking) => set({ isThinking: thinking }),
      setToolCount: (count) => set({ toolCount: count }),
      appendStreamToken: (token) => set(state => ({ _streamBuffer: state._streamBuffer + token })),
      finalizeStream: () => set(state => {
        if (state._streamFlushTimer) clearTimeout(state._streamFlushTimer);
        return { _streamBuffer: '', activeStreamId: null, _streamFlushTimer: null };
      }),
      resetStream: () => set({ _streamBuffer: '', activeStreamId: null, _streamFlushTimer: null, isAwaitingReply: false }),
      clearMessages: () => set({ messages: [] }),
      loadChatHistory: async () => {
        // ...existing implementation...
      },

      // NEW: Conversation actions
      setConversation: async (conversationId: string) => {
        const { resetStream } = get();
        resetStream(); // Finalize any active stream
        set({ isAwaitingReply: false, isThinking: false, toolCount: 0 });
        
        try {
          const response = await chatApi.getConversation(conversationId);
          const messages = response.messages.map((m: any) => ({
            id: m.id,
            role: m.role,
            content: m.content,
            timestamp: new Date(m.timestamp),
            status: 'sent' as const,
            attachments: m.attachments,
            tool_calls: m.tool_calls,
          }));
          set({ 
            messages, 
            currentConversationId: conversationId,
            isSidebarOpen: false, // Close sidebar on mobile after selection
          });
          sessionStorage.setItem(CONVERSATION_ID_KEY, conversationId);
        } catch (error) {
          console.error('Failed to load conversation:', error);
          throw error;
        }
      },

      createConversation: async (title?: string) => {
        try {
          const response = await chatApi.createConversation({ title: title || 'New Conversation' });
          const newConv: Conversation = {
            id: response.id,
            title: response.title,
            is_archived: response.is_archived,
            created_at: response.created_at,
            updated_at: response.updated_at,
            message_count: 0,
          };
          set(state => ({ 
            conversations: [newConv, ...state.conversations],
            currentConversationId: response.id,
            messages: [],
            isSidebarOpen: false,
          }));
          sessionStorage.setItem(CONVERSATION_ID_KEY, response.id);
          return response.id;
        } catch (error) {
          console.error('Failed to create conversation:', error);
          throw error;
        }
      },

      loadConversations: async () => {
        try {
          const response = await chatApi.getConversations();
          const conversations: Conversation[] = response.map((c: ApiConversation) => ({
            id: c.id,
            title: c.title,
            is_archived: c.is_archived,
            created_at: c.created_at,
            updated_at: c.updated_at,
            message_count: c.message_count || 0,
            last_message_preview: c.last_message_preview,
          }));
          set({ conversations });
        } catch (error) {
          console.error('Failed to load conversations:', error);
        }
      },

      deleteConversation: async (conversationId: string) => {
        try {
          await chatApi.deleteConversation(conversationId);
          set(state => {
            const newConversations = state.conversations.filter(c => c.id !== conversationId);
            const newCurrentId = state.currentConversationId === conversationId 
              ? (newConversations[0]?.id || null) 
              : state.currentConversationId;
            if (newCurrentId === null) {
              sessionStorage.removeItem(CONVERSATION_ID_KEY);
            }
            return { conversations: newConversations, currentConversationId: newCurrentId };
          });
        } catch (error) {
          console.error('Failed to delete conversation:', error);
          throw error;
        }
      },

      updateConversation: async (conversationId: string, updates: { title?: string; is_archived?: boolean }) => {
        try {
          await chatApi.updateConversation(conversationId, updates);
          set(state => ({
            conversations: state.conversations.map(c => 
              c.id === conversationId ? { ...c, ...updates } : c
            ),
          }));
        } catch (error) {
          console.error('Failed to update conversation:', error);
          throw error;
        }
      },

      toggleSidebar: () => set(state => {
        const newOpen = !state.isSidebarOpen;
        localStorage.setItem(SIDEBAR_OPEN_KEY, String(newOpen));
        if (newOpen) get().loadConversations(); // Refresh on open
        return { isSidebarOpen: newOpen };
      }),

      setSidebarWidth: (width: number) => {
        set({ sidebarWidth: width });
        localStorage.setItem(SIDEBAR_WIDTH_KEY, String(width));
      },
    }),
    {
      name: STORAGE_KEY,
      storage: createJSONStorage(() => sessionStorage),
      partialize: (state) => ({
        // Only persist messages and currentConversationId
        messages: state.messages,
        currentConversationId: state.currentConversationId,
      }),
      onRehydrateStorage: () => (state) => {
        if (state) {
          // Convert timestamp strings back to Date objects
          state.messages = state.messages.map((m: any) => ({
            ...m,
            timestamp: new Date(m.timestamp),
          }));
          // Rehydrate sidebar state from localStorage
          const savedWidth = localStorage.getItem(SIDEBAR_WIDTH_KEY);
          const savedOpen = localStorage.getItem(SIDEBAR_OPEN_KEY);
          if (savedWidth) state.sidebarWidth = parseInt(savedWidth, 10);
          if (savedOpen) state.isSidebarOpen = savedOpen === 'true';
        }
      },
    }
  )
);
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npm test -- frontend/src/store/__tests__/chatStore.conversations.test.ts`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/store/chatStore.ts frontend/src/store/__tests__/chatStore.conversations.test.ts
git commit -m "feat(store): add conversation state management to chatStore"
```

---

### Task 3: ConversationSidebar & ConversationList Components

**Files:**
- Create: `frontend/src/components/chat/ConversationSidebar.tsx`
- Create: `frontend/src/components/chat/ConversationSidebar.module.css`
- Create: `frontend/src/components/chat/ConversationList.tsx`
- Create: `frontend/src/components/chat/ConversationList.module.css`
- Test: `frontend/src/components/chat/__tests__/ConversationSidebar.test.tsx`
- Test: `frontend/src/components/chat/__tests__/ConversationList.test.tsx`

**Interfaces:**
- Consumes: `useChatStore` (conversations, currentConversationId, setConversation, createConversation, deleteConversation, updateConversation, toggleSidebar, sidebarWidth, setSidebarWidth), `useRightSidebar` (isCollapsed, toggleCollapse)
- Produces: `ConversationSidebar` (main content for RightSidebar), `ConversationList` (virtualized list with actions)

- [ ] **Step 1: Write the failing test**

```tsx
// frontend/src/components/chat/__tests__/ConversationList.test.tsx
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { ConversationList } from '../ConversationList';
import { useChatStore } from '../../store/chatStore';
import { RightSidebarProvider } from '../../components/layout/RightSidebar';

// Mock store
vi.mock('../../store/chatStore', () => ({
  useChatStore: vi.fn(),
}));

const mockConversations = [
  { id: 'conv-1', title: 'General', is_archived: false, created_at: new Date().toISOString(), updated_at: new Date().toISOString(), message_count: 10, last_message_preview: 'Hello!' },
  { id: 'conv-2', title: 'Project Planning', is_archived: false, created_at: new Date().toISOString(), updated_at: new Date().toISOString(), message_count: 5, last_message_preview: 'Let me help...' },
  { id: 'conv-3', title: 'Code Review', is_archived: true, created_at: new Date().toISOString(), updated_at: new Date().toISOString(), message_count: 20, last_message_preview: 'Looks good!' },
];

describe('ConversationList', () => {
  beforeEach(() => {
    vi.mocked(useChatStore).mockReturnValue({
      conversations: mockConversations,
      currentConversationId: 'conv-1',
      setConversation: vi.fn(),
      createConversation: vi.fn().mockResolvedValue('conv-new'),
      deleteConversation: vi.fn(),
      updateConversation: vi.fn(),
      toggleSidebar: vi.fn(),
      sidebarWidth: 320,
      setSidebarWidth: vi.fn(),
      isSidebarOpen: true,
    });
  });

  it('renders conversation list with titles and previews', () => {
    render(<ConversationList />);
    expect(screen.getByText('General')).toBeInTheDocument();
    expect(screen.getByText('Project Planning')).toBeInTheDocument();
    expect(screen.getByText('Code Review')).toBeInTheDocument();
    expect(screen.getByText('Hello!')).toBeInTheDocument();
  });

  it('highlights active conversation', () => {
    render(<ConversationList />);
    const activeItem = screen.getByText('General').closest('[data-testid="conversation-item"]');
    expect(activeItem).toHaveClass('active');
  });

  it('calls setConversation on click', async () => {
    const setConversation = vi.fn();
    vi.mocked(useChatStore).mockReturnValue({
      ...vi.mocked(useChatStore)(),
      setConversation,
    });
    render(<ConversationList />);
    fireEvent.click(screen.getByText('Project Planning'));
    await waitFor(() => expect(setConversation).toHaveBeenCalledWith('conv-2'));
  });

  it('shows new conversation button', () => {
    render(<ConversationList />);
    expect(screen.getByRole('button', { name: /new conversation/i })).toBeInTheDocument();
  });

  it('shows action menu on hover (desktop)', () => {
    render(<ConversationList />);
    const item = screen.getByText('General').closest('[data-testid="conversation-item"]');
    fireEvent.mouseEnter(item!);
    expect(screen.getByRole('button', { name: /rename/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /archive/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /delete/i })).toBeInTheDocument();
  });

  it('collapsed mode shows only icons', () => {
    vi.mocked(useChatStore).mockReturnValue({
      ...vi.mocked(useChatStore)(),
      sidebarWidth: 48,
    });
    render(<ConversationList />);
    // In collapsed mode, only icons should be visible
    expect(screen.queryByText('General')).not.toBeInTheDocument();
  });
});
```

```tsx
// frontend/src/components/chat/__tests__/ConversationSidebar.test.tsx
import { render, screen, fireEvent } from '@testing-library/react';
import { ConversationSidebar } from '../ConversationSidebar';
import { useChatStore } from '../../store/chatStore';

vi.mock('../../store/chatStore');
vi.mock('../../components/layout/RightSidebar', () => ({
  useRightSidebar: () => ({ isCollapsed: false, toggleCollapse: vi.fn() }),
}));

describe('ConversationSidebar', () => {
  it('renders ConversationList inside', () => {
    vi.mocked(useChatStore).mockReturnValue({
      conversations: [],
      currentConversationId: null,
      setConversation: vi.fn(),
      createConversation: vi.fn(),
      deleteConversation: vi.fn(),
      updateConversation: vi.fn(),
      toggleSidebar: vi.fn(),
      sidebarWidth: 320,
      setSidebarWidth: vi.fn(),
      isSidebarOpen: true,
    });
    render(<ConversationSidebar />);
    expect(screen.getByRole('button', { name: /new conversation/i })).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm test -- frontend/src/components/chat/__tests__/ConversationList.test.tsx`
Expected: FAIL - components not exist

- [ ] **Step 3: Write minimal implementation**

```tsx
// frontend/src/components/chat/ConversationList.tsx
import React, { useState } from 'react';
import { useChatStore } from '../../store/chatStore';
import { formatDistanceToNow } from 'date-fns';
import styles from './ConversationList.module.css';

interface ConversationItemProps {
  conversation: Conversation;
  isActive: boolean;
  isCollapsed: boolean;
  onSelect: (id: string) => void;
  onRename: (id: string, title: string) => void;
  onArchive: (id: string) => void;
  onDelete: (id: string) => void;
}

const ConversationItem: React.FC<ConversationItemProps> = ({
  conversation,
  isActive,
  isCollapsed,
  onSelect,
  onRename,
  onArchive,
  onDelete,
}) => {
  const [showActions, setShowActions] = useState(false);
  const [isRenaming, setIsRenaming] = useState(false);
  const [renameValue, setRenameValue] = useState(conversation.title);

  const handleRename = () => {
    onRename(conversation.id, renameValue);
    setIsRenaming(false);
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') handleRename();
    if (e.key === 'Escape') setIsRenaming(false);
  };

  if (isCollapsed) {
    return (
      <button
        data-testid="conversation-item"
        className={`${styles.item} ${styles.collapsed} ${isActive ? styles.active : ''}`}
        onClick={() => onSelect(conversation.id)}
        title={conversation.title}
        aria-label={conversation.title}
        role="option"
        aria-selected={isActive}
      >
        <span className={styles.icon}>💬</span>
        {conversation.is_archived && <span className={styles.archiveBadge} aria-label="Archived">📦</span>}
      </button>
    );
  }

  return (
    <div
      data-testid="conversation-item"
      className={`${styles.item} ${isActive ? styles.active : ''}`}
      onMouseEnter={() => setShowActions(true)}
      onMouseLeave={() => setShowActions(false)}
      onFocusWithin={() => setShowActions(true)}
      onBlur={() => setShowActions(false)}
    >
      <button
        className={styles.mainButton}
        onClick={() => onSelect(conversation.id)}
        role="option"
        aria-selected={isActive}
        aria-label={conversation.title}
      >
        <span className={styles.icon}>💬</span>
        <div className={styles.textContent}>
          {isRenaming ? (
            <input
              type="text"
              value={renameValue}
              onChange={e => setRenameValue(e.target.value)}
              onBlur={handleRename}
              onKeyDown={handleKeyDown}
              autoFocus
              className={styles.renameInput}
              aria-label="Conversation title"
            />
          ) : (
            <span className={styles.title}>{conversation.title}</span>
          )}
          <div className={styles.meta}>
            <span className={styles.preview}>{conversation.last_message_preview}</span>
            <span className={styles.time}>
              {conversation.updated_at ? formatDistanceToNow(new Date(conversation.updated_at), { addSuffix: true }) : ''}
            </span>
          </div>
        </div>
        {conversation.is_archived && <span className={styles.archiveBadge} aria-label="Archived">📦</span>}
      </button>
      <div className={`${styles.actions} ${showActions ? styles.visible : ''}`}>
        <button
          className={styles.actionBtn}
          onClick={e => { e.stopPropagation(); setIsRenaming(true); }}
          aria-label="Rename conversation"
        >
          ✏️
        </button>
        <button
          className={styles.actionBtn}
          onClick={e => { e.stopPropagation(); onArchive(conversation.id); }}
          aria-label={conversation.is_archived ? 'Unarchive' : 'Archive'}
        >
          {conversation.is_archived ? '📤' : '📦'}
        </button>
        <button
          className={styles.actionBtn}
          onClick={e => { e.stopPropagation(); onDelete(conversation.id); }}
          aria-label="Delete conversation"
        >
          🗑️
        </button>
      </div>
    </div>
  );
};

export const ConversationList: React.FC = () => {
  const {
    conversations,
    currentConversationId,
    setConversation,
    createConversation,
    deleteConversation,
    updateConversation,
    sidebarWidth,
  } = useChatStore();

  const isCollapsed = sidebarWidth <= 48;

  const handleCreate = async () => {
    const title = prompt('Conversation title:', 'New Conversation');
    if (title) {
      await createConversation(title);
    }
  };

  const handleRename = async (id: string, title: string) => {
    if (title.trim() && title !== conversations.find(c => c.id === id)?.title) {
      await updateConversation(id, { title: title.trim() });
    }
  };

  const handleArchive = async (id: string) => {
    const conv = conversations.find(c => c.id === id);
    if (conv) await updateConversation(id, { is_archived: !conv.is_archived });
  };

  const handleDelete = async (id: string) => {
    if (confirm('Delete this conversation?')) {
      await deleteConversation(id);
    }
  };

  return (
    <div className={styles.container} role="listbox" aria-label="Conversations">
      <button
        className={styles.newButton}
        onClick={handleCreate}
        aria-label="New conversation"
        disabled={isCollapsed}
      >
        <span className={styles.newIcon}>+</span>
        {!isCollapsed && <span className={styles.newLabel}>New Conversation</span>}
      </button>
      <div className={styles.list}>
        {conversations.length === 0 ? (
          <div className={styles.empty} role="status">
            {!isCollapsed && 'No conversations yet. Create one to get started!'}
          </div>
        ) : (
          conversations.map(conv => (
            <ConversationItem
              key={conv.id}
              conversation={conv}
              isActive={conv.id === currentConversationId}
              isCollapsed={isCollapsed}
              onSelect={setConversation}
              onRename={handleRename}
              onArchive={handleArchive}
              onDelete={handleDelete}
            />
          ))
        )}
      </div>
    </div>
  );
};
```

```css
/* frontend/src/components/chat/ConversationList.module.css */
.container {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
}

.newButton {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  padding: 12px;
  background: var(--bg-tertiary, #2a2a2a);
  border: 1px solid var(--border-color, #333);
  border-radius: 8px;
  color: var(--text-primary, #fff);
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: background 0.15s ease;
  text-align: left;
}

.newButton:hover:not(:disabled) {
  background: var(--bg-hover, #333);
}

.newButton:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.newIcon {
  font-size: 16px;
  font-weight: bold;
}

.newLabel {
  flex: 1;
}

.list {
  flex: 1;
  overflow-y: auto;
  padding: 8px 4px;
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-height: 0;
}

.empty {
  padding: 24px 12px;
  text-align: center;
  color: var(--text-muted, #888);
  font-size: 13px;
}

.item {
  position: relative;
  border-radius: 8px;
  overflow: hidden;
}

.item.collapsed {
  padding: 10px;
  justify-content: center;
}

.mainButton {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  width: 100%;
  padding: 10px 12px;
  background: transparent;
  border: none;
  color: var(--text-primary, #fff);
  text-align: left;
  cursor: pointer;
  border-radius: 6px;
  transition: background 0.1s ease;
}

.mainButton:hover {
  background: var(--bg-hover, #333);
}

.item.active .mainButton {
  background: var(--accent-bg, rgba(59, 130, 246, 0.15));
}

.icon {
  font-size: 18px;
  flex-shrink: 0;
  margin-top: 2px;
}

.textContent {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.title {
  font-size: 14px;
  font-weight: 500;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.meta {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.preview {
  font-size: 12px;
  color: var(--text-muted, #888);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  flex: 1;
}

.time {
  font-size: 11px;
  color: var(--text-muted, #888);
  white-space: nowrap;
  flex-shrink: 0;
}

.archiveBadge {
  font-size: 12px;
  opacity: 0.7;
}

.actions {
  position: absolute;
  top: 50%;
  right: 8px;
  transform: translateY(-50%);
  display: flex;
  gap: 4px;
  opacity: 0;
  pointer-events: none;
  transition: opacity 0.15s ease;
}

.item:hover .actions,
.item:focus-within .actions {
  opacity: 1;
  pointer-events: auto;
}

.actions.visible {
  opacity: 1;
  pointer-events: auto;
}

.actionBtn {
  width: 28px;
  height: 28px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--bg-tertiary, #2a2a2a);
  border: 1px solid var(--border-color, #333);
  border-radius: 6px;
  cursor: pointer;
  font-size: 12px;
  transition: background 0.1s ease, transform 0.1s ease;
}

.actionBtn:hover {
  background: var(--bg-hover, #333);
  transform: scale(1.05);
}

.renameInput {
  width: 100%;
  padding: 4px 8px;
  background: var(--bg-tertiary, #2a2a2a);
  border: 1px solid var(--accent-color, #3b82f6);
  border-radius: 4px;
  color: var(--text-primary, #fff);
  font-size: 14px;
  outline: none;
}

@media (prefers-reduced-motion: reduce) {
  .newButton,
  .mainButton,
  .actions,
  .actionBtn {
    transition: none !important;
  }
}
```

```tsx
// frontend/src/components/chat/ConversationSidebar.tsx
import React from 'react';
import { useRightSidebar } from '../../components/layout/RightSidebar';
import { ConversationList } from './ConversationList';
import styles from './ConversationSidebar.module.css';

export const ConversationSidebar: React.FC = () => {
  const { isCollapsed, toggleCollapse } = useRightSidebar();

  return (
    <div className={`${styles.sidebar} ${isCollapsed ? styles.collapsed : ''}`}>
      <div className={styles.header}>
        <h2 className={styles.title}>Conversations</h2>
        <button
          className={styles.collapseBtn}
          onClick={toggleCollapse}
          aria-label={isCollapsed ? 'Expand sidebar' : 'Collapse sidebar'}
          aria-expanded={!isCollapsed}
        >
          {isCollapsed ? '›' : '‹'}
        </button>
      </div>
      <ConversationList />
    </div>
  );
};
```

```css
/* frontend/src/components/chat/ConversationSidebar.module.css */
.sidebar {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
  transition: width 0.2s ease;
}

.sidebar.collapsed {
  /* Width controlled by RightSidebar parent */
}

.header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  border-bottom: 1px solid var(--border-color, #333);
}

.title {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary, #fff);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.collapseBtn {
  width: 24px;
  height: 24px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: transparent;
  border: none;
  color: var(--text-muted, #888);
  font-size: 14px;
  cursor: pointer;
  border-radius: 4px;
  transition: background 0.1s ease, color 0.1s ease;
}

.collapseBtn:hover {
  background: var(--bg-hover, #333);
  color: var(--text-primary, #fff);
}

@media (prefers-reduced-motion: reduce) {
  .sidebar,
  .collapseBtn {
    transition: none !important;
  }
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npm test -- frontend/src/components/chat/__tests__/ConversationList.test.tsx`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/chat/ConversationSidebar.tsx frontend/src/components/chat/ConversationSidebar.module.css frontend/src/components/chat/ConversationList.tsx frontend/src/components/chat/ConversationList.module.css frontend/src/components/chat/__tests__/ConversationSidebar.test.tsx frontend/src/components/chat/__tests__/ConversationList.test.tsx
git commit -m "feat(chat): add ConversationSidebar and ConversationList components"
```

---

### Task 4: ChatPage Integration — Wire Up Sidebar & Conversation Switching

**Files:**
- Modify: `frontend/src/pages/ChatPage.tsx`
- Modify: `frontend/src/pages/ChatPage.module.css` (if exists, else create)
- Test: `frontend/src/pages/__tests__/ChatPage.conversations.test.tsx`

**Interfaces:**
- Consumes: `useChatStore` (all conversation state + actions), `useWebSocketStore` (streaming state), `RightSidebar`, `ConversationSidebar`
- Produces: Updated `ChatPage` with right sidebar in AI Chat tab, conversation switching logic

- [ ] **Step 1: Write the failing test**

```tsx
// frontend/src/pages/__tests__/ChatPage.conversations.test.tsx
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { ChatPage } from '../ChatPage';
import { useChatStore } from '../../store/chatStore';
import { useWebSocketStore } from '../../store/websocketStore';

vi.mock('../../store/chatStore');
vi.mock('../../store/websocketStore');

describe('ChatPage - Conversation Integration', () => {
  const mockStore = {
    messages: [],
    isAwaitingReply: false,
    isThinking: false,
    toolCount: 0,
    activeStreamId: null,
    currentConversationId: 'conv-1',
    conversations: [
      { id: 'conv-1', title: 'General', is_archived: false, created_at: new Date().toISOString(), updated_at: new Date().toISOString(), message_count: 5, last_message_preview: 'Hi' },
      { id: 'conv-2', title: 'Project', is_archived: false, created_at: new Date().toISOString(), updated_at: new Date().toISOString(), message_count: 3, last_message_preview: 'Hello' },
    ],
    isSidebarOpen: false,
    sidebarWidth: 320,
    setConversation: vi.fn().mockResolvedValue(undefined),
    createConversation: vi.fn().mockResolvedValue('conv-new'),
    loadConversations: vi.fn(),
    toggleSidebar: vi.fn(),
    setSidebarWidth: vi.fn(),
    // ... other required actions
  };

  beforeEach(() => {
    vi.mocked(useChatStore).mockReturnValue(mockStore);
    vi.mocked(useWebSocketStore).mockReturnValue({
      isConnected: true,
      connect: vi.fn(),
      disconnect: vi.fn(),
      sendMessage: vi.fn(),
      toolCount: 0,
      isThinking: false,
    });
  });

  it('renders sidebar toggle button in AI Chat tab header', () => {
    render(<ChatPage />);
    expect(screen.getByRole('button', { name: /conversations/i })).toBeInTheDocument();
  });

  it('opens sidebar when toggle clicked', () => {
    render(<ChatPage />);
    fireEvent.click(screen.getByRole('button', { name: /conversations/i }));
    expect(screen.getByRole('dialog', { name: /conversations/i })).toBeInTheDocument();
  });

  it('shows ConversationSidebar content in sidebar', () => {
    render(<ChatPage />);
    fireEvent.click(screen.getByRole('button', { name: /conversations/i }));
    expect(screen.getByText('Conversations')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /new conversation/i })).toBeInTheDocument();
  });

  it('calls setConversation when conversation selected', async () => {
    render(<ChatPage />);
    fireEvent.click(screen.getByRole('button', { name: /conversations/i }));
    fireEvent.click(screen.getByText('Project'));
    await waitFor(() => expect(mockStore.setConversation).toHaveBeenCalledWith('conv-2'));
  });

  it('shows sidebar only in AI Chat tab, not Inbox/Files', () => {
    render(<ChatPage />);
    // Switch to Inbox tab
    fireEvent.click(screen.getByRole('tab', { name: /inbox/i }));
    expect(screen.queryByRole('button', { name: /conversations/i })).not.toBeInTheDocument();
  });

  it('loads currentConversationId messages on mount', async () => {
    vi.mocked(useChatStore).mockReturnValue({
      ...mockStore,
      currentConversationId: 'conv-1',
      messages: [],
    });
    render(<ChatPage />);
    await waitFor(() => expect(mockStore.setConversation).toHaveBeenCalledWith('conv-1'));
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm test -- frontend/src/pages/__tests__/ChatPage.conversations.test.tsx`
Expected: FAIL - sidebar integration not implemented

- [ ] **Step 3: Write minimal implementation**

```tsx
// frontend/src/pages/ChatPage.tsx (key modifications - see inline comments)

import React, { useEffect, useRef, useState } from 'react';
import { useChatStore } from '../store/chatStore';
import { useWebSocketStore } from '../store/websocketStore';
import { RightSidebar } from '../components/layout/RightSidebar';
import { ConversationSidebar } from '../components/chat/ConversationSidebar';
import { TypingIndicator } from '../components/chat/TypingIndicator';
import { MarkdownMessage } from '../components/chat/MarkdownMessage';
// ... other existing imports

// Add feature flag check
const ENABLE_CONVERSATION_SIDEBAR = import.meta.env.VITE_ENABLE_CONVERSATION_SIDEBAR !== 'false';

export const ChatPage: React.FC = () => {
  const {
    messages,
    isAwaitingReply,
    isThinking,
    toolCount,
    toolNames, // NEW: from websocket
    currentConversationId,
    conversations,
    isSidebarOpen,
    sidebarWidth,
    setConversation,
    createConversation,
    loadConversations,
    toggleSidebar,
    setSidebarWidth,
    resetStream,
    // ... other existing state/actions
  } = useChatStore();

  const { isConnected, toolCount: wsToolCount, toolNames: wsToolNames } = useWebSocketStore();
  
  // NEW: Local state for sidebar
  const [sidebarPosition, setSidebarPosition] = useState<'right' | 'bottom'>('right');
  const [toolNames, setToolNames] = useState<string[]>([]);

  // Sync tool names from websocket store
  useEffect(() => {
    setToolNames(wsToolNames || []);
  }, [wsToolNames]);

  // Load conversations on mount and rehydrate current conversation
  useEffect(() => {
    if (ENABLE_CONVERSATION_SIDEBAR && currentConversationId && messages.length === 0) {
      // Only load if we have a conversation ID but no messages (rehydration case)
      setConversation(currentConversationId);
    } else if (ENABLE_CONVERSATION_SIDEBAR && !currentConversationId && conversations.length === 0) {
      // First load - fetch conversations list
      loadConversations();
    }
  }, []); // Run once on mount

  // Handle mobile breakpoint
  useEffect(() => {
    const mediaQuery = window.matchMedia('(max-width: 767px)');
    const handleChange = (e: MediaQueryListEvent) => {
      setSidebarPosition(e.matches ? 'bottom' : 'right');
      if (e.matches) toggleSidebar(); // Close on mobile by default
    };
    setSidebarPosition(mediaQuery.matches ? 'bottom' : 'right');
    mediaQuery.addEventListener('change', handleChange);
    return () => mediaQuery.removeEventListener('change', handleChange);
  }, [toggleSidebar]);

  const handleSendMessage = async (content: string, attachments?: File[]) => {
    if (!currentConversationId) {
      // Auto-create conversation on first message
      const newId = await createConversation();
      // Message will be sent via websocket with new conversation ID
    }
    // ... existing send logic
  };

  const handleConversationSwitch = async (conversationId: string) => {
    // Finalize any active stream before switching
    if (isAwaitingReply || isThinking) {
      resetStream();
    }
    await setConversation(conversationId);
  };

  return (
    <div className={styles.container}>
      {/* Existing tab navigation (AI Chat / Inbox / Files) */}
      <div className={styles.tabBar} role="tablist">
        <button role="tab" aria-selected={activeTab === 'chat'}>AI Chat</button>
        <button role="tab" aria-selected={activeTab === 'inbox'}>Inbox</button>
        <button role="tab" aria-selected={activeTab === 'files'}>Files</button>
      </div>

      {activeTab === 'chat' && (
        <>
          {/* Chat header with sidebar toggle */}
          <header className={styles.header}>
            <h1>AI Chat</h1>
            {ENABLE_CONVERSATION_SIDEBAR && (
              <button
                className={styles.sidebarToggle}
                onClick={toggleSidebar}
                aria-label={isSidebarOpen ? 'Close conversations' : 'Open conversations'}
                aria-expanded={isSidebarOpen}
              >
                💬
              </button>
            )}
          </header>

          {/* Messages area */}
          <main className={styles.messagesArea}>
            {messages.map(msg => (
              <MarkdownMessage key={msg.id} message={msg} />
            ))}
            {(isAwaitingReply || isThinking) && (
              <TypingIndicator 
                thinking={isThinking} 
                toolCount={toolCount || wsToolCount}
                toolNames={toolNames} // NEW: pass tool names
              />
            )}
          </main>

          {/* Input area (existing) */}
          <ChatInput onSend={handleSendMessage} />
        </>
      )}

      {/* Inbox / Files tabs - existing content */}
      {activeTab === 'inbox' && <InboxTab />}
      {activeTab === 'files' && <FilesTab />}

      {/* Right Sidebar - Conversations */}
      {ENABLE_CONVERSATION_SIDEBAR && activeTab === 'chat' && (
        <RightSidebar
          isOpen={isSidebarOpen}
          onClose={toggleSidebar}
          width={sidebarWidth}
          position={sidebarPosition}
        >
          <ConversationSidebar />
        </RightSidebar>
      )}
    </div>
  );
};
```

```css
/* frontend/src/pages/ChatPage.module.css (additions) */
.header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  border-bottom: 1px solid var(--border-color, #333);
}

.sidebarToggle {
  width: 40px;
  height: 40px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--bg-tertiary, #2a2a2a);
  border: 1px solid var(--border-color, #333);
  border-radius: 8px;
  font-size: 18px;
  cursor: pointer;
  transition: background 0.15s ease;
}

.sidebarToggle:hover {
  background: var(--bg-hover, #333);
}

.sidebarToggle[aria-expanded="true"] {
  background: var(--accent-bg, rgba(59, 130, 246, 0.15));
  border-color: var(--accent-color, #3b82f6);
}

.messagesArea {
  flex: 1;
  overflow-y: auto;
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

@media (prefers-reduced-motion: reduce) {
  .sidebarToggle {
    transition: none !important;
  }
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npm test -- frontend/src/pages/__tests__/ChatPage.conversations.test.tsx`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/ChatPage.tsx frontend/src/pages/ChatPage.module.css frontend/src/pages/__tests__/ChatPage.conversations.test.tsx
git commit -m "feat(chat): integrate conversation sidebar into ChatPage"
```

---

### Task 5: TypingIndicator Enhancement — Tool Names Display

**Files:**
- Modify: `frontend/src/components/chat/TypingIndicator.tsx`
- Modify: `frontend/src/components/chat/TypingIndicator.module.css` (if exists)
- Modify: `frontend/src/store/websocketStore.ts` (add `toolNames` state)
- Test: `frontend/src/components/chat/__tests__/TypingIndicator.toolNames.test.tsx`

**Interfaces:**
- Consumes: `toolNames: string[]` prop, `toolCount` from websocket store
- Produces: Enhanced typing indicator showing tool names when available

- [ ] **Step 1: Write the failing test**

```tsx
// frontend/src/components/chat/__tests__/TypingIndicator.toolNames.test.tsx
import { render, screen } from '@testing-library/react';
import { TypingIndicator } from '../TypingIndicator';

describe('TypingIndicator - toolNames', () => {
  it('shows tool names when provided', () => {
    render(<TypingIndicator thinking={false} toolCount={3} toolNames={['web_search', 'file_read', 'code_exec']} />);
    expect(screen.getByText(/running: web_search, file_read, code_exec/i)).toBeInTheDocument();
  });

  it('shows tool count when names not provided', () => {
    render(<TypingIndicator thinking={false} toolCount={3} toolNames={[]} />);
    expect(screen.getByText(/running tools: 3/i)).toBeInTheDocument();
  });

  it('shows thinking state when no tools', () => {
    render(<TypingIndicator thinking={true} toolCount={0} toolNames={[]} />);
    expect(screen.getByText(/thinking/i)).toBeInTheDocument();
  });

  it('shows default animation when idle', () => {
    render(<TypingIndicator thinking={false} toolCount={0} toolNames={[]} />);
    expect(screen.getByTestId('typing-dots')).toBeInTheDocument();
  });

  it('truncates long tool name lists', () => {
    const manyTools = Array.from({ length: 10 }, (_, i) => `tool_${i}`);
    render(<TypingIndicator thinking={false} toolCount={10} toolNames={manyTools} />);
    const text = screen.getByText(/running:/i).textContent;
    expect(text).toContain('tool_0');
    expect(text).toContain('...');
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm test -- frontend/src/components/chat/__tests__/TypingIndicator.toolNames.test.tsx`
Expected: FAIL - toolNames prop not handled

- [ ] **Step 3: Write minimal implementation**

```typescript
// frontend/src/store/websocketStore.ts (additions)

interface WebSocketState {
  // ...existing...
  toolCount: number;
  toolNames: string[]; // NEW
  setToolCount: (count: number) => void;
  setToolNames: (names: string[]) => void; // NEW
  clearToolState: () => void; // NEW: resets both
}

// In store definition:
toolNames: [],
setToolNames: (names) => set({ toolNames: names }),
clearToolState: () => set({ toolCount: 0, toolNames: [] }),
// Modify setToolCount to also clear names when count goes to 0
setToolCount: (count) => set(state => ({ 
  toolCount: count, 
  toolNames: count === 0 ? [] : state.toolNames 
})),
```

```tsx
// frontend/src/components/chat/TypingIndicator.tsx
import React, { useEffect, useState } from 'react';
import styles from './TypingIndicator.module.css';

interface TypingIndicatorProps {
  thinking: boolean;
  toolCount: number;
  toolNames?: string[];
}

export const TypingIndicator: React.FC<TypingIndicatorProps> = ({
  thinking,
  toolCount,
  toolNames = [],
}) => {
  const [displayText, setDisplayText] = useState('');
  const prefersReducedMotion = useMediaQuery('(prefers-reduced-motion: reduce)');

  useEffect(() => {
    if (toolNames.length > 0) {
      const truncated = toolNames.slice(0, 3).join(', ');
      const suffix = toolNames.length > 3 ? ` +${toolNames.length - 3} more` : '';
      setDisplayText(`🔧 Running: ${truncated}${suffix}`);
    } else if (toolCount > 0) {
      setDisplayText(`🔧 Running tools: ${toolCount}`);
    } else if (thinking) {
      setDisplayText('💭 Thinking...');
    } else {
      setDisplayText('');
    }
  }, [toolNames, toolCount, thinking]);

  if (!displayText && !thinking && toolCount === 0) {
    return (
      <div className={styles.container} data-testid="typing-dots" aria-hidden="true">
        <span className={styles.dot}></span>
        <span className={styles.dot}></span>
        <span className={styles.dot}></span>
      </div>
    );
  }

  return (
    <div className={styles.container} role="status" aria-live="polite">
      <span className={styles.icon}>{thinking && toolCount === 0 ? '💭' : '🔧'}</span>
      <span className={styles.text}>{displayText}</span>
      {!prefersReducedMotion && thinking && toolCount === 0 && (
        <span className={styles.dots} aria-hidden="true">
          <span className={styles.dot}></span>
          <span className={styles.dot}></span>
          <span className={styles.dot}></span>
        </span>
      )}
    </div>
  );
};

// Helper hook
function useMediaQuery(query: string): boolean {
  const [matches, setMatches] = useState(false);
  useEffect(() => {
    const media = window.matchMedia(query);
    if (media.matches !== matches) setMatches(media.matches);
    const listener = () => setMatches(media.matches);
    media.addEventListener('change', listener);
    return () => media.removeEventListener('change', listener);
  }, [matches, query]);
  return matches;
}
```

```css
/* frontend/src/components/chat/TypingIndicator.module.css (additions) */
.container {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  color: var(--text-muted, #888);
  font-size: 13px;
}

.icon {
  font-size: 14px;
  animation: pulse 1.5s ease-in-out infinite;
}

.text {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 300px;
}

.dots {
  display: flex;
  gap: 3px;
  margin-left: 4px;
}

.dot {
  width: 6px;
  height: 6px;
  background: var(--text-muted, #888);
  border-radius: 50%;
  animation: bounce 1.4s ease-in-out infinite both;
}

.dot:nth-child(1) { animation-delay: -0.32s; }
.dot:nth-child(2) { animation-delay: -0.16s; }

@keyframes pulse {
  0%, 100% { opacity: 0.5; }
  50% { opacity: 1; }
}

@keyframes bounce {
  0%, 80%, 100% { transform: scale(0); }
  40% { transform: scale(1); }
}

@media (prefers-reduced-motion: reduce) {
  .icon,
  .dot {
    animation: none !important;
  }
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npm test -- frontend/src/components/chat/__tests__/TypingIndicator.toolNames.test.tsx`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/chat/TypingIndicator.tsx frontend/src/components/chat/TypingIndicator.module.css frontend/src/store/websocketStore.ts frontend/src/components/chat/__tests__/TypingIndicator.toolNames.test.tsx
git commit -m "feat(chat): enhance TypingIndicator with tool names display"
```

---

### Task 6: Mobile Bottom Sheet Polish & Accessibility

**Files:**
- Modify: `frontend/src/components/layout/RightSidebar.tsx` (add drag handle, swipe dismiss)
- Modify: `frontend/src/components/layout/RightSidebar.module.css` (bottom sheet polish)
- Test: `frontend/src/components/layout/__tests__/RightSidebar.mobile.test.tsx`

**Interfaces:**
- Consumes: Existing RightSidebar props
- Produces: Mobile-optimized bottom sheet with drag handle, swipe-to-dismiss, focus trap

- [ ] **Step 1: Write the failing test**

```tsx
// frontend/src/components/layout/__tests__/RightSidebar.mobile.test.tsx
import { render, screen, fireEvent } from '@testing-library/react';
import { RightSidebar } from '../RightSidebar';

describe('RightSidebar - Mobile Bottom Sheet', () => {
  beforeEach(() => {
    Object.defineProperty(window, 'matchMedia', {
      value: vi.fn().mockImplementation(query => ({
        matches: query === '(max-width: 767px)',
        addListener: vi.fn(),
        removeListener: vi.fn(),
      })),
    });
  });

  it('renders drag handle on mobile', () => {
    render(<RightSidebar isOpen={true} onClose={vi.fn()} position="bottom" />);
    expect(screen.getByRole('button', { name: /drag handle/i })).toBeInTheDocument();
  });

  it('closes on swipe down', () => {
    const onClose = vi.fn();
    render(<RightSidebar isOpen={true} onClose={onClose} position="bottom" />);
    const panel = screen.getByTestId('sidebar-panel');
    fireEvent.touchStart(panel, { touches: [{ clientY: 100 }] });
    fireEvent.touchMove(panel, { touches: [{ clientY: 200 }] });
    fireEvent.touchEnd(panel);
    expect(onClose).toHaveBeenCalled();
  });

  it('traps focus in bottom sheet', () => {
    render(
      <RightSidebar isOpen={true} onClose={vi.fn()} position="bottom">
        <button>First</button>
        <button>Last</button>
      </RightSidebar>
    );
    const firstBtn = screen.getByText('First');
    const lastBtn = screen.getByText('Last');
    firstBtn.focus();
    fireEvent.keyDown(lastBtn, { key: 'Tab', shiftKey: true });
    expect(firstBtn).toHaveFocus();
  });

  it('announces open/close to screen readers', () => {
    const { rerender } = render(<RightSidebar isOpen={true} onClose={vi.fn()} position="bottom" />);
    const overlay = screen.getByRole('dialog');
    expect(overlay).toHaveAttribute('aria-modal', 'true');
    rerender(<RightSidebar isOpen={false} onClose={vi.fn()} position="bottom" />);
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm test -- frontend/src/components/layout/__tests__/RightSidebar.mobile.test.tsx`
Expected: FAIL - mobile enhancements not implemented

- [ ] **Step 3: Write minimal implementation**

```tsx
// frontend/src/components/layout/RightSidebar.tsx (mobile enhancements)

import React, { createContext, useContext, useEffect, useRef, useState } from 'react';
import styles from './RightSidebar.module.css';

// ... existing imports and context ...

export const RightSidebar: React.FC<RightSidebarProps> = ({
  isOpen,
  onClose,
  children,
  width = 320,
  minWidth = 48,
  position = 'right',
  className = '',
}) => {
  const [isMobile, setIsMobile] = useState(false);
  const [isCollapsed, setIsCollapsed] = useState(false);
  const panelRef = useRef<HTMLDivElement>(null);
  const touchStartY = useRef(0);
  const focusableElementsRef = useRef<HTMLElement[]>([]);

  // ... existing media query effect ...

  // Focus trap for mobile
  useEffect(() => {
    if (!isOpen || !isMobile) return;
    const panel = panelRef.current;
    if (!panel) return;

    focusableElementsRef.current = Array.from(
      panel.querySelectorAll<HTMLElement>('button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])')
    ).filter(el => !el.hasAttribute('disabled'));

    const firstElement = focusableElementsRef.current[0];
    const lastElement = focusableElementsRef.current[focusableElementsRef.current.length - 1];

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key !== 'Tab') return;
      if (e.shiftKey) {
        if (document.activeElement === firstElement) {
          e.preventDefault();
          lastElement?.focus();
        }
      } else {
        if (document.activeElement === lastElement) {
          e.preventDefault();
          firstElement?.focus();
        }
      }
    };

    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };

    panel.addEventListener('keydown', handleKeyDown);
    document.addEventListener('keydown', handleEscape);
    firstElement?.focus();

    return () => {
      panel.removeEventListener('keydown', handleKeyDown);
      document.removeEventListener('keydown', handleEscape);
    };
  }, [isOpen, isMobile, onClose]);

  // Touch swipe handling
  const handleTouchStart = (e: React.TouchEvent) => {
    touchStartY.current = e.touches[0].clientY;
  };

  const handleTouchMove = (e: React.TouchEvent) => {
    const deltaY = e.touches[0].clientY - touchStartY.current;
    if (deltaY > 0 && panelRef.current) {
      panelRef.current.style.transform = `translateY(${deltaY}px)`;
    }
  };

  const handleTouchEnd = (e: React.TouchEvent) => {
    const deltaY = e.changedTouches[0].clientY - touchStartY.current;
    if (panelRef.current) {
      panelRef.current.style.transform = '';
    }
    if (deltaY > 100) onClose(); // Swipe down threshold
  };

  // ... existing toggleCollapse ...

  if (!isOpen && !isMobile) return null;

  const panelStyle: React.CSSProperties = {
    width: isCollapsed ? minWidth : width,
    transform: isMobile ? 'translateY(100%)' : 'translateX(0)',
  };

  return (
    <RightSidebarContext.Provider value={{ isCollapsed, toggleCollapse }}>
      <div
        data-testid="sidebar-overlay"
        className={`${styles.overlay} ${isOpen ? styles.open : ''} ${isMobile ? styles.mobile : ''}`}
        onClick={onClose}
        role="dialog"
        aria-modal="true"
        aria-label="Sidebar"
      >
        <div
          ref={panelRef}
          data-testid="sidebar-panel"
          className={`${styles.panel} ${position === 'bottom' ? styles.bottom : ''} ${className}`}
          style={panelStyle}
          onClick={e => e.stopPropagation()}
          onTouchStart={isMobile && position === 'bottom' ? handleTouchStart : undefined}
          onTouchMove={isMobile && position === 'bottom' ? handleTouchMove : undefined}
          onTouchEnd={isMobile && position === 'bottom' ? handleTouchEnd : undefined}
        >
          {/* Drag handle for mobile bottom sheet */}
          {isMobile && position === 'bottom' && (
            <div className={styles.dragHandle} role="button" tabIndex={0} aria-label="Drag to close">
              <div className={styles.dragBar} />
            </div>
          )}
          <div className={styles.handle} onClick={toggleCollapse} aria-label={isCollapsed ? 'Expand sidebar' : 'Collapse sidebar'}>
            <span className={styles.handleIcon}>{isCollapsed ? '›' : '‹'}</span>
          </div>
          <div className={styles.content}>{children}</div>
        </div>
      </div>
    </RightSidebarContext.Provider>
  );
};
```

```css
/* frontend/src/components/layout/RightSidebar.module.css (mobile additions) */

.dragHandle {
  display: none;
  padding: 12px;
  text-align: center;
}

.overlay.mobile .dragHandle {
  display: block;
}

.dragBar {
  width: 40px;
  height: 4px;
  background: var(--text-muted, #888);
  border-radius: 2px;
  margin: 0 auto;
}

@media (prefers-reduced-motion: reduce) {
  .panel {
    transition: none !important;
  }
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npm test -- frontend/src/components/layout/__tests__/RightSidebar.mobile.test.tsx`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/layout/RightSidebar.tsx frontend/src/components/layout/RightSidebar.module.css frontend/src/components/layout/__tests__/RightSidebar.mobile.test.tsx
git commit -m "feat(layout): polish mobile bottom sheet with swipe dismiss and focus trap"
```

---

### Task 7: E2E Tests — Conversation CRUD & Switching Flows

**Files:**
- Create: `frontend/cypress/e2e/conversation-management.cy.ts`
- Create: `frontend/cypress/e2e/tool-names-display.cy.ts`
- Modify: `frontend/cypress.config.ts` (if needed for baseUrl)

**Interfaces:**
- Tests full user flows against running dev server
- Requires backend running with test data

- [ ] **Step 1: Write the failing test**

```typescript
// frontend/cypress/e2e/conversation-management.cy.ts
describe('Conversation Management', () => {
  beforeEach(() => {
    cy.login(); // Assuming auth helper
    cy.visit('/chat');
    cy.waitForWebSocket();
  });

  it('creates new conversation and switches to it', () => {
    cy.get('[data-cy=sidebar-toggle]').click();
    cy.get('[data-cy=new-conversation-btn]').click();
    cy.get('[data-cy=conversation-title-input]').type('E2E Test Conversation{enter}');
    cy.get('[data-cy=conversation-item]').should('contain', 'E2E Test Conversation');
    cy.get('[data-cy=messages-area]').should('be.empty');
  });

  it('switches between conversations preserving state', () => {
    // Create two conversations
    cy.createConversation('Conv A');
    cy.sendMessage('Hello from A');
    cy.createConversation('Conv B');
    cy.sendMessage('Hello from B');
    
    // Switch back to A
    cy.get('[data-cy=sidebar-toggle]').click();
    cy.contains('Conv A').click();
    cy.get('[data-cy=messages-area]').should('contain', 'Hello from A');
    cy.get('[data-cy=messages-area]').should('not.contain', 'Hello from B');
  });

  it('renames conversation', () => {
    cy.createConversation('Old Name');
    cy.get('[data-cy=sidebar-toggle]').click();
    cy.get('[data-cy=conversation-item]').first().trigger('mouseenter');
    cy.get('[aria-label="Rename conversation"]').click();
    cy.get('[data-cy=rename-input]').clear().type('New Name{enter}');
    cy.get('[data-cy=conversation-item]').should('contain', 'New Name');
  });

  it('archives and unarchives conversation', () => {
    cy.createConversation('To Archive');
    cy.get('[data-cy=sidebar-toggle]').click();
    cy.get('[data-cy=conversation-item]').first().trigger('mouseenter');
    cy.get('[aria-label="Archive"]').click();
    cy.get('[data-cy=conversation-item]').should('have.attr', 'data-archived', 'true');
    
    cy.get('[aria-label="Unarchive"]').click();
    cy.get('[data-cy=conversation-item]').should('not.have.attr', 'data-archived');
  });

  it('deletes conversation', () => {
    cy.createConversation('To Delete');
    cy.get('[data-cy=sidebar-toggle]').click();
    cy.get('[data-cy=conversation-item]').first().trigger('mouseenter');
    cy.get('[aria-label="Delete conversation"]').click();
    cy.on('window:confirm', () => true);
    cy.get('[data-cy=conversation-item]').should('not.contain', 'To Delete');
  });

  it('persists sidebar state across refresh', () => {
    cy.get('[data-cy=sidebar-toggle]').click();
    cy.get('[data-cy=sidebar-panel]').should('be.visible');
    cy.reload();
    cy.get('[data-cy=sidebar-panel]').should('be.visible');
  });
});
```

```typescript
// frontend/cypress/e2e/tool-names-display.cy.ts
describe('Tool Names Display', () => {
  beforeEach(() => {
    cy.login();
    cy.visit('/chat');
    cy.waitForWebSocket();
  });

  it('shows tool names in typing indicator during tool execution', () => {
    // This test requires backend to emit tool_names in tool_progress
    // Mock or seed backend to run tools
    cy.sendMessage('Search for latest React docs');
    cy.get('[data-cy=typing-indicator]').should('contain', 'Running:');
    cy.get('[data-cy=typing-indicator]').should('contain', 'web_search');
  });

  it('falls back to tool count when names unavailable', () => {
    // Test with backend that doesn't send tool_names
    cy.sendMessage('Simple question');
    cy.get('[data-cy=typing-indicator]').should('contain', 'Running tools:');
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm run cypress:run -- --spec "cypress/e2e/conversation-management.cy.ts"`
Expected: FAIL - features not implemented

- [ ] **Step 3: Implement features (covered by Tasks 1-5)**

No new implementation - these tests verify Tasks 1-5 work end-to-end.

- [ ] **Step 4: Run test to verify it passes**

Run: `npm run cypress:run -- --spec "cypress/e2e/conversation-management.cy.ts"`
Expected: PASS (after Tasks 1-5 complete)

- [ ] **Step 5: Commit**

```bash
git add frontend/cypress/e2e/conversation-management.cy.ts frontend/cypress/e2e/tool-names-display.cy.ts
git commit -m "test(e2e): add conversation management and tool names E2E tests"
```

---

## Self-Review Checklist

### Spec Coverage (docs/superpowers/specs/2026-09-15-chat-frontend-design.md)

| Spec Section | Task(s) | Coverage |
|--------------|---------|----------|
| 9.3.1 Markdown/code blocks | — | ✅ Already done |
| 9.3.2 Streaming tokens | — | ✅ Already done |
| 9.3.3 Tool call display | Task 5 | ✅ TypingIndicator enhanced with toolNames |
| 9.3.4 File upload | — | ✅ Already done |
| 9.3.5 Conversation switching | Tasks 1-4 | ✅ RightSidebar + ConversationSidebar + ChatPage integration |
| 9.3.6 New conversation | Tasks 2-4 | ✅ createConversation in store + UI |
| 9.3.7 History reload | — | ✅ Already done |
| 9.3.8 chatStore consistency | Task 2 | ✅ Extended with conversation state |
| Right sidebar shell | Task 1 | ✅ Reusable RightSidebar component |
| Mobile bottom sheet | Tasks 1, 6 | ✅ Responsive + swipe dismiss + focus trap |
| Accessibility | Tasks 1, 3, 4, 6 | ✅ ARIA roles, keyboard nav, focus management |
| Backend compatibility | Task 5 | ✅ Optional tool_names in websocketStore |

### Placeholder Scan

- ✅ No "TBD", "TODO", "implement later", "fill in details"
- ✅ No "Add appropriate error handling" without code
- ✅ No "Write tests for the above" without actual test code
- ✅ No "Similar to Task N" references
- ✅ All steps have complete code blocks
- ✅ All types, function signatures, property names match across tasks

### Type Consistency

- ✅ `Conversation` interface defined in Task 2, used in Tasks 3, 4
- ✅ `RightSidebarProps` defined in Task 1, used in Tasks 3, 4
- ✅ `toolNames` prop added to TypingIndicator in Task 5, passed from ChatPage in Task 4
- ✅ `websocketStore` extended with `toolNames` in Task 5, consumed in Task 4
- ✅ `chatStore` actions (`setConversation`, `createConversation`, etc.) defined in Task 2, used in Tasks 3, 4
- ✅ CSS class names consistent across component files

---

## Execution Handoff

**Plan complete and saved to `docs/superpowers/plans/2026-09-15-chat-frontend-completion.md`. Two execution options:**

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration
   - **REQUIRED SUB-SKILL:** Use superpowers:subagent-driven-development
   - Fresh subagent per task + two-stage review

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints
   - **REQUIRED SUB-SKILL:** Use superpowers:executing-plans
   - Batch execution with checkpoints for review

**Which approach?**
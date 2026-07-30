// frontend/src/pages/ChatPage.a11y.browser.test.tsx
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import { auditRoute } from '@/test/a11yBrowser';
import { ChatPage } from '@/pages/ChatPage';
import { useAuthStore } from '@/store/authStore';
import { useWebSocketStore } from '@/store/websocketStore';
import { useChatStore } from '@/store/chatStore';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ReactNode } from 'react';

function formatViolations(violations: any[]) {
  return violations.map((v: any) => ({
    id: v.id,
    impact: v.impact,
    description: v.description,
    helpUrl: v.helpUrl,
    nodes: v.nodes.map((n: any) => ({
      html: n.html,
      target: n.target,
      impact: n.impact,
      any: n.any,
    })),
  }));
}

// Mock all API services used by ChatPage and its components
vi.mock('@/services/inboxApi', () => ({
  inboxApi: {
    getConversations: vi.fn().mockResolvedValue([]),
    getMessages: vi.fn().mockResolvedValue([]),
    sendMessage: vi.fn().mockResolvedValue({}),
    createConversation: vi.fn().mockResolvedValue({}),
    updateConversation: vi.fn().mockResolvedValue({}),
    deleteConversation: vi.fn().mockResolvedValue({}),
  },
}));

vi.mock('@/services/api', () => ({
  api: vi.fn().mockImplementation(() => Promise.resolve({ data: {} })),
  rawFetch: vi.fn().mockResolvedValue({}),
}));

vi.mock('@/services/fileApi', () => ({
  fileApi: {
    uploadFile: vi.fn().mockResolvedValue({}),
    getUploadUrl: vi.fn().mockResolvedValue({}),
  },
}));

vi.mock('@/services/voiceApi', () => ({
  voiceApi: {
    startRecording: vi.fn().mockResolvedValue({}),
    stopRecording: vi.fn().mockResolvedValue({}),
    getTranscription: vi.fn().mockResolvedValue({}),
  },
}));

vi.mock('@/services/chatApi', () => ({
  chatApi: {
    sendMessage: vi.fn().mockResolvedValue({}),
    streamMessage: vi.fn().mockResolvedValue({}),
  },
}));

vi.mock('@/services/localVoice', () => ({
  localVoice: {
    start: vi.fn(),
    stop: vi.fn(),
  },
}));

vi.mock('@/services/voiceBridge', () => ({
  voiceBridgeService: {
    connect: vi.fn().mockResolvedValue(undefined),
    disconnect: vi.fn(),
    sendEvent: vi.fn(),
    onEvent: vi.fn(),
    onInteraction: vi.fn(() => () => {}),
    onStatusChange: vi.fn((cb) => {
      cb('offline');
      return () => {};
    }),
    onStateChange: vi.fn(() => () => {}),
    onErrorChange: vi.fn(() => () => {}),
    status: 'offline',
    connectionError: null,
    setVoiceMode: vi.fn(),
  },
}));

describe('ChatPage color-contrast', () => {
  beforeEach(() => {
    useAuthStore.setState({
      user: { isAuthenticated: true, username: 'test', is_admin: false, isSovereign: false },
      isLoading: false,
    });
    useWebSocketStore.setState({
      connectionPhase: 'active',
      isConnected: true,
      error: null,
      connectionStats: { latencyMs: 50 },
      unreadCount: 0,
      messageHistory: [],
      lastMessage: null,
      genesisJustCompleted: false,
    } as any);
    useChatStore.setState({
      messages: [],
      activeStreamId: null,
      isAwaitingReply: false,
      isThinking: false,
      toolCount: 0,
      conversations: [],
      selectedId: null,
      inboxLoading: false,
      replyContent: '',
      isSending: false,
    } as any);
  });

  const renderWithQueryClient = (ui: ReactNode) => {
    const queryClient = new QueryClient({
      defaultOptions: {
        queries: { retry: false },
      },
    });
    return <QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>;
  };

  it('passes in light theme', async () => {
    const result = await auditRoute(
      <MemoryRouter>{renderWithQueryClient(<ChatPage />)}</MemoryRouter>,
      'light'
    );
    if (result.violations.length > 0) {
      console.log('=== LIGHT THEME VIOLATIONS ===');
      console.log(JSON.stringify(formatViolations(result.violations), null, 2));
    }
    expect(result).toHaveNoViolations();
  });

  it('passes in dark theme', async () => {
    const result = await auditRoute(
      <MemoryRouter>{renderWithQueryClient(<ChatPage />)}</MemoryRouter>,
      'dark'
    );
    if (result.violations.length > 0) {
      console.log('=== DARK THEME VIOLATIONS ===');
      console.log(JSON.stringify(formatViolations(result.violations), null, 2));
    }
    expect(result).toHaveNoViolations();
  });
});
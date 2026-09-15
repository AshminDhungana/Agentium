import { act } from '@testing-library/react';
import { useChatStore } from '../chatStore';
import { chatApi } from '../../services/chatApi';

vi.mock('../../services/chatApi');

// Mock localStorage and sessionStorage
const localStorageMock = (() => {
  let store: Record<string, string> = {};
  return {
    getItem: (key: string) => store[key] || null,
    setItem: (key: string, value: string) => { store[key] = value; },
    removeItem: (key: string) => { delete store[key]; },
    clear: () => { store = {}; },
  };
})();

const sessionStorageMock = (() => {
  let store: Record<string, string> = {};
  return {
    getItem: (key: string) => store[key] || null,
    setItem: (key: string, value: string) => { store[key] = value; },
    removeItem: (key: string) => { delete store[key]; },
    clear: () => { store = {}; },
  };
})();

Object.defineProperty(window, 'localStorage', { value: localStorageMock });
Object.defineProperty(window, 'sessionStorage', { value: sessionStorageMock });

describe('chatStore - conversations', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorageMock.clear();
    sessionStorageMock.clear();
    useChatStore.getState().clearHistory();
    useChatStore.setState({
      currentConversationId: null,
      conversations: [],
      isSidebarOpen: false,
      sidebarWidth: 320,
    });
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
    vi.mocked(chatApi.listConversations).mockResolvedValue({ conversations: [mockConversation], total: 1 });
    
    await act(async () => {
      await useChatStore.getState().loadConversations();
    });

    expect(useChatStore.getState().conversations).toEqual([
      { ...mockConversation, last_message_preview: undefined }
    ]);
    expect(chatApi.listConversations).toHaveBeenCalled();
  });

  it('setConversation loads messages and sets currentConversationId', async () => {
    const mockMessages = [
      { id: 'msg-1', role: 'sovereign', content: 'Hi', timestamp: new Date().toISOString() },
      { id: 'msg-2', role: 'head_of_council', content: 'Hello!', timestamp: new Date().toISOString() },
    ];
    vi.mocked(chatApi.getConversation).mockResolvedValue({ ...mockConversation, messages: mockMessages });

    await act(async () => {
      await useChatStore.getState().setConversation('conv-1');
    });

    expect(useChatStore.getState().currentConversationId).toBe('conv-1');
    expect(useChatStore.getState().messages.length).toBe(2);
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
    vi.mocked(chatApi.listConversations).mockResolvedValue({ conversations: [mockConversation], total: 1 });
    await act(async () => {
      await useChatStore.getState().loadConversations();
    });
    vi.mocked(chatApi.deleteConversation).mockResolvedValue({ success: true });

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
    expect(sessionStorageMock.getItem('chat:currentConversationId')).toBe('conv-1');
  });

  it('updateConversation updates title', async () => {
    vi.mocked(chatApi.listConversations).mockResolvedValue({ conversations: [mockConversation], total: 1 });
    await act(async () => {
      await useChatStore.getState().loadConversations();
    });
    vi.mocked(chatApi.updateConversation).mockResolvedValue({ ...mockConversation, title: 'Updated Title' });

    await act(async () => {
      await useChatStore.getState().updateConversation('conv-1', { title: 'Updated Title' });
    });

    expect(useChatStore.getState().conversations[0].title).toBe('Updated Title');
  });
});
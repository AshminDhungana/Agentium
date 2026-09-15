import { create } from 'zustand';
import { persist, createJSONStorage } from 'zustand/middleware';
import { showToast } from '@/hooks/useToast';
import { api } from '@/services/api';
import { chatStreamApi } from '@/services/chatStream';
import type { StructuredInputCardPayload } from '../types/structuredInput';
import { chatApi, type Conversation as ApiConversation } from '@/services/chatApi';

export interface MessageAttachment {
    name: string;
    type: string;
    size: number;
    url?: string;
    data?: string;
    category?: string;
}

export interface MessageMetadata {
    agent_used?: string;
    agent_id?: string;
    model?: string;
    latency_ms?: number;
    task_created?: boolean;
    task_id?: string;
    tokens_used?: number;
    /** 'voice' when message originated from the voice bridge */
    source?: string;
    /** True when the message bubble should render in error styling */
    error?: boolean;
    connection_id?: number;
    /** structured input card payload (replaces prompt_type/requires_response) */
    card?: StructuredInputCardPayload;
    /** True when older turns were compressed/summarized to save tokens (Task 2.1) */
    context_compressed?: boolean;
    /** Total raw turns in the conversation before windowing (for transparency) */
    raw_turn_count?: number;
    /** Estimated tokens sent to the model this turn (Task 2.1) */
    estimated_tokens?: number;
}

export interface Message {
    id: string;
    role: 'sovereign' | 'head_of_council' | 'system';
    content: string;
    timestamp: Date;
    status?: 'sending' | 'sent' | 'error' | 'streaming';
    metadata?: MessageMetadata;
    attachments?: MessageAttachment[];
}

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
    messages: Message[];
    isLoading: boolean;
    currentStreamingMessage: string;
    cardStatus: Record<string, 'active' | 'confirmed' | 'expired' | 'dismissed'>;
    activeCardId: string | null;
    activeStreamId: string | null;
    _streamBuffer: string;
    _streamFlushTimer: ReturnType<typeof setInterval> | null;

    // NEW: Conversation state
    currentConversationId: string | null;
    conversations: Conversation[];
    isSidebarOpen: boolean;
    sidebarWidth: number;

    registerCard: (cardId: string, replaceActive: boolean) => void;
    confirmCard: (cardId: string) => void;
    expireCard: (cardId: string) => void;
    dismissCard: (cardId: string) => void;
    beginStream: (messageId: string, role: Message['role']) => void;
    appendDelta: (streamId: string, delta: string) => void;
    endStream: (streamId: string, content: string, metadata?: MessageMetadata) => void;
    resetStream: () => void;
    _startFlush: (streamId: string) => void;
    _stopFlush: () => void;
    sendMessage: (content: string) => Promise<void>;
    setMessages: (updater: Message[] | ((prev: Message[]) => Message[])) => void;
    clearHistory: () => void;
    loadHistory: () => Promise<void>;

    // NEW: Conversation actions
    setConversation: (conversationId: string) => Promise<void>;
    createConversation: (title?: string) => Promise<string>;
    loadConversations: () => Promise<void>;
    deleteConversation: (conversationId: string) => Promise<void>;
    updateConversation: (conversationId: string, updates: { title?: string; is_archived?: boolean }) => Promise<void>;
    toggleSidebar: () => void;
    setSidebarWidth: (width: number) => void;
}

const STORAGE_KEY = 'agentium-chat-messages';
const CONVERSATION_ID_KEY = 'chat:currentConversationId';
const SIDEBAR_WIDTH_KEY = 'chat:sidebar:width';
const SIDEBAR_OPEN_KEY = 'chat:sidebar:open';

export const useChatStore = create<ChatState>()(
    persist(
        (set, get) => ({
            messages: [],
            isLoading: false,
            currentStreamingMessage: '',
            activeStreamId: null,
            cardStatus: {},
            activeCardId: null,
            _streamBuffer: '',
            _streamFlushTimer: null,

            // NEW initial state
            currentConversationId: null,
            conversations: [],
            isSidebarOpen: false,
            sidebarWidth: 320,

            registerCard: (cardId, replaceActive) => set((s) => {
                if (s.cardStatus[cardId]) return s;
                const status: ChatState['cardStatus'] = { ...s.cardStatus, [cardId]: 'active' as const };
                if (replaceActive && s.activeCardId && s.activeCardId !== cardId) {
                    status[s.activeCardId] = 'dismissed';
                }
                return { cardStatus: status, activeCardId: cardId };
            }),
            confirmCard: (cardId) => set((s) => ({
                cardStatus: { ...s.cardStatus, [cardId]: 'confirmed' },
                activeCardId: s.activeCardId === cardId ? null : s.activeCardId,
            })),
            expireCard: (cardId) => set((s) => {
                if (s.cardStatus[cardId] === 'confirmed' || s.cardStatus[cardId] === 'dismissed') {
                    return s;
                }
                return {
                    cardStatus: { ...s.cardStatus, [cardId]: 'expired' },
                    activeCardId: s.activeCardId === cardId ? null : s.activeCardId,
                };
            }),
            dismissCard: (cardId) => set((s) => ({
                cardStatus: { ...s.cardStatus, [cardId]: 'dismissed' },
                activeCardId: s.activeCardId === cardId ? null : s.activeCardId,
            })),

            beginStream: (messageId, role) => {
                get()._stopFlush();
                set((s) => ({
                    activeStreamId: messageId,
                    messages: [
                        ...s.messages,
                        { id: messageId, role, content: '', timestamp: new Date(), status: 'streaming' },
                    ],
                    currentStreamingMessage: '',
                    _streamBuffer: '',
                }));
            },

            appendDelta: (streamId, delta) => {
                if (
                    typeof window !== 'undefined' &&
                    window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
                ) {
                    set((s) => ({
                        currentStreamingMessage: s.currentStreamingMessage + delta,
                        messages: s.messages.map((m) =>
                            m.id === streamId ? { ...m, content: m.content + delta } : m),
                    }));
                    return;
                }
                set({ _streamBuffer: get()._streamBuffer + delta });
                get()._startFlush(streamId);
            },

            _startFlush: (streamId) => {
                if (get()._streamFlushTimer != null) return;
                const timer = setInterval(() => {
                    const pending = get()._streamBuffer;
                    if (!pending) { get()._stopFlush(); return; }
                    const slice = pending.length > 120 ? pending.length : Math.min(pending.length, 6);
                    const take = pending.slice(0, slice);
                    const rest = pending.slice(slice);
                    set((s) => ({
                        _streamBuffer: rest,
                        currentStreamingMessage: s.currentStreamingMessage + take,
                        messages: s.messages.map((m) =>
                            m.id === streamId ? { ...m, content: m.content + take } : m),
                    }));
                    if (!rest) get()._stopFlush();
                }, 40);
                set({ _streamFlushTimer: timer });
            },

            _stopFlush: () => {
                const t = get()._streamFlushTimer;
                if (t != null) {
                    clearInterval(t);
                    set({ _streamFlushTimer: null });
                }
            },

            resetStream: () => {
                get()._stopFlush();
                const s = get();
                const id = s.activeStreamId;
                if (!id) return;
                const buffered = s._streamBuffer || '';
                set((st) => ({
                    activeStreamId: null,
                    currentStreamingMessage: '',
                    _streamBuffer: '',
                    messages: st.messages.map((m) =>
                        m.id === id
                            ? { ...m, content: m.content + buffered, status: 'sent' }
                            : m),
                }));
            },

            endStream: (streamId, content, metadata) => {
                get()._stopFlush();
                set((s) => {
                    const localContent = s.messages.find((m) => m.id === streamId)?.content ?? '';
                    const finalContent = content || (localContent + (s._streamBuffer || ''));
                    return {
                        activeStreamId: s.activeStreamId === streamId ? null : s.activeStreamId,
                        currentStreamingMessage: '',
                        _streamBuffer: '',
                        messages: s.messages.map((m) =>
                            m.id === streamId
                                ? { ...m, content: finalContent, status: 'sent', metadata: { ...m.metadata, ...metadata } }
                                : m),
                    };
                });
            },

            setMessages: (updater) =>
                set((state) => ({
                    messages: typeof updater === 'function'
                        ? updater(state.messages)
                        : updater,
                })),

            sendMessage: async (content: string) => {
                const userMessage: Message = {
                    id: crypto.randomUUID(),
                    role: 'sovereign',
                    content,
                    timestamp: new Date(),
                    status: 'sent'
                };

                set((state) => ({
                    messages: [...state.messages, userMessage],
                    isLoading: true,
                    currentStreamingMessage: ''
                }));

                try {
                    const response = await chatStreamApi.sendMessage(content);

                    const assistantMessage: Message = {
                        id: crypto.randomUUID(),
                        role: 'head_of_council',
                        content: response.response || response.content || 'No response',
                        timestamp: new Date(),
                        status: 'sent',
                        metadata: {
                            agent_used: response.agent_id,
                            model: response.model,
                            task_created: response.task_created,
                            task_id: response.task_id
                        }
                    };

                    set((state) => ({
                        messages: [...state.messages, assistantMessage],
                        isLoading: false,
                        currentStreamingMessage: ''
                    }));
                } catch (error: any) {
                    console.error('Chat error:', error);

                    const errorMessage: Message = {
                        id: crypto.randomUUID(),
                        role: 'system',
                        content: `Failed to reach Head of Council: ${error instanceof Error ? error.message : 'Unknown error'}`,
                        timestamp: new Date(),
                        status: 'error'
                    };

                    set((state) => ({
                        messages: [...state.messages, errorMessage],
                        isLoading: false,
                        currentStreamingMessage: ''
                    }));

                    showToast.error('Failed to send message');
                }
            },

            loadHistory: async () => {
                try {
                    const response = await api.get('/api/v1/chat/history?limit=50');
                    const historyMessages = response.data.messages || [];
                    
                    const formattedMessages: Message[] = historyMessages.map((msg: any) => ({
                        id: msg.id || crypto.randomUUID(),
                        role: msg.role || 'head_of_council',
                        content: msg.content || '',
                        timestamp: new Date(msg.timestamp),
                        metadata: msg.metadata
                    }));

                    set({ messages: formattedMessages });
                } catch (error) {
                    console.error('Failed to load chat history:', error);
                }
            },

            clearHistory: () => {
                set({ messages: [], currentStreamingMessage: '' });
            },

            // NEW: Conversation actions
            setConversation: async (conversationId: string) => {
                const { resetStream } = get();
                resetStream();
                set({ isLoading: true });
                
                try {
                    const response = await chatApi.getConversation(conversationId);
                    const messages = response.messages?.map((m: any) => ({
                        id: m.id,
                        role: m.role,
                        content: m.content,
                        timestamp: new Date(m.created_at || m.timestamp),
                        status: 'sent' as const,
                        attachments: m.attachments,
                        metadata: m.metadata,
                    })) || [];
                    
                    set({ 
                        messages, 
                        currentConversationId: conversationId,
                        isSidebarOpen: false,
                        isLoading: false,
                    });
                    sessionStorage.setItem(CONVERSATION_ID_KEY, conversationId);
                } catch (error) {
                    console.error('Failed to load conversation:', error);
                    set({ isLoading: false });
                    throw error;
                }
            },

            createConversation: async (title?: string) => {
                try {
                    const response = await chatApi.createConversation(title || 'New Conversation');
                    const newConv: Conversation = {
                        id: response.id,
                        title: response.title || 'New Conversation',
                        is_archived: false,
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
                    const response = await chatApi.listConversations();
                    const conversations: Conversation[] = response.conversations.map((c: ApiConversation) => ({
                        id: c.id,
                        title: c.title || 'Untitled',
                        is_archived: false,
                        created_at: c.created_at,
                        updated_at: c.updated_at,
                        message_count: c.message_count || 0,
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
                    const updatePayload: { title?: string; context?: string } = {};
                    if (updates.title !== undefined) updatePayload.title = updates.title;
                    if (updates.is_archived !== undefined) {
                        // Note: backend uses archiveConversation endpoint for archiving
                        if (updates.is_archived) {
                            await chatApi.archiveConversation(conversationId);
                        }
                    }
                    if (updates.title !== undefined) {
                        await chatApi.updateConversation(conversationId, { title: updates.title });
                    }
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
                if (newOpen) get().loadConversations();
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
                messages: state.messages,
                currentConversationId: state.currentConversationId,
            }),
            onRehydrateStorage: () => (state) => {
                if (!state) return;
                state.messages = state.messages.map((m: any) =>
                    m.status === 'streaming' ? { ...m, status: 'sent' } : m);
                state.activeStreamId = null;
                state.currentStreamingMessage = '';
                state._streamBuffer = '';
                state._streamFlushTimer = null;
                // Rehydrate sidebar state from localStorage
                const savedWidth = localStorage.getItem(SIDEBAR_WIDTH_KEY);
                const savedOpen = localStorage.getItem(SIDEBAR_OPEN_KEY);
                if (savedWidth) state.sidebarWidth = parseInt(savedWidth, 10);
                if (savedOpen) state.isSidebarOpen = savedOpen === 'true';
            },
        }
    )
);
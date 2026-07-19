import { create } from 'zustand';
import { persist, createJSONStorage } from 'zustand/middleware';
import { showToast } from '@/hooks/useToast';
import { api } from '@/services/api';
import { chatStreamApi } from '@/services/chatStream';
import type { StructuredInputCardPayload } from '../types/structuredInput';

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

interface ChatState {
    messages: Message[];
    isLoading: boolean;
    currentStreamingMessage: string;
    // Structured input card lifecycle (only one active card at a time).
    cardStatus: Record<string, 'active' | 'confirmed' | 'expired' | 'dismissed'>;
    activeCardId: string | null;
    registerCard: (cardId: string, replaceActive: boolean) => void;
    confirmCard: (cardId: string) => void;
    expireCard: (cardId: string) => void;
    dismissCard: (cardId: string) => void;
    activeStreamId: string | null;
    beginStream: (messageId: string, role: Message['role']) => void;
    appendDelta: (streamId: string, delta: string) => void;
    endStream: (streamId: string, content: string, metadata?: MessageMetadata) => void;
    /**
     * Finalize an in-flight stream that was interrupted (e.g. the WebSocket
     * dropped before a `message_end` arrived). Keeps whatever text was already
     * revealed, marks the message `sent`, and clears `activeStreamId` so the
     * Stop button and blinking caret don't get stuck.
     */
    resetStream: () => void;
    /**
     * Buffer of delta text not yet flushed to the rendered message. Flushed in
     * small slices on a timer so the reply reveals at a readable pace instead of
     * popping in as fast as the backend emits deltas.
     */
    _streamBuffer: string;
    _streamFlushTimer: ReturnType<typeof setInterval> | null;
    _startFlush: (streamId: string) => void;
    _stopFlush: () => void;
    sendMessage: (content: string) => Promise<void>;
    setMessages: (updater: Message[] | ((prev: Message[]) => Message[])) => void;
    clearHistory: () => void;
    loadHistory: () => Promise<void>;
}

// All chat API calls are now routed through chatStreamApi service.

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

            registerCard: (cardId, replaceActive) => set((s) => {
                // Idempotent: a re-delivered card message (e.g. on WS reconnect)
                // must not revert an already-answered/expired one back to active.
                if (s.cardStatus[cardId]) return s;
                const status: ChatState['cardStatus'] = { ...s.cardStatus, [cardId]: 'active' as const };
                // "only one active card at a time": a new request replaces any unanswered one
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
                // Defense-in-depth: never flip an already answered/dismissed card
                // back to expired even if a stale timer fires after confirmation.
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

            // Streaming helpers: drive server-pushed token deltas into a single message.
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
                // Honour reduced-motion: reveal immediately, no pacing.
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
                // Otherwise buffer and reveal in paced slices.
                set({ _streamBuffer: get()._streamBuffer + delta });
                get()._startFlush(streamId);
            },

            _startFlush: (streamId) => {
                if (get()._streamFlushTimer != null) return; // already running
                const timer = setInterval(() => {
                    const pending = get()._streamBuffer;
                    if (!pending) { get()._stopFlush(); return; }
                    // Reveal a small slice normally, but catch up instantly if a
                    // large backlog has built up so we never lag far behind.
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
                    // Prefer the authoritative server content; fall back to what
                    // we have locally (revealed text + any still-buffered text).
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

                    // Add assistant message
                    const assistantMessage: Message = {
                        id: crypto.randomUUID(),
                        role: 'head_of_council',
                        content: response.response || response.content || 'No response',
                        timestamp: new Date(),
                        status: 'sent',
                        metadata: {
                            agent_used: response.agent_id,
                            model: response.model
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
                    // Don't show error toast - history is optional
                }
            },

            clearHistory: () => {
                set({ messages: [], currentStreamingMessage: '' });
            }
        }),
        {
            name: 'agentium-chat-messages',  // sessionStorage key
            storage: createJSONStorage(() => sessionStorage, {
                // Rehydrate timestamp strings back to Date objects
                reviver: (key, value) => {
                    if (key === 'timestamp' && typeof value === 'string') {
                        return new Date(value);
                    }
                    return value;
                },
            }),
            // Only persist messages — skip transient loading/streaming state
            partialize: (state) => ({ messages: state.messages }),
            // A stream interrupted by a reload/crash would otherwise rehydrate
            // with status 'streaming' and blink its caret forever. Finalize any
            // such message and clear transient stream fields on load.
            onRehydrateStorage: () => (state) => {
                if (!state) return;
                state.messages = state.messages.map((m) =>
                    m.status === 'streaming' ? { ...m, status: 'sent' } : m);
                state.activeStreamId = null;
                state.currentStreamingMessage = '';
                state._streamBuffer = '';
                state._streamFlushTimer = null;
            },
        }
    )
);
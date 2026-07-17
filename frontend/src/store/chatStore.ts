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
    sendMessage: (content: string) => Promise<void>;
    sendStreamingMessage: (content: string, onChunk: (chunk: string) => void) => Promise<void>;
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
            expireCard: (cardId) => set((s) => ({
                cardStatus: { ...s.cardStatus, [cardId]: 'expired' },
                activeCardId: s.activeCardId === cardId ? null : s.activeCardId,
            })),
            dismissCard: (cardId) => set((s) => ({
                cardStatus: { ...s.cardStatus, [cardId]: 'dismissed' },
                activeCardId: s.activeCardId === cardId ? null : s.activeCardId,
            })),

            // Streaming helpers: drive server-pushed token deltas into a single message.
            beginStream: (messageId, role) => set((s) => ({
                activeStreamId: messageId,
                messages: [
                    ...s.messages,
                    { id: messageId, role, content: '', timestamp: new Date(), status: 'streaming' },
                ],
                currentStreamingMessage: '',
            })),

            appendDelta: (streamId, delta) => set((s) => ({
                currentStreamingMessage: s.currentStreamingMessage + delta,
                messages: s.messages.map((m) =>
                    m.id === streamId ? { ...m, content: m.content + delta } : m),
            })),

            endStream: (streamId, content, metadata) => set((s) => ({
                activeStreamId: s.activeStreamId === streamId ? null : s.activeStreamId,
                currentStreamingMessage: '',
                messages: s.messages.map((m) =>
                    m.id === streamId
                        ? { ...m, content, status: 'sent', metadata: { ...m.metadata, ...metadata } }
                        : m),
            })),

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

                    if (response.task_created) {
                        showToast.success(`Task ${response.task_id} created`);
                    }

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

            sendStreamingMessage: async (content: string, onChunk: (chunk: string) => void) => {
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

                let assistantContent = '';
                let metadata: any = {};

                try {
                    await chatStreamApi.sendStreamingMessage(
                        content,
                        // On chunk
                        (chunk: string) => {
                            assistantContent += chunk;
                            onChunk(chunk);
                            set({ currentStreamingMessage: assistantContent });
                        },
                        // On complete
                        (meta: any) => {
                            metadata = meta;
                        },
                        // On error
                        (error: string) => {
                            throw new Error(error);
                        }
                    );

                    // Add assistant message
                    const assistantMessage: Message = {
                        id: crypto.randomUUID(),
                        role: 'head_of_council',
                        content: assistantContent,
                        timestamp: new Date(),
                        status: 'sent',
                        metadata: {
                            agent_used: metadata.agent_id,
                            model: metadata.model,
                            task_created: metadata.task_created,
                            task_id: metadata.task_id,
                            tokens_used: metadata.tokens_used
                        }
                    };

                    set((state) => ({
                        messages: [...state.messages, assistantMessage],
                        isLoading: false,
                        currentStreamingMessage: ''
                    }));

                    if (metadata.task_created) {
                        showToast.success(`Task ${metadata.task_id} created`);
                    }

                } catch (error: any) {
                    console.error('Streaming chat error:', error);

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
        }
    )
);
import { create } from 'zustand';
import toast from 'react-hot-toast';
import { api } from '@/services/api';

export interface Message {
    id: string;
    role: 'sovereign' | 'head_of_council' | 'system';
    content: string;
    timestamp: Date;
    status?: 'sending' | 'sent' | 'error';
    metadata?: {
        agent_used?: string;
        model?: string;
        latency_ms?: number;
        task_created?: boolean;
        task_id?: string;
        tokens_used?: number;
    };
}

interface ChatState {
    messages: Message[];
    isLoading: boolean;
    currentStreamingMessage: string;
    sendMessage: (content: string) => Promise<void>;
    sendStreamingMessage: (content: string, onChunk: (chunk: string) => void) => Promise<void>;
    clearHistory: () => void;
    loadHistory: () => Promise<void>;
}

// Real API implementation for streaming chat
const sendStreamingMessageToCouncil = async (
    message: string,
    onChunk: (chunk: string) => void,
    onComplete: (meta: any) => void,
    onError: (error: string) => void
): Promise<void> => {
    try {
        const response = await fetch('/api/v1/chat/send', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${localStorage.getItem('access_token')}`
            },
            body: JSON.stringify({
                message: message,
                stream: true
            })
        });

        if (!response.ok) {
            const errorData = await response.json().catch(() => ({}));
            throw new Error(errorData.detail || `HTTP ${response.status}`);
        }

        const reader = response.body?.getReader();
        if (!reader) {
            throw new Error('No response body');
        }

        const decoder = new TextDecoder();
        let buffer = '';
        let metadata: any = {};

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split('\n');
            buffer = lines.pop() || '';

            for (const line of lines) {
                if (line.trim().startsWith('data: ')) {
                    try {
                        const data = JSON.parse(line.trim().substring(6));
                        
                        switch (data.type) {
                            case 'content':
                                onChunk(data.content);
                                break;
                            case 'status':
                                // Status updates (e.g., "deliberating...")
                                break;
                            case 'complete':
                                metadata = data.metadata || {};
                                break;
                            case 'error':
                                onError(data.content || 'Unknown error');
                                return;
                            case 'done':
                                onComplete(metadata);
                                return;
                        }
                    } catch (e) {
                        console.warn('Failed to parse SSE data:', line);
                    }
                }
            }
        }

        // Handle any remaining data in buffer
        if (buffer.trim().startsWith('data: ')) {
            try {
                const data = JSON.parse(buffer.trim().substring(6));
                if (data.type === 'complete') {
                    onComplete(data.metadata || {});
                } else if (data.type === 'done') {
                    onComplete(metadata);
                }
            } catch (e) {
                onComplete(metadata);
            }
        } else {
            onComplete(metadata);
        }

    } catch (error: any) {
        onError(error.message || 'Failed to connect to Head of Council');
    }
};

// Non-streaming API call
const sendMessageToCouncil = async (message: string): Promise<any> => {
    const response = await api.post('/api/v1/chat/send', {
        message: message,
        stream: false
    });
    return response.data;
};

export const useChatStore = create<ChatState>()((set, get) => ({
            messages: [],
            isLoading: false,
            currentStreamingMessage: '',

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
                    const response = await sendMessageToCouncil(content);

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
                        toast.success(`Task ${response.task_id} created`);
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

                    toast.error('Failed to send message');
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
                    await sendStreamingMessageToCouncil(
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
                        toast.success(`Task ${metadata.task_id} created`);
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

                    toast.error('Failed to send message');
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
        })
);
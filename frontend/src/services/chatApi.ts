/**
 * Chat history and conversation management API.
 */

import { api } from './api';

export interface ChatMessage {
    id: string;
    conversation_id?: string;
    user_id: string;
    role: 'sovereign' | 'head_of_council' | 'system';
    content: string;
    attachments?: Array<{
        name: string;
        type: string;
        size: number;
        url: string;
        category: string;
    }>;
    metadata?: {
        agent_id?: string;
        model?: string;
        tokens_used?: number;
        task_created?: boolean;
        task_id?: string;
        latency_ms?: number;
    };
    agent_id?: string;
    created_at: string;
}

export interface Conversation {
    id: string;
    user_id: string;
    title?: string;
    context?: string;
    created_at: string;
    updated_at: string;
    last_message_at: string;
    message_count: number;
    messages?: ChatMessage[];
}

export interface ConversationListResponse {
    conversations: Conversation[];
    total: number;
}

export interface ChatHistoryResponse {
    messages: ChatMessage[];
    total: number;
    has_more: boolean;
    next_cursor?: string;
}

const API_BASE = '/api/v1/chat';

export const chatApi = {
    /**
     * Get chat history (legacy endpoint).
     *
     * Returns an empty result instead of throwing when the backend responds
     * with 5xx — the endpoint is non-critical and a server error should not
     * block the chat UI from rendering.
     */
    getHistory: async (limit = 50): Promise<ChatHistoryResponse> => {
        try {
            const response = await api.get<ChatHistoryResponse>(`${API_BASE}/history?limit=${limit}`);
            return response.data;
        } catch (err: any) {
            const status = err?.response?.status;
            if (status && status >= 500) {
                console.warn('[chatApi] getHistory returned', status, '— falling back to empty history');
                return { messages: [], total: 0, has_more: false };
            }
            throw err;
        }
    },

    listConversations: async (): Promise<ConversationListResponse> => {
        const response = await api.get<ConversationListResponse>(`${API_BASE}/conversations`);
        return response.data;
    },

    getConversation: async (conversationId: string): Promise<Conversation> => {
        const response = await api.get<Conversation>(`${API_BASE}/conversations/${conversationId}`);
        return response.data;
    },

    createConversation: async (title?: string, context?: string): Promise<Conversation> => {
        const response = await api.post<Conversation>(`${API_BASE}/conversations`, {
            title,
            context,
        });
        return response.data;
    },

    updateConversation: async (
        conversationId: string,
        updates: { title?: string; context?: string },
    ): Promise<Conversation> => {
        const response = await api.put<Conversation>(
            `${API_BASE}/conversations/${conversationId}`,
            updates,
        );
        return response.data;
    },

    deleteConversation: async (conversationId: string): Promise<{ success: boolean }> => {
        const response = await api.delete(`${API_BASE}/conversations/${conversationId}`);
        return response.data;
    },

    archiveConversation: async (conversationId: string): Promise<{ success: boolean }> => {
        const response = await api.post(`${API_BASE}/conversations/${conversationId}/archive`);
        return response.data;
    },

    searchMessages: async (query: string, limit = 20): Promise<ChatHistoryResponse> => {
        const response = await api.get<ChatHistoryResponse>(
            `${API_BASE}/search?q=${encodeURIComponent(query)}&limit=${limit}`,
        );
        return response.data;
    },

    deleteMessage: async (_messageId: string): Promise<{ success: boolean }> => {
        console.warn(
            'deleteMessage: per-message deletion is not yet implemented in the backend. ' +
            'Use deleteConversation to remove the entire conversation.',
        );
        return { success: false };
    },

    getStats: async (): Promise<{
        total_conversations: number;
        total_messages: number;
        messages_today: number;
        storage_used_bytes: number;
    }> => {
        const response = await api.get(`${API_BASE}/stats`);
        return response.data;
    },

    exportConversation: async (
        conversationId: string,
        format: 'json' | 'markdown' | 'txt' = 'json',
    ): Promise<Blob> => {
        const response = await api.get(
            `${API_BASE}/conversations/${conversationId}/export?format=${format}`,
            { responseType: 'blob' },
        );
        return response.data;
    },
};

export default chatApi;

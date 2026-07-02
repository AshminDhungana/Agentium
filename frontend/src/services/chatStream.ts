import { rawFetch } from './api';

export interface ChatStreamCompleteMeta {
    agent_id?: string;
    model?: string;
    task_created?: boolean;
    task_id?: string;
    tokens_used?: number;
}

export interface ChatSendResponse {
    response: string;
    content?: string;
    agent_id?: string;
    model?: string;
    task_created?: boolean;
    task_id?: string;
    tokens_used?: number;
}

export const chatStreamApi = {
    sendMessage: (message: string): Promise<ChatSendResponse> =>
        rawFetch<ChatSendResponse>('/api/v1/chat/send', {
            method: 'POST',
            body: JSON.stringify({ message, stream: false }),
        }),

    sendStreamingMessage: async (
        message: string,
        onChunk: (chunk: string) => void,
        onComplete: (meta: ChatStreamCompleteMeta) => void,
        onError: (error: string) => void,
    ): Promise<void> => {
        try {
            const token = localStorage.getItem('access_token');
            const baseURL = import.meta.env.VITE_API_BASE_URL || '';

            const response = await fetch(`${baseURL}/api/v1/chat/send`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    ...(token ? { Authorization: `Bearer ${token}` } : {}),
                },
                body: JSON.stringify({ message, stream: true }),
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
            let metadata: ChatStreamCompleteMeta = {};

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
    },
};

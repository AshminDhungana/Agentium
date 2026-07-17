import { rawFetch } from './api';

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
};

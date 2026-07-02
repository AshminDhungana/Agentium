import { api } from './api';

export interface EventTrigger {
    id: string;
    agentium_id: string;
    name: string;
    trigger_type: 'webhook' | 'schedule' | 'threshold' | 'api_poll';
    config: Record<string, unknown>;
    target_workflow_id: string | null;
    target_agent_id: string | null;
    is_active: boolean;
    last_fired_at: string | null;
    fire_count: number;
    max_fires_per_minute: number;
    pause_duration_seconds: number;
    paused_until: string | null;
    created_at: string;
}

export interface EventLog {
    id: string;
    agentium_id: string;
    trigger_id: string;
    event_payload: Record<string, unknown>;
    status: 'processed' | 'dead_letter' | 'duplicate';
    correlation_id: string | null;
    error: string | null;
    retry_count: number;
    created_at: string;
}

export interface CreateTriggerPayload {
    name: string;
    trigger_type: string;
    config: Record<string, unknown>;
    target_workflow_id: string | null;
}

export const eventTriggersApi = {
    getAll: async (): Promise<EventTrigger[]> => {
        const { data } = await api.get<EventTrigger[]>('/api/v1/events/triggers');
        return data;
    },

    create: async (payload: CreateTriggerPayload): Promise<EventTrigger> => {
        const { data } = await api.post<EventTrigger>('/api/v1/events/triggers', payload);
        return data;
    },

    update: async (id: string, payload: { is_active: boolean }): Promise<void> => {
        await api.put(`/api/v1/events/triggers/${id}`, payload);
    },

    delete: async (id: string): Promise<void> => {
        await api.delete(`/api/v1/events/triggers/${id}`);
    },

    getLogs: async (statusFilter?: string): Promise<EventLog[]> => {
        let url = '/api/v1/events/logs?limit=100';
        if (statusFilter) url += `&status=${statusFilter}`;
        const { data } = await api.get<EventLog[]>(url);
        return data;
    },

    getDeadLetters: async (): Promise<EventLog[]> => {
        const { data } = await api.get<EventLog[]>('/api/v1/events/dead-letters?limit=50');
        return data;
    },

    retryDeadLetter: async (id: string): Promise<void> => {
        await api.post(`/api/v1/events/dead-letters/${id}/retry`);
    },
};

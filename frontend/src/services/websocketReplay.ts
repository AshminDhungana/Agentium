import { rawFetch } from './api';

export interface ReplayEvent {
    type: string;
    [key: string]: unknown;
}

export interface ReplayResponse {
    events: ReplayEvent[];
}

export interface GenesisStatusResponse {
    status: 'complete' | 'not_started' | 'running' | 'failed' | 'awaiting_name';
    reason?: string;
    prompt?: string;
    timeout_seconds?: number;
}

export const websocketReplayApi = {
    fetchReplay: async (since: string): Promise<ReplayEvent[]> => {
        const data = await rawFetch<ReplayResponse>(
            `/ws/replay?since=${encodeURIComponent(since)}`,
        );
        return data.events || [];
    },

    pollGenesisStatus: async (): Promise<GenesisStatusResponse> => {
        return rawFetch<GenesisStatusResponse>('/ws/genesis-status');
    },

    submitCountryName: async (name: string): Promise<{ accepted: boolean; reason?: string }> => {
        return rawFetch<{ accepted: boolean; reason?: string }>(
            '/api/v1/genesis/set-country-name',
            { method: 'POST', body: JSON.stringify({ name }) },
        );
    },
};

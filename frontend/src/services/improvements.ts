import { api } from './api';

export interface ImpactStats {
    success_rate_delta: number;
    tools_generated: number;
    anti_patterns_warned: number;
    history: Array<{ date: string; success_rate: number }>;
}

export interface Pattern {
    id: string;
    type: string;
    content: string;
    confidence: number;
}

export interface PatternsResponse {
    patterns: Pattern[];
}

export const improvementsApi = {
    getImpactStats: async (): Promise<ImpactStats> => {
        const { data } = await api.get<ImpactStats>('/api/v1/improvements/impact');
        return data;
    },

    getPatterns: async (): Promise<PatternsResponse> => {
        const { data } = await api.get<PatternsResponse>('/api/v1/improvements/patterns');
        return data;
    },

    triggerConsolidation: async (): Promise<void> => {
        await api.post('/api/v1/improvements/consolidate');
    },
};

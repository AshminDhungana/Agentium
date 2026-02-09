import { api } from './api';
import { Constitution } from '../types';

export const constitutionService = {
    getCurrentConstitution: async (): Promise<Constitution> => {
        const response = await api.get<Constitution>('/api/v1/constitution/current');
        return response.data;
    },

    updateConstitution: async (data: {
        preamble: string;
        articles: Record<string, { title: string; content: string }> | string;
        prohibited_actions: string[];
        sovereign_preferences: Record<string, any>;
    }): Promise<Constitution> => {
        const payload = {
            ...data,
            articles: typeof data.articles === 'string' ? data.articles : JSON.stringify(data.articles),
            prohibited_actions: Array.isArray(data.prohibited_actions) ? data.prohibited_actions : [],
            sovereign_preferences: data.sovereign_preferences || {}
        };

        const response = await api.post<Constitution>('/api/v1/constitution/update', payload);
        return response.data;
    }
};
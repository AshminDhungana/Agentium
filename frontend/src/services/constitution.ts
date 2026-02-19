import { api } from './api';
import { Constitution } from '../types';

export const constitutionService = {
    getCurrentConstitution: async (): Promise<Constitution> => {
        const response = await api.get<Constitution>('/api/v1/constitution');
        return response.data;
    },

    updateConstitution: async (data: {
        preamble: string;
        articles: Record<string, { title: string; content: string }> | string;
        prohibited_actions: string[];
        sovereign_preferences: Record<string, any>;
    }): Promise<Constitution> => {
        // Parse articles if it arrives as a string; backend expects a plain object (Dict)
        const parsedArticles =
            typeof data.articles === 'string'
                ? JSON.parse(data.articles)
                : data.articles;

        const payload = {
            ...data,
            articles: parsedArticles,
            prohibited_actions: Array.isArray(data.prohibited_actions) ? data.prohibited_actions : [],
            sovereign_preferences: data.sovereign_preferences || {}
        };

        const response = await api.post<Constitution>('/api/v1/constitution/update', payload);
        return response.data;
    }
};
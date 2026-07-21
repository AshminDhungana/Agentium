import { api } from './api';

export interface BackendHealthResponse {
    status: string;
    version?: string;
}

export const backendHealthApi = {
    check: async (): Promise<BackendHealthResponse> => {
        const { data } = await api.get<BackendHealthResponse>('/api/health', { timeout: 5000 });
        return data;
    },
};

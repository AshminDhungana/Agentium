import { api } from './api';
import { Task } from '../types';

export interface CreateTaskRequest {
    title: string;
    description: string;
    priority: 'low' | 'normal' | 'urgent' | 'critical';
    task_type: 'execution' | 'research' | 'creative';
}

export const tasksService = {
    getTasks: async (filters?: { status?: string; agent_id?: string }): Promise<Task[]> => {
        const params = new URLSearchParams();
        if (filters?.status) params.append('status', filters.status);
        if (filters?.agent_id) params.append('agent_id', filters.agent_id);

        const query = params.toString() ? `?${params.toString()}` : '';
        const response = await api.get<Task[]>(`/api/v1/tasks/${query}`);

        return Array.isArray(response.data)
            ? response.data
            : (response.data as any).tasks ?? [];
    },

    createTask: async (data: CreateTaskRequest): Promise<Task> => {
        const response = await api.post<Task>('/api/v1/tasks/', data);
        return response.data;
    },

    // task id is a UUID string, not a number
    executeTask: async (taskId: string, agentId: string): Promise<any> => {
        const response = await api.post(`/api/v1/tasks/${taskId}/execute?agent_id=${agentId}`);
        return response.data;
    }
};

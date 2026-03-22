import { api } from './api';
import { Task, Subtask, CritiqueReview, CriticStatsResponse } from '../types';

// Phase 6.3 — Acceptance Criteria
export interface AcceptanceCriterion {
    metric: string;
    threshold: boolean | number | string | number[];
    validator: 'code' | 'output' | 'plan';
    is_mandatory: boolean;
    description?: string;
}

export interface CreateTaskRequest {
    title: string;
    description: string;
    priority: string;
    task_type: string;
    constitutional_basis?: string;
    hierarchical_id?: string;
    parent_task_id?: string;
    acceptance_criteria?: AcceptanceCriterion[];
    veto_authority?: 'code' | 'output' | 'plan';
}

export interface UpdateTaskRequest {
    title?: string;
    description?: string;
    priority?: string;
    status?: string;
    status_note?: string;
    constitutional_basis?: string;
    hierarchical_id?: string;
    parent_task_id?: string;
    execution_plan_id?: string;
    acceptance_criteria?: AcceptanceCriterion[];
    veto_authority?: 'code' | 'output' | 'plan';
}

export interface AllowedTransitionsResponse {
    task_id: string;
    current_status: string;
    allowed_transitions: string[];
    is_terminal: boolean;
}

export const tasksService = {
    getTasks: async (filters?: {
        status?: string;
        agent_id?: string;
        parent_task_id?: string;
        my_tasks?: boolean;
        hide_system?: boolean;
    }): Promise<Task[]> => {
        const params = new URLSearchParams();
        if (filters?.status) params.append('status', filters.status);
        if (filters?.agent_id) params.append('agent_id', filters.agent_id);
        if (filters?.parent_task_id) params.append('parent_task_id', filters.parent_task_id);
        if (filters?.my_tasks) params.append('my_tasks', 'true');
        if (filters?.hide_system !== undefined) params.append('hide_system', String(filters.hide_system));

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

    executeTask: async (taskId: string, agentId: string): Promise<any> => {
        const response = await api.post(`/api/v1/tasks/${taskId}/execute?agent_id=${agentId}`);
        return response.data;
    },

    escalateTask: async (taskId: string, reason: string): Promise<any> => {
        const response = await api.post(`/api/v1/tasks/${taskId}/escalate?reason=${encodeURIComponent(reason)}`);
        return response.data;
    },

    retryTask: async (taskId: string): Promise<any> => {
        const response = await api.post(`/api/v1/tasks/${taskId}/retry`);
        return response.data;
    },

    getTaskEvents: async (taskId: string): Promise<any> => {
        const response = await api.get(`/api/v1/tasks/${taskId}/events`);
        return response.data;
    },

    /** Returns subtasks for a task. Now typed with the shared Subtask interface. */
    getTaskSubtasks: async (taskId: string): Promise<{ subtasks: Subtask[] }> => {
        const response = await api.get<{ subtasks: Subtask[] }>(`/api/v1/tasks/${taskId}/subtasks`);
        return response.data;
    },

    getActiveTasks: async (): Promise<Task[]> => {
        const response = await api.get<{ tasks: Task[]; total: number }>('/api/v1/tasks/active');
        return response.data.tasks ?? [];
    },

    updateTask: async (taskId: string, data: UpdateTaskRequest): Promise<Task> => {
        const response = await api.patch<Task>(`/api/v1/tasks/${taskId}`, data);
        return response.data;
    },

    getAllowedTransitions: async (taskId: string): Promise<AllowedTransitionsResponse> => {
        const response = await api.get<AllowedTransitionsResponse>(
            `/api/v1/tasks/${taskId}/allowed-transitions`
        );
        return response.data;
    },

    // Phase 13.1 — Auto-Delegation Engine

    autoDelegate: async (taskId: string): Promise<any> => {
        const response = await api.post(`/api/v1/tasks/${taskId}/auto-delegate`);
        return response.data;
    },

    getDelegationLog: async (taskId: string): Promise<any> => {
        const response = await api.get(`/api/v1/tasks/${taskId}/delegation-log`);
        return response.data;
    },

    getDependencyGraph: async (taskId: string): Promise<any> => {
        const response = await api.get(`/api/v1/tasks/${taskId}/dependency-graph`);
        return response.data;
    },
};

// ─── Critic service calls ─────────────────────────────────────────────────────

export const criticsService = {
    /** Fetch aggregate stats for all critic agents. */
    getStats: async (): Promise<CriticStatsResponse> => {
        const response = await api.get<CriticStatsResponse>('/api/v1/critics/stats');
        return response.data;
    },

    /**
     * Fetch critic reviews for a task or subtask.
     * The same endpoint is used for both task-level and subtask-level lookups.
     */
    getTaskReviews: async (taskId: string): Promise<{ reviews: CritiqueReview[] }> => {
        const response = await api.get<{ reviews: CritiqueReview[] }>(
            `/api/v1/critics/reviews/${taskId}`
        );
        return response.data;
    },

    submitReview: async (payload: {
        task_id: string;
        output_content: string;
        critic_type: 'code' | 'output' | 'plan';
        subtask_id?: string;
        retry_count?: number;
    }) => {
        const response = await api.post('/api/v1/critics/review', payload);
        return response.data;
    },

    // Phase 6.3 — retrieve the acceptance criteria stored on a task
    getTaskCriteria: async (taskId: string): Promise<AcceptanceCriterion[]> => {
        const response = await api.get<{ governance: { acceptance_criteria?: AcceptanceCriterion[] } }>(
            `/api/v1/tasks/${taskId}`
        );
        return response.data.governance?.acceptance_criteria ?? [];
    },
};
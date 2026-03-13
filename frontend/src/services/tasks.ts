import { api } from './api';
import { Task } from '../types';

// Phase 6.3 — Acceptance Criteria
export interface AcceptanceCriterion {
    metric: string;                          // snake_case identifier
    threshold: boolean | number | string | number[];
    validator: 'code' | 'output' | 'plan';  // which critic validates this
    is_mandatory: boolean;                   // mandatory = failure blocks task
    description?: string;                    // human-readable, shown in dashboard
}

export interface CreateTaskRequest {
    title: string;
    description: string;
    priority: string;
    task_type: string;
    constitutional_basis?: string;
    hierarchical_id?: string;
    parent_task_id?: string;
    // Phase 6.3
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
        my_tasks?: boolean;    // scope to current user's tasks only
        hide_system?: boolean; // hide idle/system tasks (backend default: true)
    }): Promise<Task[]> => {
        const params = new URLSearchParams();
        if (filters?.status) params.append('status', filters.status);
        if (filters?.agent_id) params.append('agent_id', filters.agent_id);
        if (filters?.parent_task_id) params.append('parent_task_id', filters.parent_task_id);
        if (filters?.my_tasks) params.append('my_tasks', 'true');
        // Only send hide_system when explicitly set — lets backend default handle the common case
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

    getTaskSubtasks: async (taskId: string): Promise<any> => {
        const response = await api.get(`/api/v1/tasks/${taskId}/subtasks`);
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
};

// ─── Critic service calls ─────────────────────────────────────────────────────

export const criticsService = {
    getStats: async () => {
        const response = await api.get('/api/v1/critics/stats');
        return response.data;
    },

    getTaskReviews: async (taskId: string) => {
        const response = await api.get(`/api/v1/critics/reviews/${taskId}`);
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
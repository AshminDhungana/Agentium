import { api } from '@/services/api';

export interface Preference {
  agentium_id: string;
  key: string;
  value: any;
  category: string;
  scope: string;
  data_type: 'boolean' | 'integer' | 'float' | 'string' | 'array' | 'json';
  editable: boolean;
  description?: string;
  last_modified_by_agent?: string;
  last_agent_modified_at?: string;
  to_dict(): any;
}

export interface PreferenceCreateRequest {
  key: string;
  value: any;
  category?: string;
  scope?: string;
  scope_target_id?: string;
  description?: string;
  editable_by_agents?: boolean;
}

export interface PreferenceUpdateRequest {
  value: any;
  reason?: string;
}

export interface PreferenceBulkUpdateRequest {
  preferences: Record<string, any>;
  reason?: string;
}

export type PreferenceCategory = 
  | 'ui' | 'chat' | 'notifications' 
  | 'agents' | 'tasks' | 'models' | 'tools' | 'privacy' | 'custom';

export const CATEGORY_LABELS: Record<PreferenceCategory, string> = {
  ui: 'Interface',
  chat: 'Chat',
  notifications: 'Notifications',
  agents: 'Agents',
  tasks: 'Tasks',
  models: 'Models',
  tools: 'Tools',
  privacy: 'Privacy',
  custom: 'Custom',
};

export const CATEGORY_DESCRIPTIONS: Record<PreferenceCategory, string> = {
  ui: 'User interface settings',
  chat: 'Chat and messaging settings',
  notifications: 'Notification preferences',
  agents: 'Agent behavior settings',
  tasks: 'Task execution preferences',
  models: 'AI model configuration',
  tools: 'Tool execution settings',
  privacy: 'Privacy and data settings',
  custom: 'Custom user-defined preferences',
};

export const preferencesApi = {
  async getAll(params?: { category?: string; scope?: string }): Promise<Preference[]> {
    const response = await api.get('/api/v1/preferences', { params });
    return response.data;
  },

  async get(key: string, defaultValue?: any): Promise<{ key: string; value: any; default_used: boolean }> {
    const response = await api.get(`/api/v1/preferences/${key}`, { params: { default: defaultValue } });
    return response.data;
  },

  async create(request: PreferenceCreateRequest): Promise<{ status: string; preference: Preference }> {
    const response = await api.post('/api/v1/preferences', request);
    return response.data;
  },

  async update(key: string, request: PreferenceUpdateRequest): Promise<{ status: string; preference: Preference }> {
    const response = await api.put(`/api/v1/preferences/${key}`, request);
    return response.data;
  },

  async delete(key: string): Promise<{ status: string; key: string }> {
    const response = await api.delete(`/api/v1/preferences/${key}`);
    return response.data;
  },

  async bulkUpdate(request: PreferenceBulkUpdateRequest): Promise<{ status: string; results: any }> {
    const response = await api.post('/api/v1/preferences/bulk', request);
    return response.data;
  },

  async getDefaults(): Promise<{ defaults: Record<string, any>; categories: Record<string, string> }> {
    const response = await api.get('/api/v1/preferences/system/defaults');
    return response.data;
  },

  async initializeDefaults(): Promise<{ status: string; count: number; preferences: Preference[] }> {
    const response = await api.post('/api/v1/preferences/system/initialize');
    return response.data;
  },
};
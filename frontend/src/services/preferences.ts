/**
 * preferences.ts — User Preference Service
 */

import { api } from './api';

// ─── Types ────────────────────────────────────────────────────────────────────

export interface UserPreference {
  id: string;
  user_id: string;
  category: string;
  key: string;
  value: unknown;
  data_type: string;
  description: string | null;
  is_system: boolean;
  created_at: string;
  updated_at: string;
}

export interface PreferenceHistoryEntry {
  id: string;
  preference_id: string;
  old_value: unknown;
  new_value: unknown;
  changed_by: string;
  changed_at: string;
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

export const PREFERENCE_CATEGORIES = [
  { id: 'general',       name: 'General',       description: 'General system preferences',         icon: 'Settings'      },
  { id: 'ui',            name: 'UI',             description: 'User interface settings',             icon: 'Layout'        },
  { id: 'notifications', name: 'Notifications',  description: 'Notification preferences',            icon: 'Bell'          },
  { id: 'agents',        name: 'Agents',         description: 'Agent behavior settings',             icon: 'Users'         },
  { id: 'tasks',         name: 'Tasks',          description: 'Task execution preferences',          icon: 'CheckSquare'   },
  { id: 'chat',          name: 'Chat',           description: 'Chat and messaging settings',         icon: 'MessageSquare' },
  { id: 'models',        name: 'Models',         description: 'AI model configuration',              icon: 'Brain'         },
  { id: 'tools',         name: 'Tools',          description: 'Tool execution settings',             icon: 'Wrench'        },
  { id: 'privacy',       name: 'Privacy',        description: 'Privacy and data settings',           icon: 'Shield'        },
  { id: 'custom',        name: 'Custom',         description: 'Custom user-defined preferences',     icon: 'Pencil'        },
] as const;

export type PreferenceCategoryId = typeof PREFERENCE_CATEGORIES[number]['id'];

export const DATA_TYPE_LABELS: Record<string, { label: string; color: string }> = {
  string:  { label: 'Text',    color: 'blue'   },
  integer: { label: 'Number',  color: 'green'  },
  float:   { label: 'Decimal', color: 'cyan'   },
  boolean: { label: 'Yes/No',  color: 'purple' },
  json:    { label: 'JSON',    color: 'orange' },
  array:   { label: 'List',    color: 'pink'   },
};

export const formatPreferenceValue = (value: unknown, dataType: string): string => {
  if (value === null || value === undefined) return '—';
  switch (dataType) {
    case 'boolean': return value ? 'Yes' : 'No';
    case 'json':
    case 'array':   return JSON.stringify(value);
    default:        return String(value);
  }
};

export const parsePreferenceValue = (raw: string, dataType: string): unknown => {
  switch (dataType) {
    case 'integer': return parseInt(raw, 10);
    case 'float':   return parseFloat(raw);
    case 'boolean': return raw === 'true';
    case 'json':
    case 'array':   try { return JSON.parse(raw); } catch { return raw; }
    default:        return raw;
  }
};

// ─── Service ──────────────────────────────────────────────────────────────────

export const preferencesService = {
  // ── User preferences ────────────────────────────────────────────────────────

  getPreferences: async (filters?: {
    category?: string;
    search?: string;
  }): Promise<UserPreference[]> => {
    const params = new URLSearchParams();
    if (filters?.category) params.append('category', filters.category);
    if (filters?.search)   params.append('search', filters.search);
    const query = params.toString() ? `?${params.toString()}` : '';
    const response = await api.get<UserPreference[]>(`/api/v1/preferences${query}`);
    return response.data;
  },

  getPreference: async (
    key: string,
    options?: { category?: string },
  ): Promise<UserPreference> => {
    const params = new URLSearchParams();
    if (options?.category) params.append('category', options.category);
    const query = params.toString() ? `?${params.toString()}` : '';
    const response = await api.get<UserPreference>(
      `/api/v1/preferences/${encodeURIComponent(key)}${query}`,
    );
    return response.data;
  },

  createPreference: async (data: {
    key: string;
    value: unknown;
    category?: string;
    description?: string;
    data_type?: string;
  }): Promise<UserPreference> => {
    const response = await api.post<UserPreference>('/api/v1/preferences/', data);
    return response.data;
  },

  updatePreference: async (
    key: string,
    value: unknown,
  ): Promise<UserPreference> => {
    const response = await api.put<UserPreference>(
      `/api/v1/preferences/${encodeURIComponent(key)}`,
      { value },
    );
    return response.data;
  },

  /**
   * Delete a user preference by key.
   *
   * Previously missing from the frontend service layer.
   * Maps to: DELETE /api/v1/preferences/{key}
   */
  deletePreference: async (
    key: string,
  ): Promise<{ success: boolean; message: string }> => {
    const response = await api.delete<{ success: boolean; message: string }>(
      `/api/v1/preferences/${encodeURIComponent(key)}`,
    );
    return response.data;
  },

  bulkSetPreferences: async (
    preferences: Array<{ key: string; value: unknown; category?: string }>,
  ): Promise<UserPreference[]> => {
    const response = await api.post<UserPreference[]>(
      '/api/v1/preferences/bulk',
      { preferences },
    );
    return response.data;
  },

  // ── Agent preferences ────────────────────────────────────────────────────────

  agentPreferences: {
    get: async (key: string, agentId?: string): Promise<UserPreference> => {
      const params = new URLSearchParams();
      if (agentId) params.append('agent_id', agentId);
      const query = params.toString() ? `?${params.toString()}` : '';
      const response = await api.get<UserPreference>(
        `/api/v1/preferences/agent/get/${encodeURIComponent(key)}${query}`,
      );
      return response.data;
    },

    list: async (agentId?: string): Promise<UserPreference[]> => {
      const params = new URLSearchParams();
      if (agentId) params.append('agent_id', agentId);
      const query = params.toString() ? `?${params.toString()}` : '';
      const response = await api.get<UserPreference[]>(
        `/api/v1/preferences/agent/list${query}`,
      );
      return response.data;
    },

    set: async (key: string, value: unknown, agentId?: string): Promise<UserPreference> => {
      const response = await api.post<UserPreference>(
        `/api/v1/preferences/agent/set/${encodeURIComponent(key)}`,
        { value, agent_id: agentId },
      );
      return response.data;
    },
  },

  // ── System / Admin preferences ────────────────────────────────────────────────

  admin: {
    getDefaults: async (): Promise<UserPreference[]> => {
      const response = await api.get<UserPreference[]>('/api/v1/preferences/system/defaults');
      return response.data;
    },

    initializeSystem: async (): Promise<void> => {
      await api.post('/api/v1/preferences/system/initialize');
    },

    optimize: async (): Promise<void> => {
      await api.post('/api/v1/preferences/admin/optimize');
    },

    getRecommendations: async (): Promise<{
      total_preferences: number;
      recommendations: Array<{ key: string; reason: string; suggested_value: unknown }>;
    }> => {
      const response = await api.get('/api/v1/preferences/admin/recommendations');
      return response.data;
    },

    getPreferenceHistory: async (
      preferenceId: string,
      limit?: number,
    ): Promise<{
      preference_id: string;
      count: number;
      history: PreferenceHistoryEntry[];
    }> => {
      const params = new URLSearchParams();
      if (limit) params.append('limit', String(limit));
      const query = params.toString() ? `?${params.toString()}` : '';
      const response = await api.get(
        `/api/v1/preferences/admin/history/${encodeURIComponent(preferenceId)}${query}`,
      );
      return response.data;
    },
  },
};
# Settings Page Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expand SettingsPage.tsx from 2 tabs to 6 tabs (Account, Appearance, Preferences, API Keys, Notifications, User Management) with full preference management, theme selection, and embedded API key management.

**Architecture:** Create reusable settings components (PreferencesTab, PreferenceSection, PreferenceInput, ThemeSelector, ApiKeysTab, NotificationsTab), a useUserPreferences hook, and a preferences API service. Integrate all into SettingsPage.tsx with tab-based navigation. Reuse existing ModelConfigForm for API Keys tab.

**Tech Stack:** React 18, TypeScript, Tailwind CSS, Zustand (authStore), React Hook Form, lucide-react icons, existing theme utilities (theme.ts)

## Global Constraints

- All new components in `frontend/src/components/settings/`
- Hook in `frontend/src/hooks/useUserPreferences.ts`
- Service in `frontend/src/services/preferences.ts`
- Follow existing patterns: dark mode via `dark:` Tailwind classes, theme transition via `theme-transition` class
- Tab panels kept mounted with `hidden` class (not unmounted) to preserve state
- Optimistic UI updates with rollback on error
- No new external dependencies
- TypeScript strict mode, ESLint + Prettier compliance
- All preferences merged with backend DEFAULT_PREFERENCES on load
- Theme selector: Light / Dark / System (follows OS prefers-color-scheme)
- API Keys tab reuses ModelConfigForm component and modelsApi service
- User Management tab only renders for admin users (existing behavior)
- All 51 default preferences across 8 categories editable with correct input types

---

### Task 1: Preferences API Service (`preferences.ts`)

**Files:**
- Create: `frontend/src/services/preferences.ts`
- Test: `frontend/src/services/__tests__/preferences.test.ts`

**Interfaces:**
- Consumes: `api` from `@/services/api` (axios instance with auth interceptor)
- Produces: `preferencesApi` object with methods:
  - `getAll(params?: { category?: string; scope?: string }): Promise<Preference[]>`
  - `get(key: string, defaultValue?: any): Promise<{ key: string; value: any; default_used: boolean }>`
  - `create(request: PreferenceCreateRequest): Promise<{ status: string; preference: Preference }>`
  - `update(key: string, request: PreferenceUpdateRequest): Promise<{ status: string; preference: Preference }>`
  - `delete(key: string): Promise<{ status: string; key: string }>`
  - `bulkUpdate(request: PreferenceBulkUpdateRequest): Promise<{ status: string; results: any }>`
  - `getDefaults(): Promise<{ defaults: Record<string, any>; categories: Record<string, string> }>`
  - `initializeDefaults(): Promise<{ status: string; count: number; preferences: Preference[] }>`

**Types (mirror backend schemas):**
```typescript
interface Preference {
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

interface PreferenceCreateRequest {
  key: string;
  value: any;
  category?: string;
  scope?: string;
  scope_target_id?: string;
  description?: string;
  editable_by_agents?: boolean;
}

interface PreferenceUpdateRequest {
  value: any;
  reason?: string;
}

interface PreferenceBulkUpdateRequest {
  preferences: Record<string, any>;
  reason?: string;
}

type PreferenceCategory = 
  | 'ui' | 'chat' | 'notifications' 
  | 'agents' | 'tasks' | 'models' | 'tools' | 'privacy' | 'custom';

const CATEGORY_LABELS: Record<PreferenceCategory, string> = {
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

const CATEGORY_DESCRIPTIONS: Record<PreferenceCategory, string> = {
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
```

- [ ] **Step 1: Write the failing test**

```typescript
// frontend/src/services/__tests__/preferences.test.ts
import { preferencesApi } from '@/services/preferences';
import { api } from '@/services/api';

jest.mock('@/services/api');

describe('preferencesApi', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  describe('getAll', () => {
    it('fetches preferences with optional filters', async () => {
      const mockPrefs = [{ key: 'ui.theme', value: 'dark', category: 'ui' }];
      (api.get as jest.Mock).mockResolvedValue({ data: mockPrefs });

      const result = await preferencesApi.getAll({ category: 'ui' });

      expect(api.get).toHaveBeenCalledWith('/api/v1/preferences', { params: { category: 'ui', scope: undefined } });
      expect(result).toEqual(mockPrefs);
    });
  });

  describe('update', () => {
    it('sends PUT request with value and reason', async () => {
      const mockResponse = { status: 'updated', preference: { key: 'ui.theme', value: 'light' } };
      (api.put as jest.Mock).mockResolvedValue({ data: mockResponse });

      const result = await preferencesApi.update('ui.theme', { value: 'light', reason: 'user preference' });

      expect(api.put).toHaveBeenCalledWith('/api/v1/preferences/ui.theme', { value: 'light', reason: 'user preference' });
      expect(result).toEqual(mockResponse);
    });
  });

  describe('bulkUpdate', () => {
    it('sends POST with preferences map and reason', async () => {
      const mockResponse = { status: 'success', results: { success: ['ui.theme'], failed: [] } };
      (api.post as jest.Mock).mockResolvedValue({ data: mockResponse });

      const result = await preferencesApi.bulkUpdate({ preferences: { 'ui.theme': 'light' }, reason: 'bulk' });

      expect(api.post).toHaveBeenCalledWith('/api/v1/preferences/bulk', { preferences: { 'ui.theme': 'light' }, reason: 'bulk' });
      expect(result).toEqual(mockResponse);
    });
  });

  describe('getDefaults', () => {
    it('fetches default preferences and category metadata', async () => {
      const mockResponse = { defaults: { 'ui.theme': 'dark' }, categories: { ui: 'Interface' } };
      (api.get as jest.Mock).mockResolvedValue({ data: mockResponse });

      const result = await preferencesApi.getDefaults();

      expect(api.get).toHaveBeenCalledWith('/api/v1/preferences/system/defaults');
      expect(result).toEqual(mockResponse);
    });
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm test -- frontend/src/services/__tests__/preferences.test.ts`
Expected: FAIL - module not found

- [ ] **Step 3: Write minimal implementation**

```typescript
// frontend/src/services/preferences.ts
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npm test -- frontend/src/services/__tests__/preferences.test.ts`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/services/preferences.ts frontend/src/services/__tests__/preferences.test.ts
git commit -m "feat: add preferences API service with types and tests"
```

### Task 2: useUserPreferences Hook (`useUserPreferences.ts`)

**Files:**
- Create: `frontend/src/hooks/useUserPreferences.ts`
- Test: `frontend/src/hooks/__tests__/useUserPreferences.test.ts`

**Interfaces:**
- Consumes: `preferencesApi` from `@/services/preferences`, `DEFAULT_PREFERENCES` (imported from backend or mirrored), `useAuthStore` for user_id
- Produces: Hook returning:
  - `preferences: Record<string, any>` - merged user + system defaults
  - `loading: boolean`
  - `error: string | null`
  - `updatePreference(key: string, value: any): Promise<void>`
  - `bulkUpdate(preferences: Record<string, any>): Promise<void>`
  - `refresh(): Promise<void>`
  - `getPreference(key: string, defaultValue?: any): any`
  - `initialized: boolean`

**Behavior:**
- On mount: fetch user preferences + system defaults via `preferencesApi.getAll()` and `preferencesApi.getDefaults()`
- Merge: user preferences override system defaults (by key)
- Provide `getPreference(key, defaultValue)` that checks merged preferences first, then defaults
- `updatePreference`: optimistic update → API call → rollback on error + toast
- `bulkUpdate`: single API call for multiple preferences
- Auto-initialize defaults if user has no preferences (call `initializeDefaults`)

- [ ] **Step 1: Write the failing test**

```typescript
// frontend/src/hooks/__tests__/useUserPreferences.test.ts
import { renderHook, act, waitFor } from '@testing-library/react';
import { useUserPreferences } from '@/hooks/useUserPreferences';
import { preferencesApi } from '@/services/preferences';
import { useAuthStore } from '@/store/authStore';

jest.mock('@/services/preferences');
jest.mock('@/store/authStore');

const mockApi = preferencesApi as jest.Mocked<typeof preferencesApi>;
const mockAuthStore = useAuthStore as jest.MockedFunction<typeof useAuthStore>;

describe('useUserPreferences', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockAuthStore.mockReturnValue({ user: { id: 'user-123' } } as any);
  });

  it('fetches preferences and defaults on mount', async () => {
    mockApi.getAll.mockResolvedValue([
      { key: 'ui.theme', value: 'dark', category: 'ui', data_type: 'string' },
      { key: 'chat.history_limit', value: 50, category: 'chat', data_type: 'integer' },
    ]);
    mockApi.getDefaults.mockResolvedValue({
      defaults: { 'ui.theme': 'light', 'chat.history_limit': 50, 'notifications.enabled': true },
      categories: {},
    });

    const { result } = renderHook(() => useUserPreferences());

    await waitFor(() => expect(result.current.loading).toBe(false));

    expect(result.current.preferences['ui.theme']).toBe('dark'); // user overrides default
    expect(result.current.preferences['chat.history_limit']).toBe(50);
    expect(result.current.preferences['notifications.enabled']).toBe(true); // from defaults
    expect(result.current.initialized).toBe(true);
  });

  it('updatePreference does optimistic update then API call', async () => {
    mockApi.getAll.mockResolvedValue([]);
    mockApi.getDefaults.mockResolvedValue({ defaults: { 'ui.theme': 'dark' }, categories: {} });
    mockApi.update.mockResolvedValue({ status: 'updated', preference: { key: 'ui.theme', value: 'light' } });

    const { result } = renderHook(() => useUserPreferences());

    await waitFor(() => expect(result.current.initialized).toBe(true));

    await act(async () => {
      await result.current.updatePreference('ui.theme', 'light');
    });

    expect(result.current.preferences['ui.theme']).toBe('light');
    expect(mockApi.update).toHaveBeenCalledWith('ui.theme', { value: 'light', reason: undefined });
  });

  it('updatePreference rolls back on API error', async () => {
    mockApi.getAll.mockResolvedValue([{ key: 'ui.theme', value: 'dark', category: 'ui', data_type: 'string' }]);
    mockApi.getDefaults.mockResolvedValue({ defaults: {}, categories: {} });
    mockApi.update.mockRejectedValue(new Error('Network error'));

    const { result } = renderHook(() => useUserPreferences());

    await waitFor(() => expect(result.current.initialized).toBe(true));

    await act(async () => {
      try {
        await result.current.updatePreference('ui.theme', 'light');
      } catch (e) {
        // expected
      }
    });

    expect(result.current.preferences['ui.theme']).toBe('dark'); // rolled back
    expect(result.current.error).toContain('Network error');
  });

  it('bulkUpdate updates multiple preferences', async () => {
    mockApi.getAll.mockResolvedValue([]);
    mockApi.getDefaults.mockResolvedValue({ defaults: {}, categories: {} });
    mockApi.bulkUpdate.mockResolvedValue({ status: 'success', results: { success: ['ui.theme', 'ui.font_size'], failed: [] } });

    const { result } = renderHook(() => useUserPreferences());

    await waitFor(() => expect(result.current.initialized).toBe(true));

    await act(async () => {
      await result.current.bulkUpdate({ 'ui.theme': 'light', 'ui.font_size': 'large' });
    });

    expect(result.current.preferences['ui.theme']).toBe('light');
    expect(result.current.preferences['ui.font_size']).toBe('large');
    expect(mockApi.bulkUpdate).toHaveBeenCalledWith({ preferences: { 'ui.theme': 'light', 'ui.font_size': 'large' }, reason: undefined });
  });

  it('getPreference returns default when key not found', async () => {
    mockApi.getAll.mockResolvedValue([]);
    mockApi.getDefaults.mockResolvedValue({ defaults: { 'ui.theme': 'dark' }, categories: {} });

    const { result } = renderHook(() => useUserPreferences());

    await waitFor(() => expect(result.current.initialized).toBe(true));

    expect(result.current.getPreference('ui.theme')).toBe('dark');
    expect(result.current.getPreference('nonexistent', 'fallback')).toBe('fallback');
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm test -- frontend/src/hooks/__tests__/useUserPreferences.test.ts`
Expected: FAIL - module not found

- [ ] **Step 3: Write minimal implementation**

```typescript
// frontend/src/hooks/useUserPreferences.ts
import { useState, useEffect, useCallback } from 'react';
import { preferencesApi, Preference, PreferenceUpdateRequest, PreferenceBulkUpdateRequest } from '@/services/preferences';
import { useAuthStore } from '@/store/authStore';
import { showToast } from '@/hooks/useToast';

const DEFAULT_PREFERENCES: Record<string, any> = {
  'ui.theme': 'dark',
  'ui.language': 'en',
  'ui.sidebar_collapsed': false,
  'ui.font_size': 'medium',
  'chat.history_limit': 50,
  'chat.context_window_size': 10,
  'chat.auto_save': true,
  'chat.show_typing_indicator': true,
  'chat.prune_enabled': true,
  'chat.prune_inactivity_days': 7,
  'chat.prune_hard_delete_days': 30,
  'chat.prune_retain_count': 10,
  'chat.prune_schedule_cron': '0 3 * * *',
  'notifications.enabled': true,
  'notifications.sound': true,
  'notifications.channels': ['websocket', 'email'],
  'agents.default_timeout': 300,
  'agents.max_concurrent_tasks': 5,
  'agents.idle_timeout_minutes': 30,
  'tasks.auto_archive_days': 30,
  'tasks.default_priority': 'normal',
  'models.default_temperature': 0.7,
  'models.default_max_tokens': 4000,
  'privacy.share_usage_analytics': false,
  'tools.max_execution_time': 60,
  'tools.auto_retry_failed': true,
};

export function useUserPreferences() {
  const { user } = useAuthStore();
  const [preferences, setPreferences] = useState<Record<string, any>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [initialized, setInitialized] = useState(false);

  const mergePreferences = useCallback((userPrefs: Preference[], defaults: Record<string, any>) => {
    const merged = { ...defaults };
    for (const pref of userPrefs) {
      merged[pref.key] = pref.value;
    }
    return merged;
  }, []);

  const loadPreferences = useCallback(async () => {
    if (!user?.id) {
      setPreferences(DEFAULT_PREFERENCES);
      setLoading(false);
      setInitialized(true);
      return;
    }

    setLoading(true);
    setError(null);

    try {
      const [userPrefs, defaultsResponse] = await Promise.all([
        preferencesApi.getAll(),
        preferencesApi.getDefaults(),
      ]);

      const merged = mergePreferences(userPrefs, { ...DEFAULT_PREFERENCES, ...defaultsResponse.defaults });
      setPreferences(merged);
      setInitialized(true);

      // Auto-initialize if user has no preferences
      if (userPrefs.length === 0) {
        await preferencesApi.initializeDefaults();
        const freshPrefs = await preferencesApi.getAll();
        const freshMerged = mergePreferences(freshPrefs, { ...DEFAULT_PREFERENCES, ...defaultsResponse.defaults });
        setPreferences(freshMerged);
      }
    } catch (err: any) {
      setError(err.message || 'Failed to load preferences');
      setPreferences(DEFAULT_PREFERENCES);
    } finally {
      setLoading(false);
      setInitialized(true);
    }
  }, [user?.id, mergePreferences]);

  useEffect(() => {
    loadPreferences();
  }, [loadPreferences]);

  const updatePreference = useCallback(async (key: string, value: any) => {
    const previousValue = preferences[key];
    setPreferences(prev => ({ ...prev, [key]: value }));
    setError(null);

    try {
      await preferencesApi.update(key, { value });
    } catch (err: any) {
      setPreferences(prev => ({ ...prev, [key]: previousValue }));
      const message = err.message || 'Failed to update preference';
      setError(message);
      showToast.error(message);
      throw err;
    }
  }, [preferences]);

  const bulkUpdate = useCallback(async (prefs: Record<string, any>) => {
    const previousValues: Record<string, any> = {};
    for (const key of Object.keys(prefs)) {
      previousValues[key] = preferences[key];
    }
    setPreferences(prev => ({ ...prev, ...prefs }));
    setError(null);

    try {
      await preferencesApi.bulkUpdate({ preferences: prefs });
    } catch (err: any) {
      setPreferences(prev => {
        const reverted = { ...prev };
        for (const key of Object.keys(prefs)) {
          if (previousValues[key] !== undefined) {
            reverted[key] = previousValues[key];
          } else {
            delete reverted[key];
          }
        }
        return reverted;
      });
      const message = err.message || 'Failed to update preferences';
      setError(message);
      showToast.error(message);
      throw err;
    }
  }, [preferences]);

  const refresh = useCallback(async () => {
    await loadPreferences();
  }, [loadPreferences]);

  const getPreference = useCallback((key: string, defaultValue?: any) => {
    if (key in preferences) return preferences[key];
    if (key in DEFAULT_PREFERENCES) return DEFAULT_PREFERENCES[key];
    return defaultValue;
  }, [preferences]);

  return {
    preferences,
    loading,
    error,
    initialized,
    updatePreference,
    bulkUpdate,
    refresh,
    getPreference,
  };
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npm test -- frontend/src/hooks/__tests__/useUserPreferences.test.ts`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/hooks/useUserPreferences.ts frontend/src/hooks/__tests__/useUserPreferences.test.ts
git commit -m "feat: add useUserPreferences hook with optimistic updates and tests"
```

### Task 3: PreferenceInput Component (`PreferenceInput.tsx`)

**Files:**
- Create: `frontend/src/components/settings/PreferenceInput.tsx`
- Test: `frontend/src/components/settings/__tests__/PreferenceInput.test.tsx`

**Interfaces:**
- Consumes: 
  - `preference: { key: string; value: any; data_type: string; description?: string; category: string }`
  - `onChange: (key: string, value: any) => void`
  - `disabled?: boolean`
- Produces: Polymorphic input component rendering appropriate UI for each `data_type`

**Input Types Mapping:**
| data_type | Component | Details |
|-----------|-----------|---------|
| boolean | Toggle switch | Checkbox styled as switch with label |
| integer | Number input | step=1, min/max if known |
| float | Number input | step=0.1 or 0.01 |
| string | Text input | Standard text field |
| array | Multi-select | Select with multiple, or tag input for strings |
| json | Textarea | Monospace, JSON validation on blur |

- [ ] **Step 1: Write the failing test**

```tsx
// frontend/src/components/settings/__tests__/PreferenceInput.test.tsx
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { PreferenceInput } from '@/components/settings/PreferenceInput';

describe('PreferenceInput', () => {
  const mockOnChange = jest.fn();

  beforeEach(() => {
    mockOnChange.clear();
  });

  it('renders toggle switch for boolean type', () => {
    render(
      <PreferenceInput
        preference={{ key: 'notifications.enabled', value: true, data_type: 'boolean', category: 'notifications' }}
        onChange={mockOnChange}
      />
    );

    const checkbox = screen.getByRole('checkbox', { name: /notifications.enabled/i });
    expect(checkbox).toBeChecked();
  });

  it('calls onChange with inverted boolean when clicked', () => {
    render(
      <PreferenceInput
        preference={{ key: 'ui.sidebar_collapsed', value: false, data_type: 'boolean', category: 'ui' }}
        onChange={mockOnChange}
      />
    );

    fireEvent.click(screen.getByRole('checkbox'));
    expect(mockOnChange).toHaveBeenCalledWith('ui.sidebar_collapsed', true);
  });

  it('renders number input for integer type', () => {
    render(
      <PreferenceInput
        preference={{ key: 'chat.history_limit', value: 50, data_type: 'integer', category: 'chat' }}
        onChange={mockOnChange}
      />
    );

    const input = screen.getByRole('spinbutton', { name: /chat.history_limit/i });
    expect(input).toHaveValue(50);
  });

  it('calls onChange with parsed integer on blur', () => {
    render(
      <PreferenceInput
        preference={{ key: 'agents.max_concurrent_tasks', value: 5, data_type: 'integer', category: 'agents' }}
        onChange={mockOnChange}
      />
    );

    const input = screen.getByRole('spinbutton');
    fireEvent.change(input, { target: { value: '10' } });
    fireEvent.blur(input);
    expect(mockOnChange).toHaveBeenCalledWith('agents.max_concurrent_tasks', 10);
  });

  it('renders number input with step for float type', () => {
    render(
      <PreferenceInput
        preference={{ key: 'models.default_temperature', value: 0.7, data_type: 'float', category: 'models' }}
        onChange={mockOnChange}
      />
    );

    const input = screen.getByRole('spinbutton', { name: /models.default_temperature/i });
    expect(input).toHaveValue(0.7);
    expect(input).toHaveAttribute('step', '0.1');
  });

  it('renders text input for string type', () => {
    render(
      <PreferenceInput
        preference={{ key: 'ui.language', value: 'en', data_type: 'string', category: 'ui' }}
        onChange={mockOnChange}
      />
    );

    const input = screen.getByRole('textbox', { name: /ui.language/i });
    expect(input).toHaveValue('en');
  });

  it('renders textarea for json type', () => {
    render(
      <PreferenceInput
        preference={{ key: 'custom.json_config', value: { a: 1 }, data_type: 'json', category: 'custom' }}
        onChange={mockOnChange}
      />
    );

    const textarea = screen.getByRole('textbox', { name: /custom.json_config/i });
    expect(textarea).toHaveValue('{\n  "a": 1\n}');
  });

  it('validates JSON on blur and calls onChange with parsed object', () => {
    render(
      <PreferenceInput
        preference={{ key: 'custom.data', value: {}, data_type: 'json', category: 'custom' }}
        onChange={mockOnChange}
      />
    );

    const textarea = screen.getByRole('textbox');
    fireEvent.change(textarea, { target: { value: '{"b": 2}' } });
    fireEvent.blur(textarea);
    expect(mockOnChange).toHaveBeenCalledWith('custom.data', { b: 2 });
  });

  it('shows error for invalid JSON', () => {
    render(
      <PreferenceInput
        preference={{ key: 'custom.data', value: {}, data_type: 'json', category: 'custom' }}
        onChange={mockOnChange}
      />
    );

    const textarea = screen.getByRole('textbox');
    fireEvent.change(textarea, { target: { value': '{invalid' } });
    fireEvent.blur(textarea);
    expect(screen.getByText(/invalid json/i)).toBeInTheDocument();
    expect(mockOnChange).not.toHaveBeenCalled();
  });

  it('renders multi-select for array type', () => {
    render(
      <PreferenceInput
        preference={{ key: 'notifications.channels', value: ['websocket'], data_type: 'array', category: 'notifications' }}
        onChange={mockOnChange}
      />
    );

    const select = screen.getByRole('listbox', { name: /notifications.channels/i });
    expect(select).toBeInTheDocument();
    // Check that 'websocket' option is selected
  });

  it('disables input when disabled prop is true', () => {
    render(
      <PreferenceInput
        preference={{ key: 'ui.theme', value: 'dark', data_type: 'string', category: 'ui' }}
        onChange={mockOnChange}
        disabled
      />
    );

    const input = screen.getByRole('textbox');
    expect(input).toBeDisabled();
  });

  it('shows description as helper text when provided', () => {
    render(
      <PreferenceInput
        preference={{ 
          key: 'ui.font_size', 
          value: 'medium', 
          data_type: 'string', 
          category: 'ui',
          description: 'Base font size for the interface' 
        }}
        onChange={mockOnChange}
      />
    );

    expect(screen.getByText(/base font size for the interface/i)).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm test -- frontend/src/components/settings/__tests__/PreferenceInput.test.tsx`
Expected: FAIL - module not found

- [ ] **Step 3: Write minimal implementation**

```tsx
// frontend/src/components/settings/PreferenceInput.tsx
import React, { useState, useRef, useEffect } from 'react';
import { Toggle } from '@/components/ui/Toggle';
import { AlertCircle } from 'lucide-react';

interface PreferenceInputProps {
  preference: {
    key: string;
    value: any;
    data_type: 'boolean' | 'integer' | 'float' | 'string' | 'array' | 'json';
    description?: string;
    category: string;
  };
  onChange: (key: string, value: any) => void;
  disabled?: boolean;
}

const inputClass = 'w-full px-3 py-2 text-sm bg-white dark:bg-[#0f1117] border border-gray-200 dark:border-[#1e2535] rounded-lg text-gray-900 dark:text-white placeholder-gray-400 dark:placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500/40 focus:border-blue-500 transition-colors duration-150 disabled:opacity-50 disabled:cursor-not-allowed';

export function PreferenceInput({ preference, onChange, disabled }: PreferenceInputProps) {
  const { key, value, data_type, description, category } = preference;
  const [jsonError, setJsonError] = useState<string | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Format value for display based on type
  const formatValue = (val: any, type: string): string => {
    if (type === 'json') return JSON.stringify(val, null, 2);
    if (type === 'array') return JSON.stringify(val);
    return String(val ?? '');
  };

  const parseValue = (val: string, type: string): any => {
    if (type === 'integer') return parseInt(val, 10) || 0;
    if (type === 'float') return parseFloat(val) || 0;
    if (type === 'boolean') return val === 'true';
    if (type === 'json') {
      try {
        return JSON.parse(val);
      } catch {
        throw new Error('Invalid JSON');
      }
    }
    if (type === 'array') {
      try {
        return JSON.parse(val);
      } catch {
        return val.split(',').map(s => s.trim()).filter(Boolean);
      }
    }
    return val;
  };

  const handleBlur = (e: React.FocusEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) => {
    if (disabled) return;
    try {
      const parsed = parseValue(e.currentTarget.value, data_type);
      if (data_type === 'json') setJsonError(null);
      onChange(key, parsed);
    } catch (err: any) {
      if (data_type === 'json') setJsonError(err.message);
    }
  };

  const handleChange = (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) => {
    if (disabled) return;
    if (data_type === 'json') setJsonError(null);
  };

  const handleCheckboxChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (disabled) return;
    onChange(key, e.target.checked);
  };

  const handleSelectChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    if (disabled) return;
    const selected = Array.from(e.target.selectedOptions).map(o => o.value);
    try {
      // Try to parse as JSON first (for arrays of objects), fallback to string array
      const parsed = selected.length === 1 ? JSON.parse(selected[0]) : selected;
      onChange(key, parsed);
    } catch {
      onChange(key, selected);
    }
  };

  switch (data_type) {
    case 'boolean': {
      return (
        <div className="flex items-center gap-3">
          <label className="relative inline-flex items-center cursor-pointer">
            <input
              type="checkbox"
              role="switch"
              checked={Boolean(value)}
              onChange={handleCheckboxChange}
              disabled={disabled}
              className="sr-only peer"
              aria-label={key}
            />
            <div className="w-11 h-6 bg-gray-200 dark:bg-[#1e2535] peer-focus:outline-none peer-focus:ring-4 peer-focus:ring-blue-500/30 rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all dark:border-gray-600 peer-checked:bg-blue-600" />
          </label>
          <span className="text-sm text-gray-900 dark:text-white capitalize">{key.split('.').pop()}</span>
        </div>
      );
    }

    case 'integer':
    case 'float': {
      const step = data_type === 'float' ? 0.1 : 1;
      return (
        <div className="flex flex-col gap-1.5">
          <input
            type="number"
            step={step}
            value={formatValue(value, data_type)}
            onChange={handleChange}
            onBlur={handleBlur}
            disabled={disabled}
            className={inputClass}
            aria-label={key}
            id={key}
          />
          {description && <p className="text-xs text-gray-500 dark:text-gray-400">{description}</p>}
        </div>
      );
    }

    case 'string': {
      return (
        <div className="flex flex-col gap-1.5">
          <input
            type="text"
            value={formatValue(value, data_type)}
            onChange={handleChange}
            onBlur={handleBlur}
            disabled={disabled}
            className={inputClass}
            aria-label={key}
            id={key}
            placeholder={`Enter ${key.split('.').pop()}`}
          />
          {description && <p className="text-xs text-gray-500 dark:text-gray-400">{description}</p>}
        </div>
      );
    }

    case 'json': {
      return (
        <div className="flex flex-col gap-1.5">
          <textarea
            ref={textareaRef}
            value={formatValue(value, data_type)}
            onChange={handleChange}
            onBlur={handleBlur}
            disabled={disabled}
            className={`${inputClass} font-mono text-xs min-h-[80px] resize-y`}
            aria-label={key}
            id={key}
            placeholder="Enter valid JSON"
            spellCheck={false}
          />
          {jsonError && (
            <div className="flex items-center gap-1.5 text-xs text-red-600 dark:text-red-400">
              <AlertCircle className="w-3.5 h-3.5 flex-shrink-0" />
              <span>Invalid JSON: {jsonError}</span>
            </div>
          )}
          {description && !jsonError && <p className="text-xs text-gray-500 dark:text-gray-400">{description}</p>}
        </div>
      );
    }

    case 'array': {
      // For array, render as multi-select with common options
      const arrayValue = Array.isArray(value) ? value : [];
      const options = category === 'notifications' 
        ? ['websocket', 'email', 'slack', 'webhook']
        : [];

      return (
        <div className="flex flex-col gap-1.5">
          <select
            multiple
            value={arrayValue}
            onChange={handleSelectChange}
            onBlur={handleBlur}
            disabled={disabled}
            className={`${inputClass} min-h-[100px] py-2`}
            aria-label={key}
            id={key}
          >
            {options.map(opt => (
              <option key={opt} value={opt}>{opt}</option>
            ))}
          </select>
          <p className="text-xs text-gray-500 dark:text-gray-400">
            Hold Ctrl/Cmd to select multiple. {description || ''}
          </p>
        </div>
      );
    }

    default: {
      return (
        <div className="flex flex-col gap-1.5">
          <input
            type="text"
            value={formatValue(value, data_type)}
            onChange={handleChange}
            onBlur={handleBlur}
            disabled={disabled}
            className={inputClass}
            aria-label={key}
            id={key}
          />
          {description && <p className="text-xs text-gray-500 dark:text-gray-400">{description}</p>}
        </div>
      );
    }
  }
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npm test -- frontend/src/components/settings/__tests__/PreferenceInput.test.tsx`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/settings/PreferenceInput.tsx frontend/src/components/settings/__tests__/PreferenceInput.test.tsx
git commit -m "feat: add PreferenceInput polymorphic component with tests"
```

### Task 4: PreferenceSection Component (`PreferenceSection.tsx`)

**Files:**
- Create: `frontend/src/components/settings/PreferenceSection.tsx`
- Test: `frontend/src/components/settings/__tests__/PreferenceSection.test.tsx`

**Interfaces:**
- Consumes:
  - `category: PreferenceCategory`
  - `preferences: Preference[]` - array of preference objects for this category
  - `onChange: (key: string, value: any) => void`
  - `disabled?: boolean`
  - `allPreferences: Record<string, any>` - for cross-reference
- Produces: Collapsible section with category header and preference inputs

**Behavior:**
- Renders category label + description (from CATEGORY_LABELS/DESCRIPTIONS)
- Collapsible with ChevronDown/Up icon
- Default expanded for first 3 categories (ui, chat, notifications), collapsed for others
- Maps each preference to PreferenceInput
- Shows loading skeleton while preferences loading

- [ ] **Step 1: Write the failing test**

```tsx
// frontend/src/components/settings/__tests__/PreferenceSection.test.tsx
import { render, screen, fireEvent } from '@testing-library/react';
import { PreferenceSection } from '@/components/settings/PreferenceSection';
import { CATEGORY_LABELS, CATEGORY_DESCRIPTIONS } from '@/services/preferences';

describe('PreferenceSection', () => {
  const mockOnChange = jest.fn();
  const mockPreferences = [
    { key: 'ui.theme', value: 'dark', data_type: 'string', category: 'ui', description: 'Color theme' },
    { key: 'ui.font_size', value: 'medium', data_type: 'string', category: 'ui', description: 'Base font size' },
  ];
  const allPreferences = { 'ui.theme': 'dark', 'ui.font_size': 'medium' };

  beforeEach(() => {
    mockOnChange.clear();
  });

  it('renders category label and description', () => {
    render(
      <PreferenceSection
        category="ui"
        preferences={mockPreferences}
        onChange={mockOnChange}
        allPreferences={allPreferences}
      />
    );

    expect(screen.getByText(CATEGORY_LABELS.ui)).toBeInTheDocument();
    expect(screen.getByText(CATEGORY_DESCRIPTIONS.ui)).toBeInTheDocument();
  });

  it('renders PreferenceInput for each preference', () => {
    render(
      <PreferenceSection
        category="ui"
        preferences={mockPreferences}
        onChange={mockOnChange}
        allPreferences={allPreferences}
      />
    );

    expect(screen.getByRole('textbox', { name: /ui.theme/i })).toBeInTheDocument();
    expect(screen.getByRole('textbox', { name: /ui.font_size/i })).toBeInTheDocument();
  });

  it('is expanded by default for ui category', () => {
    render(
      <PreferenceSection
        category="ui"
        preferences={mockPreferences}
        onChange={mockOnChange}
        allPreferences={allPreferences}
      />
    );

    expect(screen.getByRole('textbox', { name: /ui.theme/i })).toBeVisible();
  });

  it('is collapsed by default for privacy category', () => {
    render(
      <PreferenceSection
        category="privacy"
        preferences={mockPreferences}
        onChange={mockOnChange}
        allPreferences={allPreferences}
      />
    );

    expect(screen.queryByRole('textbox', { name: /ui.theme/i })).not.toBeInTheDocument();
  });

  it('toggles expansion when header clicked', () => {
    render(
      <PreferenceSection
        category="privacy"
        preferences={mockPreferences}
        onChange={mockOnChange}
        allPreferences={allPreferences}
      />
    );

    const header = screen.getByText(CATEGORY_LABELS.privacy).closest('button');
    fireEvent.click(header!);

    expect(screen.getByRole('textbox', { name: /ui.theme/i })).toBeInTheDocument();
  });

  it('passes disabled prop to PreferenceInput', () => {
    render(
      <PreferenceSection
        category="ui"
        preferences={mockPreferences}
        onChange={mockOnChange}
        allPreferences={allPreferences}
        disabled
      />
    );

    expect(screen.getByRole('textbox', { name: /ui.theme/i })).toBeDisabled();
  });

  it('shows empty state when no preferences in category', () => {
    render(
      <PreferenceSection
        category="custom"
        preferences={[]}
        onChange={mockOnChange}
        allPreferences={allPreferences}
      />
    );

    expect(screen.getByText(/no preferences in this category/i)).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm test -- frontend/src/components/settings/__tests__/PreferenceSection.test.tsx`
Expected: FAIL - module not found

- [ ] **Step 3: Write minimal implementation**

```tsx
// frontend/src/components/settings/PreferenceSection.tsx
import React, { useState } from 'react';
import { ChevronDown, FolderOpen, FolderClosed } from 'lucide-react';
import { PreferenceInput } from './PreferenceInput';
import { PreferenceCategory, CATEGORY_LABELS, CATEGORY_DESCRIPTIONS } from '@/services/preferences';

interface Preference {
  key: string;
  value: any;
  data_type: 'boolean' | 'integer' | 'float' | 'string' | 'array' | 'json';
  description?: string;
  category: string;
}

interface PreferenceSectionProps {
  category: PreferenceCategory;
  preferences: Preference[];
  onChange: (key: string, value: any) => void;
  disabled?: boolean;
  allPreferences: Record<string, any>;
}

const DEFAULT_EXPANDED: PreferenceCategory[] = ['ui', 'chat', 'notifications'];

export function PreferenceSection({ category, preferences, onChange, disabled, allPreferences }: PreferenceSectionProps) {
  const [expanded, setExpanded] = useState(() => DEFAULT_EXPANDED.includes(category));

  const label = CATEGORY_LABELS[category] || category;
  const description = CATEGORY_DESCRIPTIONS[category] || '';

  return (
    <div className="bg-white dark:bg-[#161b27] rounded-xl border border-gray-200 dark:border-[#1e2535] overflow-hidden transition-colors duration-200">
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full px-5 py-4 flex items-center justify-between text-left hover:bg-gray-50 dark:hover:bg-[#0f1117] transition-colors"
        aria-expanded={expanded}
      >
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-lg bg-blue-100 dark:bg-blue-500/10 flex items-center justify-center">
            <FolderOpen className="w-5 h-5 text-blue-600 dark:text-blue-400" />
          </div>
          <div>
            <h3 className="text-base font-semibold text-gray-900 dark:text-white">{label}</h3>
            <p className="text-xs text-gray-500 dark:text-gray-400">{description}</p>
          </div>
        </div>
        <ChevronDown
          className={`w-5 h-5 text-gray-400 dark:text-gray-500 transition-transform duration-200 ${expanded ? 'rotate-180' : ''}`}
          aria-hidden="true"
        />
      </button>

      <div className={expanded ? 'block' : 'hidden'} data-testid={`${category}-section-content`}>
        <div className="px-5 pb-5 pt-0 border-t border-gray-100 dark:border-[#1e2535]">
          {preferences.length === 0 ? (
            <p className="text-sm text-gray-500 dark:text-gray-400 py-4 text-center">
              No preferences in this category
            </p>
          ) : (
            <div className="space-y-4">
              {preferences.map((pref) => (
                <div key={pref.key} className="flex flex-col gap-2 sm:flex-row sm:items-center sm:gap-4">
                  <label
                    htmlFor={pref.key}
                    className="sm:w-48 sm:flex-shrink-0 text-sm font-medium text-gray-700 dark:text-gray-300"
                  >
                    {pref.key.split('.').pop()?.replace(/_/g, ' ')}
                  </label>
                  <div className="flex-1">
                    <PreferenceInput
                      preference={pref}
                      onChange={onChange}
                      disabled={disabled}
                    />
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npm test -- frontend/src/components/settings/__tests__/PreferenceSection.test.tsx`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/settings/PreferenceSection.tsx frontend/src/components/settings/__tests__/PreferenceSection.test.tsx
git commit -m "feat: add PreferenceSection collapsible category component with tests"
```

### Task 5: PreferencesTab Component (`PreferencesTab.tsx`)

**Files:**
- Create: `frontend/src/components/settings/PreferencesTab.tsx`
- Test: `frontend/src/components/settings/__tests__/PreferencesTab.test.tsx`

**Interfaces:**
- Consumes: `useUserPreferences` hook
- Produces: Complete preferences panel with all 8 category sections

**Behavior:**
- Calls `useUserPreferences()` to get preferences, loading, error, updatePreference, bulkUpdate
- Groups preferences by category (from preference.category field)
- Renders PreferenceSection for each category
- Shows loading skeletons while fetching
- Shows error banner with retry on fetch failure
- Handles bulk updates efficiently (debounced or batched)
- Passes allPreferences to each section for cross-reference

- [ ] **Step 1: Write the failing test**

```tsx
// frontend/src/components/settings/__tests__/PreferencesTab.test.tsx
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { PreferencesTab } from '@/components/settings/PreferencesTab';
import { useUserPreferences } from '@/hooks/useUserPreferences';
import { PreferenceCategory } from '@/services/preferences';

jest.mock('@/hooks/useUserPreferences');

const mockUseUserPreferences = useUserPreferences as jest.MockedFunction<typeof useUserPreferences>;

describe('PreferencesTab', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('shows loading skeletons while fetching', () => {
    mockUseUserPreferences.mockReturnValue({
      preferences: {},
      loading: true,
      error: null,
      initialized: false,
      updatePreference: jest.fn(),
      bulkUpdate: jest.fn(),
      refresh: jest.fn(),
      getPreference: jest.fn(),
    });

    render(<PreferencesTab />);

    expect(screen.getByText(/loading preferences/i)).toBeInTheDocument();
    // Should show skeleton cards for each category
    expect(screen.getAllByTestId(/skeleton/)).toHaveLength(8);
  });

  it('renders all 8 category sections when loaded', () => {
    mockUseUserPreferences.mockReturnValue({
      preferences: {
        'ui.theme': 'dark',
        'ui.font_size': 'medium',
        'chat.history_limit': 50,
        'notifications.enabled': true,
        'agents.max_concurrent_tasks': 5,
        'tasks.auto_archive_days': 30,
        'models.default_temperature': 0.7,
        'tools.max_execution_time': 60,
        'privacy.share_usage_analytics': false,
      },
      loading: false,
      error: null,
      initialized: true,
      updatePreference: jest.fn(),
      bulkUpdate: jest.fn(),
      refresh: jest.fn(),
      getPreference: jest.fn(),
    });

    render(<PreferencesTab />);

    for (const cat of ['ui', 'chat', 'notifications', 'agents', 'tasks', 'models', 'tools', 'privacy'] as PreferenceCategory[]) {
      expect(screen.getByText(cat.charAt(0).toUpperCase() + cat.slice(1))).toBeInTheDocument();
    }
  });

  it('shows error banner with retry button on fetch failure', () => {
    mockUseUserPreferences.mockReturnValue({
      preferences: {},
      loading: false,
      error: 'Network error',
      initialized: true,
      updatePreference: jest.fn(),
      bulkUpdate: jest.fn(),
      refresh: jest.fn(),
      getPreference: jest.fn(),
    });

    render(<PreferencesTab />);

    expect(screen.getByText(/failed to load preferences/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /retry/i })).toBeInTheDocument();
  });

  it('calls updatePreference when input changes', async () => {
    const mockUpdate = jest.fn();
    mockUseUserPreferences.mockReturnValue({
      preferences: { 'ui.theme': 'dark' },
      loading: false,
      error: null,
      initialized: true,
      updatePreference: mockUpdate,
      bulkUpdate: jest.fn(),
      refresh: jest.fn(),
      getPreference: jest.fn(),
    });

    render(<PreferencesTab />);

    const input = screen.getByRole('textbox', { name: /ui.theme/i });
    fireEvent.change(input, { target: { value: 'light' } });
    fireEvent.blur(input);

    await waitFor(() => expect(mockUpdate).toHaveBeenCalledWith('ui.theme', 'light'));
  });

  it('disables inputs when loading', () => {
    mockUseUserPreferences.mockReturnValue({
      preferences: { 'ui.theme': 'dark' },
      loading: true,
      error: null,
      initialized: false,
      updatePreference: jest.fn(),
      bulkUpdate: jest.fn(),
      refresh: jest.fn(),
      getPreference: jest.fn(),
    });

    render(<PreferencesTab />);

    // During loading, no inputs should be rendered (skeletons instead)
    expect(screen.queryByRole('textbox', { name: /ui.theme/i })).not.toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm test -- frontend/src/components/settings/__tests__/PreferencesTab.test.tsx`
Expected: FAIL - module not found

- [ ] **Step 3: Write minimal implementation**

```tsx
// frontend/src/components/settings/PreferencesTab.tsx
import React, { useMemo } from 'react';
import { useUserPreferences } from '@/hooks/useUserPreferences';
import { PreferenceSection } from './PreferenceSection';
import { PreferenceCategory, CATEGORY_LABELS } from '@/services/preferences';
import { LoadingSpinner } from '@/components/ui/LoadingSpinner';
import { showToast } from '@/hooks/useToast';

interface Preference {
  key: string;
  value: any;
  data_type: 'boolean' | 'integer' | 'float' | 'string' | 'array' | 'json';
  description?: string;
  category: string;
}

const SKELETON_CATEGORIES: PreferenceCategory[] = ['ui', 'chat', 'notifications', 'agents', 'tasks', 'models', 'tools', 'privacy'];

export function PreferencesTab() {
  const { preferences, loading, error, initialized, updatePreference, bulkUpdate, refresh, getPreference } = useUserPreferences();

  const categorizedPrefs = useMemo((): Record<PreferenceCategory, Preference[]> => {
    const result: Record<string, Preference[]> = {};
    for (const cat of SKELETON_CATEGORIES) {
      result[cat] = [];
    }

    for (const [key, value] of Object.entries(preferences)) {
      const category = key.split('.')[0] as PreferenceCategory;
      if (result[category]) {
        result[category].push({
          key,
          value,
          data_type: typeof value === 'boolean' ? 'boolean' : 
                     typeof value === 'number' ? (Number.isInteger(value) ? 'integer' : 'float') :
                     Array.isArray(value) ? 'array' :
                     typeof value === 'object' ? 'json' : 'string',
          category,
        });
      }
    }
    return result as Record<PreferenceCategory, Preference[]>;
  }, [preferences]);

  const handleChange = (key: string, value: any) => {
    updatePreference(key, value);
  };

  if (loading && !initialized) {
    return (
      <div className="space-y-4" role="status" aria-label="Loading preferences">
        {SKELETON_CATEGORIES.map(cat => (
          <div key={cat} className="bg-white dark:bg-[#161b27] rounded-xl border border-gray-200 dark:border-[#1e2535] p-5 animate-pulse" data-testid="skeleton">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-lg bg-gray-200 dark:bg-[#1e2535]" />
              <div className="flex-1">
                <div className="h-4 w-32 bg-gray-200 dark:bg-[#1e2535] rounded mb-1" />
                <div className="h-3 w-48 bg-gray-200 dark:bg-[#1e2535] rounded" />
              </div>
            </div>
          </div>
        ))}
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-4 bg-red-50 dark:bg-red-500/10 border border-red-200 dark:border-red-500/20 rounded-xl" role="alert">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-lg bg-red-100 dark:bg-red-500/10 flex items-center justify-center">
              <svg className="w-5 h-5 text-red-600 dark:text-red-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
              </svg>
            </div>
            <div>
              <p className="font-medium text-red-900 dark:text-red-300">Failed to load preferences</p>
              <p className="text-sm text-red-700 dark:text-red-400/80">{error}</p>
            </div>
          </div>
          <button
            onClick={async () => {
              try {
                await refresh();
              } catch {
                showToast.error('Retry failed');
              }
            }}
            className="px-3 py-1.5 bg-red-100 dark:bg-red-500/10 hover:bg-red-200 dark:hover:bg-red-500/20 text-red-700 dark:text-red-400 rounded-lg text-sm font-medium transition-colors"
          >
            Retry
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {SKELETON_CATEGORIES.map(category => (
        <PreferenceSection
          key={category}
          category={category}
          preferences={categorizedPrefs[category] || []}
          onChange={handleChange}
          allPreferences={preferences}
        />
      ))}
    </div>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npm test -- frontend/src/components/settings/__tests__/PreferencesTab.test.tsx`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/settings/PreferencesTab.tsx frontend/src/components/settings/__tests__/PreferencesTab.test.tsx
git commit -m "feat: add PreferencesTab main panel with all categories and tests"
```

### Task 6: ThemeSelector Component (`ThemeSelector.tsx`)

**Files:**
- Create: `frontend/src/components/settings/ThemeSelector.tsx`
- Test: `frontend/src/components/settings/__tests__/ThemeSelector.test.tsx`

**Interfaces:**
- Consumes: `useUserPreferences` hook (for `ui.theme` preference), `isDarkMode`, `setDarkMode` from `@/utils/theme`
- Produces: Theme selector with 3 options (Light, Dark, System)

**Behavior:**
- Reads `ui.theme` preference (values: 'light' | 'dark' | 'system')
- On mount: applies theme to document.documentElement
- On change: calls `setDarkMode()` + updates `ui.theme` preference via `updatePreference`
- System option: follows `window.matchMedia('(prefers-color-scheme: dark)')`
- Visual: 3 radio cards with icons (Sun, Moon, Monitor)

- [ ] **Step 1: Write the failing test**

```tsx
// frontend/src/components/settings/__tests__/ThemeSelector.test.tsx
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { ThemeSelector } from '@/components/settings/ThemeSelector';
import { useUserPreferences } from '@/hooks/useUserPreferences';
import { isDarkMode, setDarkMode } from '@/utils/theme';

jest.mock('@/hooks/useUserPreferences');
jest.mock('@/utils/theme');

const mockUseUserPreferences = useUserPreferences as jest.MockedFunction<typeof useUserPreferences>;
const mockIsDarkMode = isDarkMode as jest.MockedFunction<typeof isDarkMode>;
const mockSetDarkMode = setDarkMode as jest.MockedFunction<typeof setDarkMode>;

describe('ThemeSelector', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockIsDarkMode.mockReturnValue(false);
  });

  it('renders three theme options', () => {
    mockUseUserPreferences.mockReturnValue({
      preferences: { 'ui.theme': 'system' },
      loading: false,
      error: null,
      initialized: true,
      updatePreference: jest.fn(),
      bulkUpdate: jest.fn(),
      refresh: jest.fn(),
      getPreference: (key: string) => key === 'ui.theme' ? 'system' : undefined,
    });

    render(<ThemeSelector />);

    expect(screen.getByRole('radio', { name: /light/i })).toBeInTheDocument();
    expect(screen.getByRole('radio', { name: /dark/i })).toBeInTheDocument();
    expect(screen.getByRole('radio', { name: /system/i })).toBeInTheDocument();
  });

  it('shows System as selected when ui.theme is system', () => {
    mockUseUserPreferences.mockReturnValue({
      preferences: { 'ui.theme': 'system' },
      loading: false,
      error: null,
      initialized: true,
      updatePreference: jest.fn(),
      bulkUpdate: jest.fn(),
      refresh: jest.fn(),
      getPreference: (key: string) => key === 'ui.theme' ? 'system' : undefined,
    });

    render(<ThemeSelector />);

    expect(screen.getByRole('radio', { name: /system/i })).toBeChecked();
  });

  it('shows Dark as selected when ui.theme is dark', () => {
    mockUseUserPreferences.mockReturnValue({
      preferences: { 'ui.theme': 'dark' },
      loading: false,
      error: null,
      initialized: true,
      updatePreference: jest.fn(),
      bulkUpdate: jest.fn(),
      refresh: jest.fn(),
      getPreference: (key: string) => key === 'ui.theme' ? 'dark' : undefined,
    });

    render(<ThemeSelector />);

    expect(screen.getByRole('radio', { name: /dark/i })).toBeChecked();
  });

  it('calls setDarkMode(true) and updatePreference when Dark selected', async () => {
    const mockUpdate = jest.fn();
    mockUseUserPreferences.mockReturnValue({
      preferences: { 'ui.theme': 'light' },
      loading: false,
      error: null,
      initialized: true,
      updatePreference: mockUpdate,
      bulkUpdate: jest.fn(),
      refresh: jest.fn(),
      getPreference: (key: string) => key === 'ui.theme' ? 'light' : undefined,
    });

    render(<ThemeSelector />);

    fireEvent.click(screen.getByRole('radio', { name: /dark/i }));

    await waitFor(() => {
      expect(mockSetDarkMode).toHaveBeenCalledWith(true);
      expect(mockUpdate).toHaveBeenCalledWith('ui.theme', 'dark');
    });
  });

  it('calls setDarkMode(false) when Light selected', async () => {
    const mockUpdate = jest.fn();
    mockUseUserPreferences.mockReturnValue({
      preferences: { 'ui.theme': 'dark' },
      loading: false,
      error: null,
      initialized: true,
      updatePreference: mockUpdate,
      bulkUpdate: jest.fn(),
      refresh: jest.fn(),
      getPreference: (key: string) => key === 'ui.theme' ? 'dark' : undefined,
    });

    render(<ThemeSelector />);

    fireEvent.click(screen.getByRole('radio', { name: /light/i }));

    await waitFor(() => {
      expect(mockSetDarkMode).toHaveBeenCalledWith(false);
      expect(mockUpdate).toHaveBeenCalledWith('ui.theme', 'light');
    });
  });

  it('handles System option with media query', async () => {
    const mockUpdate = jest.fn();
    const mockMatchMedia = jest.fn().mockReturnValue({ matches: true, addEventListener: jest.fn(), removeEventListener: jest.fn() });
    Object.defineProperty(window, 'matchMedia', { value: mockMatchMedia, writable: true });

    mockUseUserPreferences.mockReturnValue({
      preferences: { 'ui.theme': 'system' },
      loading: false,
      error: null,
      initialized: true,
      updatePreference: mockUpdate,
      bulkUpdate: jest.fn(),
      refresh: jest.fn(),
      getPreference: (key: string) => key === 'ui.theme' ? 'system' : undefined,
    });

    render(<ThemeSelector />);

    fireEvent.click(screen.getByRole('radio', { name: /light/i }));
    fireEvent.click(screen.getByRole('radio', { name: /system/i }));

    await waitFor(() => {
      expect(mockUpdate).toHaveBeenCalledWith('ui.theme', 'system');
    });
  });

  it('shows loading state while preferences loading', () => {
    mockUseUserPreferences.mockReturnValue({
      preferences: {},
      loading: true,
      error: null,
      initialized: false,
      updatePreference: jest.fn(),
      bulkUpdate: jest.fn(),
      refresh: jest.fn(),
      getPreference: jest.fn(),
    });

    render(<ThemeSelector />);

    expect(screen.getByText(/loading theme/i)).toBeInTheDocument();
  });

  it('disables radios when update in progress', () => {
    let resolveUpdate: (value: void) => void;
    const updatePromise = new Promise<void>(resolve => { resolveUpdate = resolve; });
    
    mockUseUserPreferences.mockReturnValue({
      preferences: { 'ui.theme': 'system' },
      loading: false,
      error: null,
      initialized: true,
      updatePreference: jest.fn(() => updatePromise),
      bulkUpdate: jest.fn(),
      refresh: jest.fn(),
      getPreference: (key: string) => key === 'ui.theme' ? 'system' : undefined,
    });

    render(<ThemeSelector />);

    fireEvent.click(screen.getByRole('radio', { name: /dark/i }));
    expect(screen.getByRole('radio', { name: /dark/i })).toBeDisabled();
    
    resolveUpdate!();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm test -- frontend/src/components/settings/__tests__/ThemeSelector.test.tsx`
Expected: FAIL - module not found

- [ ] **Step 3: Write minimal implementation**

```tsx
// frontend/src/components/settings/ThemeSelector.tsx
import React, { useEffect, useState } from 'react';
import { Sun, Moon, Monitor, Check } from 'lucide-react';
import { useUserPreferences } from '@/hooks/useUserPreferences';
import { isDarkMode, setDarkMode } from '@/utils/theme';

type ThemeOption = 'light' | 'dark' | 'system';

const THEME_OPTIONS: { value: ThemeOption; label: string; icon: React.ReactNode; description: string }[] = [
  { value: 'light', label: 'Light', icon: <Sun className="w-5 h-5" />, description: 'Always use light mode' },
  { value: 'dark', label: 'Dark', icon: <Moon className="w-5 h-5" />, description: 'Always use dark mode' },
  { value: 'system', label: 'System', icon: <Monitor className="w-5 h-5" />, description: 'Follow system preference' },
];

export function ThemeSelector() {
  const { preferences, loading, initialized, updatePreference, getPreference } = useUserPreferences();
  const [currentTheme, setCurrentTheme] = useState<ThemeOption>('system');
  const [updating, setUpdating] = useState(false);

  // Initialize from preference
  useEffect(() => {
    if (initialized) {
      const theme = getPreference('ui.theme', 'system') as ThemeOption;
      setCurrentTheme(theme);
    }
  }, [initialized, getPreference]);

  // Apply theme on mount and when system preference changes
  useEffect(() => {
    if (!initialized) return;
    
    const applyTheme = (theme: ThemeOption) => {
      if (theme === 'system') {
        const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
        setDarkMode(prefersDark);
      } else {
        setDarkMode(theme === 'dark');
      }
    };

    applyTheme(currentTheme);

    // Listen for system theme changes when in system mode
    if (currentTheme === 'system') {
      const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)');
      const handler = (e: MediaQueryListEvent) => setDarkMode(e.matches);
      mediaQuery.addEventListener('change', handler);
      return () => mediaQuery.removeEventListener('change', handler);
    }
  }, [currentTheme, initialized]);

  const handleThemeChange = async (theme: ThemeOption) => {
    if (updating) return;
    setUpdating(true);
    setCurrentTheme(theme);

    // Immediately apply to UI
    if (theme === 'system') {
      const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
      setDarkMode(prefersDark);
    } else {
      setDarkMode(theme === 'dark');
    }

    try {
      await updatePreference('ui.theme', theme);
    } catch {
      // Rollback on error
      const previousTheme = getPreference('ui.theme', 'system') as ThemeOption;
      setCurrentTheme(previousTheme);
      if (previousTheme === 'system') {
        const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
        setDarkMode(prefersDark);
      } else {
        setDarkMode(previousTheme === 'dark');
      }
    } finally {
      setUpdating(false);
    }
  };

  if (loading && !initialized) {
    return (
      <div className="flex items-center gap-3 text-sm text-gray-600 dark:text-gray-400">
        <LoadingSpinner size="sm" />
        <span>Loading theme...</span>
      </div>
    );
  }

  return (
    <div className="grid grid-cols-3 gap-3" role="radiogroup" aria-label="Theme selection">
      {THEME_OPTIONS.map(option => (
        <button
          key={option.value}
          role="radio"
          aria-checked={currentTheme === option.value}
          onClick={() => handleThemeChange(option.value)}
          disabled={updating}
          className={`relative p-4 rounded-xl border-2 transition-all duration-200 flex flex-col items-center gap-2 ${
            currentTheme === option.value
              ? 'border-blue-500 bg-blue-50 dark:bg-blue-500/10'
              : 'border-gray-200 dark:border-[#1e2535] bg-white dark:bg-[#161b27] hover:border-gray-300 dark:hover:border-[#2a3347]'
          }`}
        >
          <div className={`text-gray-600 dark:text-gray-400 ${currentTheme === option.value ? 'text-blue-600 dark:text-blue-400' : ''}`}>
            {option.icon}
          </div>
          <span className="font-medium text-sm text-gray-900 dark:text-white">{option.label}</span>
          <span className="text-xs text-gray-500 dark:text-gray-400 text-center">{option.description}</span>
          {currentTheme === option.value && (
            <div className="absolute top-2 right-2 w-5 h-5 rounded-full bg-blue-500 flex items-center justify-center">
              <Check className="w-3 h-3 text-white" />
            </div>
          )}
        </button>
      ))}
    </div>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npm test -- frontend/src/components/settings/__tests__/ThemeSelector.test.tsx`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/settings/ThemeSelector.tsx frontend/src/components/settings/__tests__/ThemeSelector.test.tsx
git commit -m "feat: add ThemeSelector component with Light/Dark/System options and tests"
```

### Task 7: ApiKeysTab Component (`ApiKeysTab.tsx`)

**Files:**
- Create: `frontend/src/components/settings/ApiKeysTab.tsx`
- Test: `frontend/src/components/settings/__tests__/ApiKeysTab.test.tsx`

**Interfaces:**
- Consumes: `useModelConfigs` hook, `modelsApi` service, `ModelConfigForm` component
- Produces: Model config management UI embedded in Settings

**Behavior:**
- Lists existing model configs from `useModelConfigs`
- Each row: provider logo, config name, default model, status badge, actions (test, edit, delete, set default)
- "Add Provider" button opens `ModelConfigForm` in edit mode (step='configure')
- Reuses existing `ModelConfigForm` logic but embedded (no full-page layout)
- On save: calls `modelsApi.createConfig`/`updateConfig` → refresh list
- On delete: confirmation dialog → `modelsApi.deleteConfig`
- On test: `modelsApi.testConfig` → show result toast

- [ ] **Step 1: Write the failing test**

```tsx
// frontend/src/components/settings/__tests__/ApiKeysTab.test.tsx
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { ApiKeysTab } from '@/components/settings/ApiKeysTab';
import { useModelConfigs } from '@/hooks/useModelConfigs';
import { modelsApi } from '@/services/models';
import { ModelConfigForm } from '@/components/models/ModelConfigForm';

jest.mock('@/hooks/useModelConfigs');
jest.mock('@/services/models');
jest.mock('@/components/models/ModelConfigForm');

const mockUseModelConfigs = useModelConfigs as jest.MockedFunction<typeof useModelConfigs>;
const mockModelsApi = modelsApi as jest.Mocked<typeof modelsApi>;
const MockModelConfigForm = ModelConfigForm as jest.MockedComponent<typeof ModelConfigForm>;

describe('ApiKeysTab', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('shows loading skeleton while fetching configs', () => {
    mockUseModelConfigs.mockReturnValue({
      configs: [],
      loading: true,
      error: null,
      activeActions: new Map(),
      pendingDeleteId: null,
      activeCount: 0,
      totalTokens: 0,
      totalCost: 0,
      loadConfigs: jest.fn(),
      handleDelete: jest.fn(),
      handleSetDefault: jest.fn(),
      handleTest: jest.fn(),
      handleFetchModels: jest.fn(),
      handleSave: jest.fn(),
      setPendingDeleteId: jest.fn(),
    });

    render(<ApiKeysTab />);

    expect(screen.getByText(/loading configurations/i)).toBeInTheDocument();
  });

  it('renders empty state when no configs', () => {
    mockUseModelConfigs.mockReturnValue({
      configs: [],
      loading: false,
      error: null,
      activeActions: new Map(),
      pendingDeleteId: null,
      activeCount: 0,
      totalTokens: 0,
      totalCost: 0,
      loadConfigs: jest.fn(),
      handleDelete: jest.fn(),
      handleSetDefault: jest.fn(),
      handleTest: jest.fn(),
      handleFetchModels: jest.fn(),
      handleSave: jest.fn(),
      setPendingDeleteId: jest.fn(),
    });

    render(<ApiKeysTab />);

    expect(screen.getByText(/no configurations yet/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /add your first provider/i })).toBeInTheDocument();
  });

  it('renders config list with provider info', () => {
    const mockConfigs = [
      { id: '1', config_name: 'My OpenAI', provider: 'openai', default_model: 'gpt-4', is_default: true, requests_per_minute: 60 },
      { id: '2', config_name: 'My Anthropic', provider: 'anthropic', default_model: 'claude-3', is_default: false, requests_per_minute: 50 },
    ];

    mockUseModelConfigs.mockReturnValue({
      configs: mockConfigs,
      loading: false,
      error: null,
      activeActions: new Map(),
      pendingDeleteId: null,
      activeCount: 2,
      totalTokens: 1000,
      totalCost: 0.5,
      loadConfigs: jest.fn(),
      handleDelete: jest.fn(),
      handleSetDefault: jest.fn(),
      handleTest: jest.fn(),
      handleFetchModels: jest.fn(),
      handleSave: jest.fn(),
      setPendingDeleteId: jest.fn(),
    });

    render(<ApiKeysTab />);

    expect(screen.getByText('My OpenAI')).toBeInTheDocument();
    expect(screen.getByText('My Anthropic')).toBeInTheDocument();
    expect(screen.getByText('gpt-4')).toBeInTheDocument();
    expect(screen.getByText('claude-3')).toBeInTheDocument();
  });

  it('opens ModelConfigForm when Add Provider clicked', () => {
    mockUseModelConfigs.mockReturnValue({
      configs: [],
      loading: false,
      error: null,
      activeActions: new Map(),
      pendingDeleteId: null,
      activeCount: 0,
      totalTokens: 0,
      totalCost: 0,
      loadConfigs: jest.fn(),
      handleDelete: jest.fn(),
      handleSetDefault: jest.fn(),
      handleTest: jest.fn(),
      handleFetchModels: jest.fn(),
      handleSave: jest.fn(),
      setPendingDeleteId: jest.fn(),
    });
    MockModelConfigForm.mockImplementation(({ onCancel }) => (
      <div data-testid="model-config-form">
        <button onClick={onCancel}>Cancel</button>
      </div>
    ));

    render(<ApiKeysTab />);

    fireEvent.click(screen.getByRole('button', { name: /add provider/i }));
    expect(screen.getByTestId('model-config-form')).toBeInTheDocument();
  });

  it('opens ModelConfigForm with initialConfig when Edit clicked', () => {
    const mockConfigs = [
      { id: '1', config_name: 'My OpenAI', provider: 'openai', default_model: 'gpt-4', is_default: true },
    ];

    mockUseModelConfigs.mockReturnValue({
      configs: mockConfigs,
      loading: false,
      error: null,
      activeActions: new Map(),
      pendingDeleteId: null,
      activeCount: 1,
      totalTokens: 0,
      totalCost: 0,
      loadConfigs: jest.fn(),
      handleDelete: jest.fn(),
      handleSetDefault: jest.fn(),
      handleTest: jest.fn(),
      handleFetchModels: jest.fn(),
      handleSave: jest.fn(),
      setPendingDeleteId: jest.fn(),
    });
    MockModelConfigForm.mockImplementation(({ onCancel }) => (
      <div data-testid="model-config-form">
        <button onClick={onCancel}>Cancel</button>
      </div>
    ));

    render(<ApiKeysTab />);

    fireEvent.click(screen.getByRole('button', { name: /edit my openai/i }));
    expect(screen.getByTestId('model-config-form')).toBeInTheDocument();
  });

  it('calls handleDelete when Delete clicked', () => {
    const mockDelete = jest.fn();
    const mockConfigs = [
      { id: '1', config_name: 'My OpenAI', provider: 'openai', default_model: 'gpt-4', is_default: true },
    ];

    mockUseModelConfigs.mockReturnValue({
      configs: mockConfigs,
      loading: false,
      error: null,
      activeActions: new Map(),
      pendingDeleteId: null,
      activeCount: 1,
      totalTokens: 0,
      totalCost: 0,
      loadConfigs: jest.fn(),
      handleDelete: mockDelete,
      handleSetDefault: jest.fn(),
      handleTest: jest.fn(),
      handleFetchModels: jest.fn(),
      handleSave: jest.fn(),
      setPendingDeleteId: jest.fn(),
    });

    render(<ApiKeysTab />);

    fireEvent.click(screen.getByRole('button', { name: /delete my openai/i }));
    expect(mockDelete).toHaveBeenCalledWith('1');
  });

  it('shows error banner when fetch fails', () => {
    mockUseModelConfigs.mockReturnValue({
      configs: [],
      loading: false,
      error: 'Failed to load',
      activeActions: new Map(),
      pendingDeleteId: null,
      activeCount: 0,
      totalTokens: 0,
      totalCost: 0,
      loadConfigs: jest.fn(),
      handleDelete: jest.fn(),
      handleSetDefault: jest.fn(),
      handleTest: jest.fn(),
      handleFetchModels: jest.fn(),
      handleSave: jest.fn(),
      setPendingDeleteId: jest.fn(),
    });

    render(<ApiKeysTab />);

    expect(screen.getByText(/failed to load configurations/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /retry/i })).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm test -- frontend/src/components/settings/__tests__/ApiKeysTab.test.tsx`
Expected: FAIL - module not found

- [ ] **Step 3: Write minimal implementation**

```tsx
// frontend/src/components/settings/ApiKeysTab.tsx
import React, { useState } from 'react';
import { Plus, AlertCircle, CheckCircle2, Server, Settings } from 'lucide-react';
import { useModelConfigs } from '@/hooks/useModelConfigs';
import { ModelConfigForm } from '@/components/models/ModelConfigForm';
import { ModelCardSkeleton } from '@/components/models/ModelCardSkeleton';
import { LoadingSpinner } from '@/components/ui/LoadingSpinner';
import { showToast } from '@/hooks/useToast';

interface ModelConfig {
  id: string;
  config_name: string;
  provider: string;
  default_model: string;
  is_default: boolean;
  requests_per_minute: number;
  api_key_masked?: string;
}

export function ApiKeysTab() {
  const {
    configs,
    loading,
    error,
    activeActions,
    pendingDeleteId,
    activeCount,
    totalTokens,
    totalCost,
    loadConfigs,
    handleDelete,
    handleSetDefault,
    handleTest,
    handleFetchModels,
    handleSave,
    setPendingDeleteId,
  } = useModelConfigs();

  const [showForm, setShowForm] = useState(false);
  const [editingConfig, setEditingConfig] = useState<ModelConfig | null>(null);

  const handleEdit = (config: ModelConfig) => {
    setEditingConfig(config);
    setShowForm(true);
  };

  const handleAddProvider = () => {
    setEditingConfig(null);
    setShowForm(true);
  };

  const handleSaveAndClose = async (config: ModelConfig) => {
    await handleSave(config);
    setShowForm(false);
    setEditingConfig(null);
  };

  const handleCancel = () => {
    setShowForm(false);
    setEditingConfig(null);
  };

  const formatTokenCount = (count: number) => {
    if (count >= 1000000) return `${(count / 1000000).toFixed(1)}M`;
    if (count >= 1000) return `${(count / 1000).toFixed(1)}K`;
    return count.toString();
  };

  // Summary cards
  const summaryCards = [
    { label: 'Total Providers', value: configs.length, icon: <Server className="w-5 h-5" />, color: 'blue' },
    { label: 'Active Providers', value: activeCount, icon: <CheckCircle2 className="w-5 h-5" />, color: 'green' },
    { label: 'Total Tokens', value: formatTokenCount(totalTokens), icon: <Settings className="w-5 h-5" />, color: 'purple' },
    { label: 'Est. Cost', value: `$${totalCost.toFixed(2)}`, icon: <Server className="w-5 h-5" />, color: 'orange' },
  ];

  const colorClasses = {
    blue: { bg: 'bg-blue-100 dark:bg-blue-500/10', text: 'text-blue-600 dark:text-blue-400' },
    green: { bg: 'bg-green-100 dark:bg-green-500/10', text: 'text-green-600 dark:text-green-400' },
    purple: { bg: 'bg-purple-100 dark:bg-purple-500/10', text: 'text-purple-600 dark:text-purple-400' },
    orange: { bg: 'bg-orange-100 dark:bg-orange-500/10', text: 'text-orange-600 dark:text-orange-400' },
  };

  const SummaryCard = ({ label, value, icon, color }: { label: string; value: string | number; icon: React.ReactNode; color: keyof typeof colorClasses }) => {
    const c = colorClasses[color];
    return (
      <div className="bg-white dark:bg-[#161b27] p-5 rounded-xl border border-gray-200 dark:border-[#1e2535]" role="region" aria-label={`${label}: ${value}`}>
        <div className="flex items-center justify-between mb-3">
          <div className={`w-10 h-10 rounded-lg ${c.bg} flex items-center justify-center`}>
            <span className={c.text} aria-hidden="true">{icon}</span>
          </div>
          <span className="text-xl font-bold text-gray-900 dark:text-white">{value}</span>
        </div>
        <p className="text-sm font-medium text-gray-600 dark:text-gray-400">{label}</p>
      </div>
    );
  };

  if (showForm) {
    return (
      <ModelConfigForm
        initialConfig={editingConfig || undefined}
        onSave={handleSaveAndClose}
        onCancel={handleCancel}
      />
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold text-gray-900 dark:text-white">API Keys</h2>
          <p className="text-gray-600 dark:text-gray-400 text-sm mt-1">
            Manage your AI provider API keys and model configurations.
          </p>
        </div>
        <button
          onClick={handleAddProvider}
          className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg font-medium transition-colors flex items-center gap-2"
        >
          <Plus className="w-4 h-4" />
          <span>Add Provider</span>
        </button>
      </div>

      {/* Summary Stats */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {summaryCards.map((card, i) => (
          <SummaryCard key={i} {...card} />
        ))}
      </div>

      {/* Error Banner */}
      {error && (
        <div className="p-4 bg-red-50 dark:bg-red-500/10 border border-red-200 dark:border-red-500/20 rounded-xl flex items-start gap-3" role="alert">
          <AlertCircle className="w-5 h-5 text-red-600 dark:text-red-400 shrink-0 mt-0.5" />
          <div className="flex-1">
            <p className="font-medium text-red-900 dark:text-red-300 text-sm">Failed to load configurations</p>
            <p className="text-sm text-red-700 dark:text-red-400/80 mt-0.5">{String(error)}</p>
          </div>
          <button
            onClick={loadConfigs}
            className="px-3 py-1.5 bg-red-100 dark:bg-red-500/10 hover:bg-red-200 dark:hover:bg-red-500/20 text-red-700 dark:text-red-400 rounded-lg text-sm font-medium transition-colors border border-red-200 dark:border-red-500/20"
          >
            Retry
          </button>
        </div>
      )}

      {/* Configs List */}
      {loading && configs.length > 0 ? (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4" aria-busy="true">
          {configs.map((_, i) => <ModelCardSkeleton key={i} />)}
        </div>
      ) : configs.length === 0 ? (
        <div className="text-center py-12 bg-white dark:bg-[#161b27] rounded-xl border border-gray-200 dark:border-[#1e2535]">
          <div className="inline-flex items-center justify-center w-16 h-16 bg-gray-100 dark:bg-[#0f1117] rounded-2xl mb-4">
            <Settings className="w-8 h-8 text-gray-500 dark:text-gray-400" />
          </div>
          <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-2">No Configurations Yet</h3>
          <p className="text-gray-600 dark:text-gray-400 text-sm mb-4 max-w-md mx-auto">
            Get started by adding your first AI provider. Connect OpenAI, Anthropic, Google, Groq, or run models locally.
          </p>
          <button
            onClick={handleAddProvider}
            className="px-5 py-2.5 bg-blue-600 hover:bg-blue-700 text-white rounded-lg font-medium transition-colors inline-flex items-center gap-2"
          >
            <Plus className="w-4 h-4" />
            Add Your First Provider
          </button>
        </div>
      ) : (
        <div className="space-y-3">
          {configs.map((config) => (
            <div key={config.id} className="bg-white dark:bg-[#161b27] rounded-xl border border-gray-200 dark:border-[#1e2535] p-4 transition-colors hover:border-gray-300 dark:hover:border-[#2a3347]">
              <div className="flex items-start justify-between gap-4">
                <div className="flex items-center gap-4 flex-1 min-w-0">
                  <div className="w-10 h-10 rounded-lg bg-blue-100 dark:bg-blue-500/10 flex items-center justify-center flex-shrink-0">
                    <Server className="w-5 h-5 text-blue-600 dark:text-blue-400" />
                  </div>
                  <div className="min-w-0">
                    <div className="flex items-center gap-2">
                      <h4 className="font-semibold text-gray-900 dark:text-white truncate">{config.config_name}</h4>
                      {config.is_default && (
                        <span className="px-2 py-0.5 text-xs font-medium bg-blue-100 dark:bg-blue-500/10 text-blue-700 dark:text-blue-400 rounded-full">
                          Default
                        </span>
                      )}
                    </div>
                    <p className="text-sm text-gray-500 dark:text-gray-400 truncate">
                      {config.provider.toUpperCase()} • {config.default_model}
                    </p>
                  </div>
                </div>

                <div className="flex items-center gap-2 flex-shrink-0">
                  {!config.is_default && (
                    <button
                      onClick={() => handleSetDefault(config.id)}
                      disabled={activeActions.get(config.id) === 'set_default'}
                      className="px-3 py-1.5 text-sm text-gray-600 dark:text-gray-400 hover:text-blue-600 dark:hover:text-blue-400 transition-colors"
                      title="Set as default"
                    >
                      <CheckCircle2 className="w-4 h-4" />
                    </button>
                  )}
                  <button
                    onClick={() => handleTest(config.id)}
                    disabled={activeActions.get(config.id) === 'test'}
                    className="px-3 py-1.5 text-sm text-gray-600 dark:text-gray-400 hover:text-green-600 dark:hover:text-green-400 transition-colors"
                    title="Test connection"
                  >
                    <Server className="w-4 h-4" />
                  </button>
                  <button
                    onClick={() => handleEdit(config)}
                    className="px-3 py-1.5 text-sm text-gray-600 dark:text-gray-400 hover:text-blue-600 dark:hover:text-blue-400 transition-colors"
                    title="Edit"
                  >
                    <Settings className="w-4 h-4" />
                  </button>
                  {pendingDeleteId === config.id ? (
                    <div className="flex items-center gap-1">
                      <button
                        onClick={() => handleDelete(config.id)}
                        className="px-3 py-1.5 text-sm text-red-600 hover:text-red-700 transition-colors"
                      >
                        Confirm
                      </button>
                      <button
                        onClick={() => setPendingDeleteId(null)}
                        className="px-3 py-1.5 text-sm text-gray-500 hover:text-gray-700 transition-colors"
                      >
                        Cancel
                      </button>
                    </div>
                  ) : (
                    <button
                      onClick={() => setPendingDeleteId(config.id)}
                      className="px-3 py-1.5 text-sm text-gray-500 hover:text-red-600 transition-colors"
                      title="Delete"
                    >
                      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                      </svg>
                    </button>
                  )}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npm test -- frontend/src/components/settings/__tests__/ApiKeysTab.test.tsx`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/settings/ApiKeysTab.tsx frontend/src/components/settings/__tests__/ApiKeysTab.test.tsx
git commit -m "feat: add ApiKeysTab embedded model config management with tests"
```

### Task 8: NotificationsTab Component (`NotificationsTab.tsx`)

**Files:**
- Create: `frontend/src/components/settings/NotificationsTab.tsx`
- Test: `frontend/src/components/settings/__tests__/NotificationsTab.test.tsx`

**Interfaces:**
- Consumes: `useUserPreferences` hook
- Produces: Notification preferences UI

**Behavior:**
- Master toggle: `notifications.enabled` (disables all others when off)
- Sound toggle: `notifications.sound`
- Channel multi-select: `notifications.channels` (websocket, email)
- Future-ready: per-event toggles section (placeholder)
- Uses PreferenceInput for each setting
- Shows/hides child options based on master toggle

- [ ] **Step 1: Write the failing test**

```tsx
// frontend/src/components/settings/__tests__/NotificationsTab.test.tsx
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { NotificationsTab } from '@/components/settings/NotificationsTab';
import { useUserPreferences } from '@/hooks/useUserPreferences';

jest.mock('@/hooks/useUserPreferences');

const mockUseUserPreferences = useUserPreferences as jest.MockedFunction<typeof useUserPreferences>;

describe('NotificationsTab', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('renders master toggle for notifications.enabled', () => {
    mockUseUserPreferences.mockReturnValue({
      preferences: { 'notifications.enabled': true, 'notifications.sound': true, 'notifications.channels': ['websocket'] },
      loading: false,
      error: null,
      initialized: true,
      updatePreference: jest.fn(),
      bulkUpdate: jest.fn(),
      refresh: jest.fn(),
      getPreference: (key: string, def?: any) => ({ 'notifications.enabled': true, 'notifications.sound': true, 'notifications.channels': ['websocket'] } as any)[key] ?? def,
    });

    render(<NotificationsTab />);

    expect(screen.getByRole('checkbox', { name: /notifications.enabled/i })).toBeChecked();
  });

  it('shows sound and channels when enabled', () => {
    mockUseUserPreferences.mockReturnValue({
      preferences: { 'notifications.enabled': true, 'notifications.sound': true, 'notifications.channels': ['websocket'] },
      loading: false,
      error: null,
      initialized: true,
      updatePreference: jest.fn(),
      bulkUpdate: jest.fn(),
      refresh: jest.fn(),
      getPreference: (key: string, def?: any) => ({ 'notifications.enabled': true, 'notifications.sound': true, 'notifications.channels': ['websocket'] } as any)[key] ?? def,
    });

    render(<NotificationsTab />);

    expect(screen.getByRole('checkbox', { name: /notifications.sound/i })).toBeInTheDocument();
    expect(screen.getByRole('listbox', { name: /notifications.channels/i })).toBeInTheDocument();
  });

  it('hides sound and channels when disabled', () => {
    mockUseUserPreferences.mockReturnValue({
      preferences: { 'notifications.enabled': false, 'notifications.sound': true, 'notifications.channels': ['websocket'] },
      loading: false,
      error: null,
      initialized: true,
      updatePreference: jest.fn(),
      bulkUpdate: jest.fn(),
      refresh: jest.fn(),
      getPreference: (key: string, def?: any) => ({ 'notifications.enabled': false, 'notifications.sound': true, 'notifications.channels': ['websocket'] } as any)[key] ?? def,
    });

    render(<NotificationsTab />);

    expect(screen.queryByRole('checkbox', { name: /notifications.sound/i })).not.toBeInTheDocument();
    expect(screen.queryByRole('listbox', { name: /notifications.channels/i })).not.toBeInTheDocument();
  });

  it('calls updatePreference when master toggle changes', async () => {
    const mockUpdate = jest.fn();
    mockUseUserPreferences.mockReturnValue({
      preferences: { 'notifications.enabled': true },
      loading: false,
      error: null,
      initialized: true,
      updatePreference: mockUpdate,
      bulkUpdate: jest.fn(),
      refresh: jest.fn(),
      getPreference: (key: string) => key === 'notifications.enabled' ? true : undefined,
    });

    render(<NotificationsTab />);

    fireEvent.click(screen.getByRole('checkbox', { name: /notifications.enabled/i }));

    await waitFor(() => expect(mockUpdate).toHaveBeenCalledWith('notifications.enabled', false));
  });

  it('shows loading state', () => {
    mockUseUserPreferences.mockReturnValue({
      preferences: {},
      loading: true,
      error: null,
      initialized: false,
      updatePreference: jest.fn(),
      bulkUpdate: jest.fn(),
      refresh: jest.fn(),
      getPreference: jest.fn(),
    });

    render(<NotificationsTab />);

    expect(screen.getByText(/loading notifications/i)).toBeInTheDocument();
  });

  it('disables inputs when loading', () => {
    mockUseUserPreferences.mockReturnValue({
      preferences: { 'notifications.enabled': true },
      loading: true,
      error: null,
      initialized: false,
      updatePreference: jest.fn(),
      bulkUpdate: jest.fn(),
      refresh: jest.fn(),
      getPreference: jest.fn(),
    });

    render(<NotificationsTab />);

    expect(screen.getByRole('checkbox', { name: /notifications.enabled/i })).toBeDisabled();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm test -- frontend/src/components/settings/__tests__/NotificationsTab.test.tsx`
Expected: FAIL - module not found

- [ ] **Step 3: Write minimal implementation**

```tsx
// frontend/src/components/settings/NotificationsTab.tsx
import React from 'react';
import { Bell, Volume2, MessageSquare, Mail, Loader2 } from 'lucide-react';
import { useUserPreferences } from '@/hooks/useUserPreferences';
import { PreferenceInput } from './PreferenceInput';

const channelOptions = [
  { value: 'websocket', label: 'In-App (WebSocket)', icon: <MessageSquare className="w-4 h-4" /> },
  { value: 'email', label: 'Email', icon: <Mail className="w-4 h-4" /> },
];

export function NotificationsTab() {
  const { preferences, loading, initialized, updatePreference, getPreference } = useUserPreferences();

  const enabled = getPreference('notifications.enabled', true);
  const sound = getPreference('notifications.sound', true);
  const channels = getPreference('notifications.channels', ['websocket', 'email']);

  if (loading && !initialized) {
    return (
      <div className="flex items-center gap-3 text-sm text-gray-600 dark:text-gray-400">
        <Loader2 className="w-4 h-4 animate-spin" />
        <span>Loading notifications...</span>
      </div>
    );
  }

  const handleEnabledChange = (value: boolean) => {
    updatePreference('notifications.enabled', value);
  };

  const handleSoundChange = (value: boolean) => {
    updatePreference('notifications.sound', value);
  };

  const handleChannelsChange = (value: string[]) => {
    updatePreference('notifications.channels', value);
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h2 className="text-2xl font-bold text-gray-900 dark:text-white">Notifications</h2>
        <p className="text-gray-600 dark:text-gray-400 text-sm mt-1">
          Configure how and when you receive notifications.
        </p>
      </div>

      {/* Master Toggle */}
      <div className="bg-white dark:bg-[#161b27] rounded-xl border border-gray-200 dark:border-[#1e2535] p-5">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-4">
            <div className="w-12 h-12 rounded-lg bg-blue-100 dark:bg-blue-500/10 flex items-center justify-center">
              <Bell className="w-6 h-6 text-blue-600 dark:text-blue-400" />
            </div>
            <div>
              <h3 className="text-lg font-semibold text-gray-900 dark:text-white">Enable Notifications</h3>
              <p className="text-sm text-gray-500 dark:text-gray-400">
                Master switch for all notifications. When disabled, no notifications will be sent.
              </p>
            </div>
          </div>
          <PreferenceInput
            preference={{
              key: 'notifications.enabled',
              value: enabled,
              data_type: 'boolean',
              category: 'notifications',
            }}
            onChange={handleEnabledChange}
            disabled={loading}
          />
        </div>
      </div>

      {/* Notification Options (only when enabled) */}
      {enabled && (
        <div className="space-y-4">
          {/* Sound Toggle */}
          <div className="bg-white dark:bg-[#161b27] rounded-xl border border-gray-200 dark:border-[#1e2535] p-5">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-4">
                <div className="w-12 h-12 rounded-lg bg-green-100 dark:bg-green-500/10 flex items-center justify-center">
                  <Volume2 className="w-6 h-6 text-green-600 dark:text-green-400" />
                </div>
                <div>
                  <h3 className="text-lg font-semibold text-gray-900 dark:text-white">Notification Sound</h3>
                  <p className="text-sm text-gray-500 dark:text-gray-400">
                    Play a sound when a notification arrives.
                  </p>
                </div>
              </div>
              <PreferenceInput
                preference={{
                  key: 'notifications.sound',
                  value: sound,
                  data_type: 'boolean',
                  category: 'notnotations',
                }}
                onChange={handleSoundChange}
                disabled={loading}
              />
            </div>
          </div>

          {/* Channels */}
          <div className="bg-white dark:bg-[#161b27] rounded-xl border border-gray-200 dark:border-[#1e2535] p-5">
            <div className="flex flex-col gap-4">
              <div className="flex items-center gap-4">
                <div className="w-12 h-12 rounded-lg bg-purple-100 dark:bg-purple-500/10 flex items-center justify-center">
                  <MessageSquare className="w-6 h-6 text-purple-600 dark:text-purple-400" />
                </div>
                <div>
                  <h3 className="text-lg font-semibold text-gray-900 dark:text-white">Notification Channels</h3>
                  <p className="text-sm text-gray-500 dark:text-gray-400">
                    Choose where you want to receive notifications.
                  </p>
                </div>
              </div>
              <PreferenceInput
                preference={{
                  key: 'notifications.channels',
                  value: channels,
                  data_type: 'array',
                  category: 'notifications',
                  description: 'Hold Ctrl/Cmd to select multiple channels',
                }}
                onChange={handleChannelsChange}
                disabled={loading}
              />
            </div>
          </div>

          {/* Per-event toggles placeholder */}
          <div className="bg-white dark:bg-[#161b27] rounded-xl border border-gray-200 dark:border-[#1e2535] p-5">
            <div className="flex items-center gap-4">
              <div className="w-12 h-12 rounded-lg bg-gray-100 dark:bg-[#1e2535] flex items-center justify-center">
                <Loader2 className="w-6 h-6 text-gray-500 dark:text-gray-400" />
              </div>
              <div>
                <h3 className="text-lg font-semibold text-gray-900 dark:text-white">Event-Specific Settings</h3>
                <p className="text-sm text-gray-500 dark:text-gray-400">
                  Granular control over which events trigger notifications (coming soon).
                </p>
              </div>
            </div>
            <div className="mt-4 p-3 bg-gray-50 dark:bg-[#0f1117] rounded-lg text-sm text-gray-500 dark:text-gray-400">
              Per-event notification toggles will be available in a future update.
            </div>
          </div>
        </div>
      )}

      {/* Disabled State Message */}
      {!enabled && (
        <div className="bg-yellow-50 dark:bg-yellow-500/10 border border-yellow-200 dark:border-yellow-500/20 rounded-xl p-5">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-lg bg-yellow-100 dark:bg-yellow-500/10 flex items-center justify-center">
              <Bell className="w-5 h-5 text-yellow-600 dark:text-yellow-400" />
            </div>
            <div>
              <p className="font-medium text-yellow-900 dark:text-yellow-300">Notifications Disabled</p>
              <p className="text-sm text-yellow-800 dark:text-yellow-400/80 mt-1">
                Enable notifications above to configure sound and channels.
              </p>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npm test -- frontend/src/components/settings/__tests__/NotificationsTab.test.tsx`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/settings/NotificationsTab.tsx frontend/src/components/settings/__tests__/NotificationsTab.test.tsx
git commit -m "feat: add NotificationsTab with master toggle and channel selection"
```

### Task 9: Update SettingsPage.tsx - Integrate All Tabs

**Files:**
- Modify: `frontend/src/pages/SettingsPage.tsx`
- Test: `frontend/src/pages/__tests__/SettingsPage.test.tsx`

**Interfaces:**
- Consumes: All new components (PreferencesTab, ThemeSelector, ApiKeysTab, NotificationsTab), existing hooks/components
- Produces: Complete 6-tab SettingsPage

**Changes:**
1. Add new tab state: `'appearance' | 'preferences' | 'api-keys' | 'notifications'`
2. Import new components
3. Add tab buttons in header (with proper icons)
4. Add tab panels with `hidden` class for mounted-but-hidden behavior
5. Wire up PreferencesTab in preferences panel
6. Wire up ThemeSelector in appearance panel
7. Wire up ApiKeysTab in api-keys panel
8. Wire up NotificationsTab in notifications panel
9. Keep existing Account and User Management tabs working
10. Add proper icons for each tab (User, Monitor, Sliders, Key, Bell, Users)

- [ ] **Step 1: Write the failing test**

```tsx
// frontend/src/pages/__tests__/SettingsPage.test.tsx
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { SettingsPage } from '@/pages/SettingsPage';
import { useAuthStore } from '@/store/authStore';
import { useUserPreferences } from '@/hooks/useUserPreferences';
import { useModelConfigs } from '@/hooks/useModelConfigs';

jest.mock('@/store/authStore');
jest.mock('@/hooks/useUserPreferences');
jest.mock('@/hooks/useModelConfigs');

const mockUseAuthStore = useAuthStore as jest.MockedFunction<typeof useAuthStore>;
const mockUseUserPreferences = useUserPreferences as jest.MockedFunction<typeof useUserPreferences>;
const mockUseModelConfigs = useModelConfigs as jest.MockedFunction<typeof useModelConfigs>;

describe('SettingsPage', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockUseAuthStore.mockReturnValue({
      user: { id: 'user-1', username: 'testuser', is_admin: false, isAuthenticated: true, role: 'user' },
      changePassword: jest.fn().mockResolvedValue(true),
      updateAvatar: jest.fn(),
    } as any);
    mockUseUserPreferences.mockReturnValue({
      preferences: { 'ui.theme': 'dark' },
      loading: false,
      error: null,
      initialized: true,
      updatePreference: jest.fn(),
      bulkUpdate: jest.fn(),
      refresh: jest.fn(),
      getPreference: (key: string) => key === 'ui.theme' ? 'dark' : undefined,
    });
    mockUseModelConfigs.mockReturnValue({
      configs: [],
      loading: false,
      error: null,
      activeActions: new Map(),
      pendingDeleteId: null,
      activeCount: 0,
      totalTokens: 0,
      totalCost: 0,
      loadConfigs: jest.fn(),
      handleDelete: jest.fn(),
      handleSetDefault: jest.fn(),
      handleTest: jest.fn(),
      handleFetchModels: jest.fn(),
      handleSave: jest.fn(),
      setPendingDeleteId: jest.fn(),
    });
  });

  it('renders all 6 tabs for regular user', () => {
    render(<SettingsPage />);

    expect(screen.getByRole('tab', { name: /account settings/i })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: /appearance/i })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: /preferences/i })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: /api keys/i })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: /notifications/i })).toBeInTheDocument();
    expect(screen.queryByRole('tab', { name: /user management/i })).not.toBeInTheDocument();
  });

  it('renders User Management tab for admin user', () => {
    mockUseAuthStore.mockReturnValue({
      user: { id: 'admin-1', username: 'admin', is_admin: true, isAuthenticated: true, role: 'admin' },
      changePassword: jest.fn().mockResolvedValue(true),
      updateAvatar: jest.fn(),
    } as any);

    render(<SettingsPage />);

    expect(screen.getByRole('tab', { name: /user management/i })).toBeInTheDocument();
  });

  it('shows Account tab by default', () => {
    render(<SettingsPage />);

    expect(screen.getByText(/change password/i)).toBeInTheDocument();
    expect(screen.queryByText(/theme selection/i)).not.toBeInTheDocument();
  });

  it('switches to Appearance tab when clicked', () => {
    render(<SettingsPage />);

    fireEvent.click(screen.getByRole('tab', { name: /appearance/i }));

    expect(screen.getByText(/theme selection/i)).toBeInTheDocument();
    expect(screen.queryByText(/change password/i)).not.toBeInTheDocument();
  });

  it('switches to Preferences tab when clicked', () => {
    render(<SettingsPage />);

    fireEvent.click(screen.getByRole('tab', { name: /preferences/i }));

    expect(screen.getByText(/interface/i)).toBeInTheDocument(); // UI category label
  });

  it('switches to API Keys tab when clicked', () => {
    render(<SettingsPage />);

    fireEvent.click(screen.getByRole('tab', { name: /api keys/i }));

    expect(screen.getByText(/manage your ai provider/i)).toBeInTheDocument();
  });

  it('switches to Notifications tab when clicked', () => {
    render(<SettingsPage />);

    fireEvent.click(screen.getByRole('tab', { name: /notifications/i }));

    expect(screen.getByText(/enable notifications/i)).toBeInTheDocument();
  });

  it('preserves tab state when switching (Account form not reset)', () => {
    render(<SettingsPage />);

    // Type in password field
    const currentPasswordInput = screen.getByLabelText(/current password/i);
    fireEvent.change(currentPasswordInput, { target: { value: 'test123' } });

    // Switch to Appearance and back
    fireEvent.click(screen.getByRole('tab', { name: /appearance/i }));
    fireEvent.click(screen.getByRole('tab', { name: /account settings/i }));

    // Value should still be there (panels kept mounted with hidden class)
    expect(screen.getByLabelText(/current password/i)).toHaveValue('test123');
  });

  it('shows pending count badge on User Management tab for admin', () => {
    mockUseAuthStore.mockReturnValue({
      user: { id: 'admin-1', username: 'admin', is_admin: true, isAuthenticated: true, role: 'admin' },
      changePassword: jest.fn().mockResolvedValue(true),
      updateAvatar: jest.fn(),
    } as any);

    // Mock the UserManagement callback to set pending count
    // This tests the integration point
    render(<SettingsPage />);

    const userMgmtTab = screen.getByRole('tab', { name: /user management/i });
    expect(userMgmtTab).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm test -- frontend/src/pages/__tests__/SettingsPage.test.tsx`
Expected: FAIL - new tabs not implemented yet

- [ ] **Step 3: Write minimal implementation**

```tsx
// frontend/src/pages/SettingsPage.tsx
import { useState, useRef, type ChangeEvent } from 'react';
import { useAuthStore } from '@/store/authStore';
import { useForm } from 'react-hook-form';
import {
    Lock,
    Shield,
    Save,
    Eye,
    EyeOff,
    User,
    Key,
    CheckCircle2,
    AlertTriangle,
    Info,
    Users,
    Monitor,
    Sliders,
    Bell,
} from 'lucide-react';
import { showToast } from '@/hooks/useToast';
import { api } from '@/services/api';
import UserManagement from './Usermanagement';
import { usePasswordStrength } from '@/hooks/usePasswordStrength';
import { LoadingSpinner } from '@/components/ui/LoadingSpinner';
import { PreferencesTab } from '@/components/settings/PreferencesTab';
import { ThemeSelector } from '@/components/settings/ThemeSelector';
import { ApiKeysTab } from '@/components/settings/ApiKeysTab';
import { NotificationsTab } from '@/components/settings/NotificationsTab';

interface PasswordFormData {
    currentPassword: string;
    newPassword: string;
    confirmPassword: string;
}

const ROLE_PERMISSION_LABELS: Record<string, string> = {
    primary_sovereign: 'Full Access',
    deputy_sovereign:  'Elevated Access',
    observer:          'Read Only',
    admin:             'Full Access',
    user:              'Standard',
};

type TabId = 'account' | 'appearance' | 'preferences' | 'api-keys' | 'notifications' | 'users';

const TABS: { id: TabId; label: string; icon: React.ReactNode; adminOnly?: boolean }[] = [
    { id: 'account', label: 'Account Settings', icon: <User className="w-4 h-4" /> },
    { id: 'appearance', label: 'Appearance', icon: <Monitor className="w-4 h-4" /> },
    { id: 'preferences', label: 'Preferences', icon: <Sliders className="w-4 h-4" /> },
    { id: 'api-keys', label: 'API Keys', icon: <Key className="w-4 h-4" /> },
    { id: 'notifications', label: 'Notifications', icon: <Bell className="w-4 h-4" /> },
    { id: 'users', label: 'User Management', icon: <Users className="w-4 h-4" />, adminOnly: true },
];

export function SettingsPage() {
    const { user, changePassword, updateAvatar } = useAuthStore();
    const [activeTab, setActiveTab] = useState<TabId>('account');

    const [showCurrentPassword, setShowCurrentPassword] = useState(false);
    const [showNewPassword, setShowNewPassword] = useState(false);
    const [showConfirmPassword, setShowConfirmPassword] = useState(false);
    const [isSubmitting, setIsSubmitting] = useState(false);
    const [pendingCount, setPendingCount] = useState(0);
    const fileInputRef = useRef<HTMLInputElement>(null);
    const [uploading, setUploading] = useState(false);

    const {
        register,
        handleSubmit,
        watch,
        reset,
        formState: { errors },
    } = useForm<PasswordFormData>();

    const newPassword = watch('newPassword');

    const {
        strength: passwordStrength,
        color: strengthColor,
        label: strengthLabel,
        textColor: strengthTextColor,
    } = usePasswordStrength(newPassword ?? '');

    const permissionLabel =
        ROLE_PERMISSION_LABELS[user?.role ?? ''] ?? 'Standard';

    const lastLoginDisplay = (() => {
        const raw = user?.last_login_at;
        if (!raw) return 'N/A';
        return new Date(raw).toLocaleDateString('en-US', {
            month: 'short',
            day:   'numeric',
            year:  'numeric',
        });
    })();

    const onSubmit = async (data: PasswordFormData) => {
        setIsSubmitting(true);
        try {
            const success = await changePassword(data.currentPassword, data.newPassword);
            if (success) {
                showToast.success('Password changed successfully');
                reset();
            } else {
                const currentError = useAuthStore.getState().error;
                showToast.error(currentError || 'Failed to change password');
            }
        } catch (error: any) {
            let message = 'Failed to change password';
            if (error?.response?.data?.detail) {
                message = Array.isArray(error.response.data.detail)
                    ? error.response.data.detail.map((e: any) => e.msg).join(', ')
                    : String(error.response.data.detail);
            }
            showToast.error(message);
        } finally {
            setIsSubmitting(false);
        }
    };

    const handleAvatarChange = async (e: ChangeEvent<HTMLInputElement>) => {
        const file = e.target.files?.[0];
        if (!file) return;
        if (!['image/jpeg', 'image/png', 'image/webp', 'image/gif'].includes(file.type)) {
            showToast.error('Unsupported image type. Use jpg, png, webp or gif.');
            return;
        }
        if (file.size > 5 * 1024 * 1024) {
            showToast.error('Image must be 5 MB or smaller.');
            return;
        }
        setUploading(true);
        try {
            const form = new FormData();
            form.append('file', file);
            const res = await api.post('/api/v1/users/me/avatar', form, {
                headers: { 'Content-Type': 'multipart/form-data' },
            });
            updateAvatar(res.data.avatar_url);
            showToast.success('Profile picture updated.');
        } catch {
            showToast.error('Upload failed. Please try again.');
        } finally {
            setUploading(false);
            if (fileInputRef.current) fileInputRef.current.value = '';
        }
    };

    const handleAvatarRemove = async () => {
        try {
            await api.delete('/api/v1/users/me/avatar');
            updateAvatar(null);
            showToast.success('Profile picture removed.');
        } catch {
            showToast.error('Remove failed. Please try again.');
        }
    };

    const inputClass = (hasError: boolean) =>
        `w-full px-4 py-3 border rounded-lg bg-white dark:bg-[#0f1117] text-gray-900 dark:text-white placeholder-gray-400 dark:placeholder-gray-500 outline-none transition-all duration-150 ${
            hasError
                ? 'border-red-300 dark:border-red-500/50 focus:ring-2 focus:ring-red-500/30 focus:border-red-500'
                : 'border-gray-300 dark:border-[#1e2535] focus:ring-2 focus:ring-blue-500/30 focus:border-blue-500 dark:focus:border-blue-500/70'
        }`;

    const renderTabButton = (tab: typeof TABS[0], index: number) => {
        if (tab.adminOnly && !user?.is_admin) return null;

        const isActive = activeTab === tab.id;
        const showBadge = tab.id === 'users' && pendingCount > 0;

        return (
            <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                role="tab"
                aria-selected={isActive}
                className={`flex items-center gap-2 px-5 py-2.5 rounded-lg text-sm font-semibold transition-all duration-150 ${
                    isActive
                        ? 'bg-blue-600 hover:bg-blue-700 text-white shadow-sm'
                        : 'bg-white dark:bg-[#161b27] text-gray-600 dark:text-gray-400 border border-gray-200 dark:border-[#1e2535] hover:border-gray-300 dark:hover:border-[#2a3347] hover:text-gray-900 dark:hover:text-gray-200'
                }`}
            >
                <span className="flex items-center">{tab.icon}</span>
                {tab.label}
                {showBadge && (
                    <span className={`px-1.5 py-0.5 rounded-full text-xs font-bold leading-none ${
                        isActive
                            ? 'bg-white/20 text-white'
                            : 'bg-yellow-100 text-yellow-700 dark:bg-yellow-500/15 dark:text-yellow-400'
                    }`}>
                        {pendingCount}
                    </span>
                )}
            </button>
        );
    };

    const renderTabPanel = (tabId: TabId) => {
        const isActive = activeTab === tabId;

        switch (tabId) {
            case 'account':
                return (
                    <div className={isActive ? 'block' : 'hidden'} role="tabpanel">
                        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                            {/* Sidebar - Account Card & Info */}
                            <div className="lg:col-span-1 space-y-5">
                                <div className="bg-white dark:bg-[#161b27] rounded-xl border border-gray-200 dark:border-[#1e2535] p-6 shadow-sm dark:shadow-[0_2px_16px_rgba(0,0,0,0.25)] transition-colors duration-200">
                                    <div className="flex flex-col items-center text-center">
                                        <div className="w-20 h-20 rounded-full overflow-hidden bg-gradient-to-br from-blue-500 via-purple-500 to-pink-500 flex items-center justify-center mb-4 shadow-lg">
                                            {user?.avatar_url ? (
                                                <img src={user.avatar_url} alt="Profile" className="w-full h-full object-cover" />
                                            ) : (
                                                <User className="w-10 h-10 text-white" />
                                            )}
                                        </div>
                                        <input
                                            ref={fileInputRef}
                                            type="file"
                                            accept="image/*"
                                            className="hidden"
                                            onChange={handleAvatarChange}
                                        />
                                        <div className="flex flex-col gap-2 w-full max-w-[12rem]">
                                            <button
                                                type="button"
                                                onClick={() => fileInputRef.current?.click()}
                                                disabled={isSubmitting || uploading}
                                                className="px-3 py-1.5 text-sm rounded-lg bg-blue-600 hover:bg-blue-700 text-white font-medium transition-colors disabled:opacity-50"
                                            >
                                                {uploading ? 'Uploading…' : 'Upload picture'}
                                            </button>
                                            {user?.avatar_url && (
                                                <button
                                                    type="button"
                                                    onClick={handleAvatarRemove}
                                                    disabled={isSubmitting || uploading}
                                                    className="px-3 py-1.5 text-sm rounded-lg border border-gray-300 dark:border-[#1e2535] text-gray-600 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-[#1e2535] transition-colors disabled:opacity-50"
                                                >
                                                    Remove
                                                </button>
                                            )}
                                        </div>
                                        <h2 className="text-xl font-bold text-gray-900 dark:text-white mb-2">{user?.username}</h2>
                                        <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold bg-blue-100 text-blue-700 dark:bg-blue-500/10 dark:text-blue-400 border border-blue-200 dark:border-blue-500/20">
                                            <Shield className="w-3 h-3" />
                                            {user?.role}
                                        </span>
                                        <div className="w-full mt-6 pt-5 border-t border-gray-100 dark:border-[#1e2535] space-y-3">
                                            <div className="flex items-center justify-between text-sm">
                                                <span className="text-gray-600 dark:text-gray-400">Account Status</span>
                                                <span className="flex items-center gap-1.5 text-green-700 dark:text-green-300 font-medium text-xs">
                                                    <CheckCircle2 className="w-3.5 h-3.5" />
                                                    Active
                                                </span>
                                            </div>
                                            <div className="flex items-center justify-between text-sm">
                                                <span className="text-gray-600 dark:text-gray-400">Last Login</span>
                                                <span className="text-gray-900 dark:text-gray-100 font-medium text-xs">{lastLoginDisplay}</span>
                                            </div>
                                        </div>
                                    </div>
                                </div>
                                <div className="bg-white dark:bg-[#161b27] rounded-xl border border-gray-200 dark:border-[#1e2535] p-6 shadow-sm dark:shadow-[0_2px_16px_rgba(0,0,0,0.25)] transition-colors duration-200">
                                    <h3 className="text-sm font-semibold text-gray-900 dark:text-white mb-4 flex items-center gap-2">
                                        <Info className="w-4 h-4 text-gray-600 dark:text-gray-500" />
                                        Account Info
                                    </h3>
                                    <div className="divide-y divide-gray-100 dark:divide-[#1e2535]">
                                        <div className="flex items-center justify-between py-2.5">
                                            <span className="text-xs text-gray-600 dark:text-gray-400">User ID</span>
                                            <span className="text-xs font-mono text-gray-900 dark:text-gray-100">#{user?.id || '—'}</span>
                                        </div>
                                        <div className="flex items-center justify-between py-2.5">
                                            <span className="text-xs text-gray-600 dark:text-gray-400">Permissions</span>
                                            <span className="text-xs text-gray-900 dark:text-gray-100">{permissionLabel}</span>
                                        </div>
                                        <div className="flex items-center justify-between py-2.5">
                                            <span className="text-xs text-gray-600 dark:text-gray-400">2FA Status</span>
                                            <span className="text-xs text-gray-600 dark:text-gray-300">Not Enabled</span>
                                        </div>
                                    </div>
                                </div>
                            </div>

                            {/* Main content - Password change */}
                            <div className="lg:col-span-2">
                                <div className="bg-white dark:bg-[#161b27] rounded-xl border border-gray-200 dark:border-[#1e2535] shadow-sm dark:shadow-[0_2px_16px_rgba(0,0,0,0.25)] overflow-hidden transition-colors duration-200">
                                    <div className="bg-gray-50 dark:bg-[#0f1117] border-b border-gray-200 dark:border-[#1e2535] px-6 py-5">
                                        <div className="flex items-center gap-3">
                                            <div className="w-10 h-10 rounded-lg bg-purple-100 dark:bg-purple-500/10 border border-purple-200 dark:border-purple-500/20 flex items-center justify-center">
                                                <Key className="w-5 h-5 text-purple-600 dark:text-purple-400" />
                                            </div>
                                            <div>
                                                <h2 className="text-base font-semibold text-gray-900 dark:text-white">Change Password</h2>
                                                <p className="text-sm text-gray-600 dark:text-gray-400">Update your security credentials</p>
                                            </div>
                                        </div>
                                    </div>
                                    <form onSubmit={handleSubmit(onSubmit)} className="p-6">
                                        <div className="space-y-5">
                                            <div>
                                                <label htmlFor="currentPassword" className="block text-sm font-semibold text-gray-700 dark:text-gray-300 mb-2">Current Password</label>
                                                <div className="relative">
                                                    <input
                                                        id="currentPassword"
                                                        type={showCurrentPassword ? 'text' : 'password'}
                                                        {...register('currentPassword', { required: 'Current password is required' })}
                                                        className={`${inputClass(!!errors.currentPassword)} pr-11`}
                                                        placeholder="Enter current password"
                                                    />
                                                    <button type="button" onClick={() => setShowCurrentPassword(!showCurrentPassword)} className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-600 hover:text-gray-600 dark:hover:text-gray-300 transition-colors duration-150" aria-label={showCurrentPassword ? 'Hide password' : 'Show password'}>
                                                        {showCurrentPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                                                    </button>
                                                </div>
                                                {errors.currentPassword && <p className="mt-1.5 text-xs text-red-600 dark:text-red-400 flex items-center gap-1.5"><AlertTriangle className="w-3.5 h-3.5 flex-shrink-0" />{errors.currentPassword.message}</p>}
                                            </div>
                                            <div className="relative py-1">
                                                <div className="absolute inset-0 flex items-center"><div className="w-full border-t border-gray-200 dark:border-[#1e2535]" /></div>
                                                <div className="relative flex justify-center"><span className="px-3 bg-white dark:bg-[#161b27] text-xs text-gray-700 dark:text-gray-300">New Password</span></div>
                                            </div>
                                            <div>
                                                <label htmlFor="newPassword" className="block text-sm font-semibold text-gray-700 dark:text-gray-300 mb-2">New Password</label>
                                                <div className="relative">
                                                    <input id="newPassword" type={showNewPassword ? 'text' : 'password'} {...register('newPassword', { required: 'New password is required', minLength: { value: 8, message: 'Password must be at least 8 characters' } })} className={`${inputClass(!!errors.newPassword)} pr-11`} placeholder="Enter new password" />
                                                    <button type="button" onClick={() => setShowNewPassword(!showNewPassword)} className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-600 hover:text-gray-600 dark:hover:text-gray-300 transition-colors duration-150" aria-label={showNewPassword ? 'Hide password' : 'Show password'}>{showNewPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}</button>
                                                </div>
                                                {newPassword && (
                                                    <div className="mt-2.5 space-y-1.5">
                                                        <div className="flex items-center justify-between text-xs"><span className="text-gray-600 dark:text-gray-400">Password Strength</span><span className={`font-semibold ${strengthTextColor}`}>{strengthLabel}</span></div>
                                                        <div className="h-1.5 bg-gray-200 dark:bg-[#1e2535] rounded-full overflow-hidden"><div className={`h-full ${strengthColor} transition-all duration-300 rounded-full`} style={{ width: `${passwordStrength}%` }} /></div>
                                                    </div>
                                                )}
                                                {errors.newPassword && <p className="mt-1.5 text-xs text-red-600 dark:text-red-400 flex items-center gap-1.5"><AlertTriangle className="w-3.5 h-3.5 flex-shrink-0" />{errors.newPassword.message}</p>}
                                            </div>
                                            <div>
                                                <label htmlFor="confirmPassword" className="block text-sm font-semibold text-gray-700 dark:text-gray-300 mb-2">Confirm New Password</label>
                                                <div className="relative">
                                                    <input id="confirmPassword" type={showConfirmPassword ? 'text' : 'password'} {...register('confirmPassword', { required: 'Please confirm your password', validate: (value) => value === newPassword || 'Passwords do not match' })} className={`${inputClass(!!errors.confirmPassword)} pr-11`} placeholder="Confirm new password" />
                                                    <button type="button" onClick={() => setShowConfirmPassword(!showConfirmPassword)} className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-600 hover:text-gray-600 dark:hover:text-gray-300 transition-colors duration-150" aria-label={showConfirmPassword ? 'Hide password' : 'Show password'}>{showConfirmPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}</button>
                                                </div>
                                                {errors.confirmPassword && <p className="mt-1.5 text-xs text-red-600 dark:text-red-400 flex items-center gap-1.5"><AlertTriangle className="w-3.5 h-3.5 flex-shrink-0" />{errors.confirmPassword.message}</p>}
                                            </div>
                                            <div className="flex items-center gap-3 pt-2">
                                                <button type="submit" disabled={isSubmitting} className="flex-1 flex items-center justify-center gap-2 px-6 py-2.5 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed text-white text-sm font-semibold rounded-lg transition-colors duration-150 shadow-sm">
                                                    {isSubmitting ? (<><LoadingSpinner size="sm" />Updating…</>) : (<><Save className="w-4 h-4" />Update Password</>)}
                                                </button>
                                                <button type="button" onClick={() => reset()} className="px-6 py-2.5 border border-gray-300 dark:border-[#1e2535] hover:bg-gray-50 dark:hover:bg-[#0f1117] hover:border-gray-400 dark:hover:border-[#2a3347] text-gray-700 dark:text-gray-300 text-sm font-medium rounded-lg transition-all duration-150">Cancel</button>
                                            </div>
                                        </div>
                                    </form>
                                </div>
                                <div className="mt-5 p-4 bg-yellow-50 dark:bg-yellow-500/10 border border-yellow-200 dark:border-yellow-500/20 rounded-xl flex gap-3 transition-colors duration-200">
                                    <div className="w-8 h-8 rounded-lg bg-yellow-100 dark:bg-yellow-500/10 flex items-center justify-center flex-shrink-0 mt-0.5"><Shield className="w-4 h-4 text-yellow-600 dark:text-yellow-400" /></div>
                                    <div>
                                        <h3 className="text-sm font-semibold text-yellow-900 dark:text-yellow-300 mb-1">Sovereign Security</h3>
                                        <p className="text-sm text-yellow-800 dark:text-yellow-400/80 leading-relaxed">Your credentials protect the entire Agentium governance system. Use a strong, unique password and store it securely.</p>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
                );

            case 'appearance':
                return (
                    <div className={isActive ? 'block' : 'hidden'} role="tabpanel">
                        <div className="max-w-2xl mx-auto">
                            <div className="bg-white dark:bg-[#161b27] rounded-xl border border-gray-200 dark:border-[#1e2535] p-6 shadow-sm dark:shadow-[0_2px_16px_rgba(0,0,0,0.25)]">
                                <h2 className="text-xl font-semibold text-gray-900 dark:text-white mb-2 flex items-center gap-2">
                                    <Monitor className="w-5 h-5 text-gray-600 dark:text-gray-500" />
                                    Theme
                                </h2>
                                <p className="text-gray-600 dark:text-gray-400 text-sm mb-6">Choose your preferred color scheme.</p>
                                <ThemeSelector />
                            </div>
                            {/* Future: language, font size, sidebar collapse, animations */}
                            <div className="mt-6 bg-white dark:bg-[#161b27] rounded-xl border border-gray-200 dark:border-[#1e2535] p-6 shadow-sm dark:shadow-[0_2px_16px_rgba(0,0,0,0.25)]">
                                <h2 className="text-xl font-semibold text-gray-900 dark:text-white mb-2 flex items-center gap-2">
                                    <Sliders className="w-5 h-5 text-gray-600 dark:text-gray-500" />
                                    Interface (Coming Soon)
                                </h2>
                                <p className="text-gray-600 dark:text-gray-400 text-sm">Language, font size, sidebar behavior, and animation settings will be available here.</p>
                            </div>
                        </div>
                    </div>
                );

            case 'preferences':
                return (
                    <div className={isActive ? 'block' : 'hidden'} role="tabpanel">
                        <PreferencesTab />
                    </div>
                );

            case 'api-keys':
                return (
                    <div className={isActive ? 'block' : 'hidden'} role="tabpanel">
                        <ApiKeysTab />
                    </div>
                );

            case 'notifications':
                return (
                    <div className={isActive ? 'block' : 'hidden'} role="tabpanel">
                        <NotificationsTab />
                    </div>
                );

            case 'users':
                if (!user?.is_admin) return null;
                return (
                    <div className={isActive ? 'block' : 'hidden'} role="tabpanel">
                        <UserManagement embedded onPendingCountChange={setPendingCount} />
                    </div>
                );

            default:
                return null;
        }
    };

    return (
        <div className="min-h-screen bg-gray-50 dark:bg-[#0f1117] p-6 transition-colors duration-200">
            <div className="max-w-6xl mx-auto">
                <div className="mb-8">
                    <h1 className="text-3xl font-bold text-gray-900 dark:text-white mb-1">Settings</h1>
                    <p className="text-gray-600 dark:text-gray-400 text-sm">Manage your account and system preferences.</p>
                </div>

                <div className="flex flex-wrap gap-2 mb-6" role="tablist" aria-label="Settings sections">
                    {TABS.map(renderTabButton)}
                </div>

                {TABS.map(tab => renderTabPanel(tab.id))}
            </div>
        </div>
    );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npm test -- frontend/src/pages/__tests__/SettingsPage.test.tsx`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/SettingsPage.tsx frontend/src/pages/__tests__/SettingsPage.test.tsx
git commit -m "feat: update SettingsPage with 6 tabs (Account, Appearance, Preferences, API Keys, Notifications, User Management)"
```

### Task 10: Integration Tests & Polish

**Files:**
- Create: `frontend/src/__tests__/settings-integration.test.tsx`
- Modify: `frontend/src/components/settings/index.ts` (barrel exports)

**Tests:**
1. Full SettingsPage render with all tabs
2. Theme persistence across reloads (localStorage + preference)
3. Preference changes persist to backend and survive reload
4. API Keys tab CRUD flow
5. Admin vs non-admin tab visibility
6. Dark/light mode renders correctly in all tabs
6. Accessibility audit (axe)

**Polish:**
- Barrel export for settings components
- Ensure all components have proper TypeScript types
- Run lint and typecheck
- Verify no console errors

- [ ] **Step 1: Write the failing integration test**

```tsx
// frontend/src/__tests__/settings-integration.test.tsx
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import { SettingsPage } from '@/pages/SettingsPage';
import { useAuthStore } from '@/store/authStore';
import { useUserPreferences } from '@/hooks/useUserPreferences';
import { useModelConfigs } from '@/hooks/useModelConfigs';
import { isDarkMode, setDarkMode } from '@/utils/theme';

jest.mock('@/store/authStore');
jest.mock('@/hooks/useUserPreferences');
jest.mock('@/hooks/useModelConfigs');
jest.mock('@/utils/theme');

const mockUseAuthStore = useAuthStore as jest.MockedFunction<typeof useAuthStore>;
const mockUseUserPreferences = useUserPreferences as jest.MockedFunction<typeof useUserPreferences>;
const mockUseModelConfigs = useModelConfigs as jest.MockedFunction<typeof useModelConfigs>;
const mockIsDarkMode = isDarkMode as jest.MockedFunction<typeof isDarkMode>;
const mockSetDarkMode = setDarkMode as jest.MockedFunction<typeof setDarkMode>;

describe('SettingsPage Integration', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockUseAuthStore.mockReturnValue({
      user: { id: 'user-1', username: 'testuser', is_admin: false, isAuthenticated: true, role: 'user' },
      changePassword: jest.fn().mockResolvedValue(true),
      updateAvatar: jest.fn(),
    } as any);
    mockUseUserPreferences.mockReturnValue({
      preferences: { 'ui.theme': 'system', 'notifications.enabled': true },
      loading: false,
      error: null,
      initialized: true,
      updatePreference: jest.fn().mockResolvedValue(undefined),
      bulkUpdate: jest.fn().mockResolvedValue(undefined),
      refresh: jest.fn().mockResolvedValue(undefined),
      getPreference: (key: string, def?: any) => {
        const prefs: Record<string, any> = { 'ui.theme': 'system', 'notifications.enabled': true };
        return prefs[key] ?? def;
      },
    });
    mockUseModelConfigs.mockReturnValue({
      configs: [],
      loading: false,
      error: null,
      activeActions: new Map(),
      pendingDeleteId: null,
      activeCount: 0,
      totalTokens: 0,
      totalCost: 0,
      loadConfigs: jest.fn(),
      handleDelete: jest.fn(),
      handleSetDefault: jest.fn(),
      handleTest: jest.fn(),
      handleFetchModels: jest.fn(),
      handleSave: jest.fn(),
      setPendingCount: jest.fn(),
    });
    mockIsDarkMode.mockReturnValue(false);
    mockSetDarkMode.mockImplementation(() => {});
  });

  it('renders without console errors', () => {
    const consoleError = jest.spyOn(console, 'error').mockImplementation(() => {});
    
    render(<SettingsPage />);
    
    expect(consoleError).not.toHaveBeenCalled();
    consoleError.mockRestore();
  });

  it('theme selector changes persist to preference and localStorage', async () => {
    const mockUpdate = jest.fn().mockResolvedValue(undefined);
    mockUseUserPreferences.mockReturnValue({
      preferences: { 'ui.theme': 'light' },
      loading: false,
      error: null,
      initialized: true,
      updatePreference: mockUpdate,
      bulkUpdate: jest.fn(),
      refresh: jest.fn(),
      getPreference: (key: string) => key === 'ui.theme' ? 'light' : undefined,
    });

    render(<SettingsPage />);

    // Switch to Appearance tab
    fireEvent.click(screen.getByRole('tab', { name: /appearance/i }));

    // Click Dark theme
    fireEvent.click(screen.getByRole('radio', { name: /dark/i }));

    await waitFor(() => {
      expect(mockSetDarkMode).toHaveBeenCalledWith(true);
      expect(mockUpdate).toHaveBeenCalledWith('ui.theme', 'dark');
    });
  });

  it('preference change in Preferences tab calls updatePreference', async () => {
    const mockUpdate = jest.fn().mockResolvedValue(undefined);
    mockUseUserPreferences.mockReturnValue({
      preferences: { 'ui.theme': 'dark', 'chat.history_limit': 50 },
      loading: false,
      error: null,
      initialized: true,
      updatePreference: mockUpdate,
      bulkUpdate: jest.fn(),
      refresh: jest.fn(),
      getPreference: (key: string, def?: any) => ({ 'ui.theme': 'dark', 'chat.history_limit': 50 } as any)[key] ?? def,
    });

    render(<SettingsPage />);

    // Switch to Preferences tab
    fireEvent.click(screen.getByRole('tab', { name: /preferences/i }));

    // Find and change chat history limit
    const input = screen.getByRole('spinbutton', { name: /chat.history_limit/i });
    fireEvent.change(input, { target: { value: '100' } });
    fireEvent.blur(input);

    await waitFor(() => {
      expect(mockUpdate).toHaveBeenCalledWith('chat.history_limit', 100);
    });
  });

  it('API Keys tab shows empty state and add button', () => {
    render(<SettingsPage />);

    fireEvent.click(screen.getByRole('tab', { name: /api keys/i }));

    expect(screen.getByText(/no configurations yet/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /add your first provider/i })).toBeInTheDocument();
  });

  it('Notifications tab shows master toggle and conditional options', () => {
    render(<SettingsPage />);

    fireEvent.click(screen.getByRole('tab', { name: /notifications/i }));

    expect(screen.getByRole('checkbox', { name: /notifications.enabled/i })).toBeChecked();
    expect(screen.getByRole('checkbox', { name: /notifications.sound/i })).toBeInTheDocument();
    expect(screen.getByRole('listbox', { name: /notifications.channels/i })).toBeInTheDocument();

    // Disable master toggle
    fireEvent.click(screen.getByRole('checkbox', { name: /notifications.enabled/i }));

    expect(screen.queryByRole('checkbox', { name: /notifications.sound/i })).not.toBeInTheDocument();
    expect(screen.queryByRole('listbox', { name: /notifications.channels/i })).not.toBeInTheDocument();
  });

  it('admin user sees User Management tab', () => {
    mockUseAuthStore.mockReturnValue({
      user: { id: 'admin-1', username: 'admin', is_admin: true, isAuthenticated: true, role: 'admin' },
      changePassword: jest.fn().mockResolvedValue(true),
      updateAvatar: jest.fn(),
    } as any);

    render(<SettingsPage />);

    expect(screen.getByRole('tab', { name: /user management/i })).toBeInTheDocument();
  });

  it('non-admin user does not see User Management tab', () => {
    mockUseAuthStore.mockReturnValue({
      user: { id: 'user-1', username: 'user', is_admin: false, isAuthenticated: true, role: 'user' },
      changePassword: jest.fn().mockResolvedValue(true),
      updateAvatar: jest.fn(),
    } as any);

    render(<SettingsPage />);

    expect(screen.queryByRole('tab', { name: /user management/i })).not.toBeInTheDocument();
  });

  it('tab panels remain mounted when switching (state preserved)', () => {
    render(<SettingsPage />);

    // Type in password field on Account tab
    const currentPasswordInput = screen.getByLabelText(/current password/i);
    fireEvent.change(currentPasswordInput, { target: { value: 'secret123' } });

    // Switch to Appearance
    fireEvent.click(screen.getByRole('tab', { name: /appearance/i }));

    // Switch back to Account
    fireEvent.click(screen.getByRole('tab', { name: /account settings/i }));

    // Value should be preserved
    expect(screen.getByLabelText(/current password/i)).toHaveValue('secret123');
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm test -- frontend/src/__tests__/settings-integration.test.tsx`
Expected: FAIL - integration issues

- [ ] **Step 3: Fix any integration issues and run tests**

Run: `npm test -- frontend/src/__tests__/settings-integration.test.tsx`
Expected: PASS

- [ ] **Step 4: Create barrel export**

```typescript
// frontend/src/components/settings/index.ts
export * from './PreferenceInput';
export * from './PreferenceSection';
export * from './PreferencesTab';
export * from './ThemeSelector';
export * from './ApiKeysTab';
export * from './NotificationsTab';
```

- [ ] **Step 5: Run lint and typecheck**

Run: `npm run lint && npm run typecheck`
Expected: No errors

- [ ] **Step 6: Commit**

```bash
git add frontend/src/__tests__/settings-integration.test.tsx frontend/src/components/settings/index.ts
git commit -m "test: add SettingsPage integration tests and barrel exports"
```

### Task 11: E2E Tests & Final Verification

**Files:**
- Create: `frontend/e2e/settings-page.spec.ts` (Playwright)
- Verify: All acceptance criteria from design spec

**E2E Test Scenarios:**
1. **Theme Persistence**: Change theme → reload page → theme persists
2. **Preference Persistence**: Change chat history limit → reload → value persists
3. **API Key Management**: Add provider → verify in list → edit → delete
4. **Admin Access**: Login as admin → verify User Management tab visible
5. **Non-Admin Access**: Login as user → verify User Management tab hidden
6. **Tab State Preservation**: Fill form → switch tabs → return → form intact
7. **Dark Mode**: Toggle theme → verify all tabs render correctly in dark mode

**Manual Verification Checklist:**
- [ ] All 6 tabs render correctly for appropriate user roles
- [ ] Theme selector works (Light/Dark/System) and persists
- [ ] All 51 default preferences are editable with correct input types
- [ ] Preference changes persist to backend and survive reload
- [ ] API Keys tab shows existing configs, allows add/edit/delete/test
- [ ] Notifications tab controls work and persist
- [ ] User Management tab only visible to admins
- [ ] No console errors, no TypeScript errors
- [ ] All existing SettingsPage functionality preserved (password, avatar)
- [ ] Dark/light mode renders correctly in all tabs
- [ ] Responsive design works on mobile/tablet/desktop
- [ ] Accessibility: keyboard navigation, ARIA labels, focus management

- [ ] **Step 1: Write E2E test for theme persistence**

```typescript
// frontend/e2e/settings-page.spec.ts
import { test, expect } from '@playwright/test';

test.describe('Settings Page', () => {
  test.beforeEach(async ({ page }) => {
    // Login as regular user
    await page.goto('/login');
    await page.fill('input[name="username"]', 'testuser');
    await page.fill('input[name="password"]', 'password123');
    await page.click('button[type="submit"]');
    await page.waitForURL('/dashboard');
    await page.goto('/settings');
  });

  test('theme selector persists across reload', async ({ page }) => {
    // Switch to Appearance tab
    await page.click('role=tab[name="Appearance"]');
    
    // Select Dark theme
    await page.click('role=radio[name="Dark"]');
    
    // Verify dark mode applied
    await expect(page.locator('html')).toHaveClass(/dark/);
    
    // Reload page
    await page.reload();
    await page.waitForLoadState('networkidle');
    
    // Verify dark mode still applied
    await expect(page.locator('html')).toHaveClass(/dark/);
    
    // Verify preference saved
    await page.click('role=tab[name="Appearance"]');
    await expect(page.locator('role=radio[name="Dark"]')).toBeChecked();
  });

  test('theme selector system option follows OS preference', async ({ page }) => {
    await page.click('role=tab[name="Appearance"]');
    await page.click('role=radio[name="System"]');
    
    // Verify system preference is saved
    await page.reload();
    await expect(page.locator('role=radio[name="System"]')).toBeChecked();
  });

  test('preference changes persist to backend', async ({ page }) => {
    await page.click('role=tab[name="Preferences"]');
    
    // Find chat history limit input and change it
    const historyLimitInput = page.locator('role=spinbutton[name="chat.history_limit"]');
    await historyLimitInput.clear();
    await historyLimitInput.fill('75');
    await historyLimitInput.blur();
    
    // Wait for API call
    await page.waitForResponse('/api/v1/preferences/chat.history_limit');
    
    // Reload and verify
    await page.reload();
    await page.click('role=tab[name="Preferences"]');
    await expect(historyLimitInput).toHaveValue('75');
  });

  test('API Keys tab - add provider flow', async ({ page }) => {
    await page.click('role=tab[name="API Keys"]');
    
    // Click add provider
    await page.click('role=button[name="Add Provider"]');
    
    // Select provider (OpenAI)
    await page.click('role=button[name="Select OpenAI"]');
    
    // Fill config name
    await page.fill('input[name="config_name"]', 'Test OpenAI Config');
    
    // Fill API key
    await page.fill('input[name="api_key"]', 'sk-test123');
    
    // Save
    await page.click('role=button[name="Update Password"]'); // This might need adjustment based on actual button text
    
    // Verify appears in list
    await expect(page.locator('text=Test OpenAI Config')).toBeVisible();
  });

  test('Notifications tab - master toggle hides/shows options', async ({ page }) => {
    await page.click('role=tab[name="Notifications"]');
    
    // Verify options visible when enabled
    await expect(page.locator('role=checkbox[name="notifications.sound"]')).toBeVisible();
    await expect(page.locator('role=listbox[name="notifications.channels"]')).toBeVisible();
    
    // Disable master toggle
    await page.click('role=checkbox[name="notifications.enabled"]');
    
    // Verify options hidden
    await expect(page.locator('role=checkbox[name="notifications.sound"]')).not.toBeVisible();
    await expect(page.locator('role=listbox[name="notifications.channels"]')).not.toBeVisible();
    
    // Re-enable
    await page.click('role=checkbox[name="notifications.enabled"]');
    await expect(page.locator('role=checkbox[name="notifications.sound"]')).toBeVisible();
  });

  test('tab state preserved when switching', async ({ page }) => {
    // Type in password field
    await page.fill('input[name="currentPassword"]', 'secret123');
    
    // Switch to Appearance
    await page.click('role=tab[name="Appearance"]');
    
    // Switch back to Account
    await page.click('role=tab[name="Account Settings"]');
    
    // Value preserved
    await expect(page.locator('input[name="currentPassword"]')).toHaveValue('secret123');
  });

  test('dark mode renders correctly in all tabs', async ({ page }) => {
    // Enable dark mode
    await page.click('role=tab[name="Appearance"]');
    await page.click('role=radio[name="Dark"]');
    
    // Check each tab renders without visual issues
    const tabs = ['Account Settings', 'Appearance', 'Preferences', 'API Keys', 'Notifications'];
    
    for (const tabName of tabs) {
      await page.click(`role=tab[name="${tabName}"]`);
      // Verify no white backgrounds in dark mode (basic check)
      const bgColor = await page.locator('body').evaluate(el => getComputedStyle(el).backgroundColor);
      expect(bgColor).not.toBe('rgb(255, 255, 255)'); // Not pure white
    }
  });
});

test.describe('Settings Page - Admin', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/login');
    await page.fill('input[name="username"]', 'admin');
    await page.fill('input[name="password"]', 'admin');
    await page.click('button[type="submit"]');
    await page.waitForURL('/dashboard');
    await page.goto('/settings');
  });

  test('admin sees User Management tab', async ({ page }) => {
    await expect(page.locator('role=tab[name="User Management"]')).toBeVisible();
  });

  test('User Management tab loads embedded component', async ({ page }) => {
    await page.click('role=tab[name="User Management"]');
    await expect(page.locator('text=User Management')).toBeVisible();
  });
});
```

- [ ] **Step 2: Run E2E tests**

Run: `npx playwright test frontend/e2e/settings-page.spec.ts`
Expected: PASS (may need backend running)

- [ ] **Step 3: Manual verification of all acceptance criteria**

Run through checklist manually with dev server running

- [ ] **Step 4: Final commit**

```bash
git add frontend/e2e/settings-page.spec.ts
git commit -m "test: add E2E tests for SettingsPage"
```

---

## Summary

### Total Tasks: 11

| Task | Component | Description |
|------|-----------|-------------|
| 1 | `preferences.ts` | API service with types and tests |
| 2 | `useUserPreferences.ts` | Hook with optimistic updates and tests |
| 3 | `PreferenceInput.tsx` | Polymorphic input component with tests |
| 4 | `PreferenceSection.tsx` | Collapsible category section with tests |
| 5 | `PreferencesTab.tsx` | Main preferences panel with tests |
| 6 | `ThemeSelector.tsx` | Light/Dark/System theme selector with tests |
| 7 | `ApiKeysTab.tsx` | Embedded model config management with tests |
| 8 | `NotificationsTab.tsx` | Notification preferences with tests |
| 9 | `SettingsPage.tsx` | Updated with 6 tabs integration |
| 10 | Integration tests | Cross-component tests + barrel exports + lint |
| 11 | E2E tests | Playwright tests + manual verification |

### File Structure Created

```
frontend/src/
├── services/
│   ├── preferences.ts
│   └── __tests__/preferences.test.ts
├── hooks/
│   ├── useUserPreferences.ts
│   └── __tests__/useUserPreferences.test.ts
├── components/
│   └── settings/
│       ├── index.ts
│       ├── PreferenceInput.tsx
│       ├── PreferenceSection.tsx
│       ├── PreferencesTab.tsx
│       ├── ThemeSelector.tsx
│       ├── ApiKeysTab.tsx
│       ├── NotificationsTab.tsx
│       └── __tests__/
│           ├── PreferenceInput.test.tsx
│           ├── PreferenceSection.test.tsx
│           ├── PreferencesTab.test.tsx
│           ├── ThemeSelector.test.tsx
│           ├── ApiKeysTab.test.tsx
│           └── NotificationsTab.test.tsx
├── pages/
│   ├── SettingsPage.tsx (modified)
│   └── __tests__/SettingsPage.test.tsx
├── __tests__/
│   └── settings-integration.test.tsx
└── e2e/
    └── settings-page.spec.ts
```

### Dependencies Reused
- `useAuthStore`, `useToast`, `api` service
- `useModelConfigs`, `modelsApi`, `ModelConfigForm`
- `isDarkMode`, `setDarkMode` from `@/utils/theme`
- `UserManagement` component (embedded)
- `LoadingSpinner`, `Toggle` UI components
- `lucide-react` icons
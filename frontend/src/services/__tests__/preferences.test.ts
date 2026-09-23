import { describe, it, expect, beforeEach, vi } from 'vitest';
import { preferencesApi } from '@/services/preferences';
import { api } from '@/services/api';

vi.mock('@/services/api');

describe('preferencesApi', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('getAll', () => {
    it('fetches preferences with optional filters', async () => {
      const mockPrefs = [{ key: 'ui.theme', value: 'dark', category: 'ui' }];
      vi.mocked(api.get).mockResolvedValue({ data: mockPrefs } as any);

      const result = await preferencesApi.getAll({ category: 'ui' });

      expect(api.get).toHaveBeenCalledWith('/api/v1/preferences', { params: { category: 'ui', scope: undefined } });
      expect(result).toEqual(mockPrefs);
    });
  });

  describe('get', () => {
    it('fetches a single preference with default value', async () => {
      const mockResponse = { key: 'ui.theme', value: 'dark', default_used: false };
      vi.mocked(api.get).mockResolvedValue({ data: mockResponse } as any);

      const result = await preferencesApi.get('ui.theme', 'light');

      expect(api.get).toHaveBeenCalledWith('/api/v1/preferences/ui.theme', { params: { default: 'light' } });
      expect(result).toEqual(mockResponse);
    });
  });

  describe('create', () => {
    it('sends POST request with preference data', async () => {
      const mockResponse = { status: 'created', preference: { key: 'ui.theme', value: 'dark' } };
      vi.mocked(api.post).mockResolvedValue({ data: mockResponse } as any);

      const result = await preferencesApi.create({ key: 'ui.theme', value: 'dark', category: 'ui' });

      expect(api.post).toHaveBeenCalledWith('/api/v1/preferences', { key: 'ui.theme', value: 'dark', category: 'ui' });
      expect(result).toEqual(mockResponse);
    });
  });

  describe('update', () => {
    it('sends PUT request with value and reason', async () => {
      const mockResponse = { status: 'updated', preference: { key: 'ui.theme', value: 'light' } };
      vi.mocked(api.put).mockResolvedValue({ data: mockResponse } as any);

      const result = await preferencesApi.update('ui.theme', { value: 'light', reason: 'user preference' });

      expect(api.put).toHaveBeenCalledWith('/api/v1/preferences/ui.theme', { value: 'light', reason: 'user preference' });
      expect(result).toEqual(mockResponse);
    });
  });

  describe('delete', () => {
    it('sends DELETE request', async () => {
      const mockResponse = { status: 'deleted', key: 'ui.theme' };
      vi.mocked(api.delete).mockResolvedValue({ data: mockResponse } as any);

      const result = await preferencesApi.delete('ui.theme');

      expect(api.delete).toHaveBeenCalledWith('/api/v1/preferences/ui.theme');
      expect(result).toEqual(mockResponse);
    });
  });

  describe('bulkUpdate', () => {
    it('sends POST with preferences map and reason', async () => {
      const mockResponse = { status: 'success', results: { success: ['ui.theme'], failed: [] } };
      vi.mocked(api.post).mockResolvedValue({ data: mockResponse } as any);

      const result = await preferencesApi.bulkUpdate({ preferences: { 'ui.theme': 'light' }, reason: 'bulk' });

      expect(api.post).toHaveBeenCalledWith('/api/v1/preferences/bulk', { preferences: { 'ui.theme': 'light' }, reason: 'bulk' });
      expect(result).toEqual(mockResponse);
    });
  });

  describe('getDefaults', () => {
    it('fetches default preferences and category metadata', async () => {
      const mockResponse = { defaults: { 'ui.theme': 'dark' }, categories: { ui: 'Interface' } };
      vi.mocked(api.get).mockResolvedValue({ data: mockResponse } as any);

      const result = await preferencesApi.getDefaults();

      expect(api.get).toHaveBeenCalledWith('/api/v1/preferences/system/defaults');
      expect(result).toEqual(mockResponse);
    });
  });

  describe('initializeDefaults', () => {
    it('initializes default preferences for current user', async () => {
      const mockResponse = { status: 'initialized', count: 10, preferences: [] };
      vi.mocked(api.post).mockResolvedValue({ data: mockResponse } as any);

      const result = await preferencesApi.initializeDefaults();

      expect(api.post).toHaveBeenCalledWith('/api/v1/preferences/system/initialize');
      expect(result).toEqual(mockResponse);
    });
  });
});
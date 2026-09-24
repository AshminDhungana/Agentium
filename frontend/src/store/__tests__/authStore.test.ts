// frontend/src/store/__tests__/authStore.test.ts
// Session-management tests (pre-existing) + deriveIsSovereign truth table
// (12.4.2 artifact). Plain is_admin is deliberately NOT sufficient (B6: not
// all admins are sovereign); the sovereign flag or the primary_sovereign role
// is required.
import { describe, it, expect, vi, beforeEach } from 'vitest';

const storageMap = new Map<string, string>();
const mockLocalStorage = {
  getItem: vi.fn((key: string) => storageMap.get(key) ?? null),
  setItem: vi.fn((key: string, value: string) => {
    storageMap.set(key, String(value));
  }),
  removeItem: vi.fn((key: string) => {
    storageMap.delete(key);
  }),
  clear: vi.fn(() => {
    storageMap.clear();
  }),
  key: vi.fn((index: number) => Array.from(storageMap.keys())[index] ?? null),
  get length() {
    return storageMap.size;
  },
};

Object.defineProperty(globalThis, 'localStorage', {
  value: mockLocalStorage,
  configurable: true,
  writable: true,
});

vi.mock('@/services/api', () => ({
  api: {
    post: vi.fn(),
    defaults: {
      headers: {
        common: {},
      },
    },
  },
}));

import { useAuthStore, deriveIsSovereign } from '../authStore';
import { api } from '@/services/api';

describe('authStore session management', () => {
  beforeEach(() => {
    mockLocalStorage.clear();
    delete api.defaults.headers.common['Authorization'];
    vi.clearAllMocks();
    useAuthStore.setState({
      user: null,
      isInitialized: false,
      isLoading: false,
      error: null,
    });
  });

  it('logout calls /api/v1/auth/logout and clears localStorage, token headers, and store state', async () => {
    mockLocalStorage.setItem('access_token', 'valid-test-token');
    api.defaults.headers.common['Authorization'] = 'Bearer valid-test-token';
    useAuthStore.setState({
      user: {
        id: 'usr-1',
        username: 'testuser',
        is_admin: false,
        isAuthenticated: true,
      },
    });

    (api.post as any).mockResolvedValueOnce({
      data: { status: 'success', message: 'Logged out successfully' },
    });

    await useAuthStore.getState().logout();

    expect(api.post).toHaveBeenCalledWith('/api/v1/auth/logout');
    expect(mockLocalStorage.getItem('access_token')).toBeNull();
    expect(api.defaults.headers.common['Authorization']).toBeUndefined();
    expect(useAuthStore.getState().user).toBeNull();
    expect(useAuthStore.getState().isInitialized).toBe(true);
  });

  it('logout clears local state even if backend logout API fails', async () => {
    mockLocalStorage.setItem('access_token', 'failing-token');
    useAuthStore.setState({
      user: {
        id: 'usr-1',
        username: 'testuser',
        is_admin: false,
        isAuthenticated: true,
      },
    });

    (api.post as any).mockRejectedValueOnce(new Error('Network error'));

    await useAuthStore.getState().logout();

    expect(api.post).toHaveBeenCalledWith('/api/v1/auth/logout');
    expect(mockLocalStorage.getItem('access_token')).toBeNull();
    expect(useAuthStore.getState().user).toBeNull();
    expect(useAuthStore.getState().isInitialized).toBe(true);
  });

  it('checkAuth restores user session on valid backend response', async () => {
    mockLocalStorage.setItem('access_token', 'valid-jwt');

    (api.post as any).mockResolvedValueOnce({
      data: {
        valid: true,
        user: {
          user_id: 'usr-42',
          username: 'restoreduser',
          is_admin: true,
          role: 'primary_sovereign',
          is_sovereign: true,
        },
      },
    });

    const success = await useAuthStore.getState().checkAuth();

    expect(success).toBe(true);
    expect(api.post).toHaveBeenCalledWith('/api/v1/auth/verify', null);
    const storeUser = useAuthStore.getState().user;
    expect(storeUser?.username).toBe('restoreduser');
    expect(storeUser?.isAuthenticated).toBe(true);
    expect(useAuthStore.getState().isInitialized).toBe(true);
  });

  it('checkAuth clears state when token verification fails (valid=false)', async () => {
    mockLocalStorage.setItem('access_token', 'invalid-jwt');

    (api.post as any).mockResolvedValueOnce({
      data: { valid: false },
    });

    const success = await useAuthStore.getState().checkAuth();

    expect(success).toBe(false);
    expect(mockLocalStorage.getItem('access_token')).toBeNull();
    expect(useAuthStore.getState().user).toBeNull();
    expect(useAuthStore.getState().isInitialized).toBe(true);
  });
});

describe('deriveIsSovereign', () => {
  it('returns true for the is_sovereign flag (DB path)', () => {
    expect(deriveIsSovereign({ is_sovereign: true })).toBe(true);
  });

  it('returns true for the primary_sovereign role', () => {
    expect(deriveIsSovereign({ role: 'primary_sovereign' })).toBe(true);
  });

  it('returns false for a plain admin (not all admins are sovereign)', () => {
    expect(deriveIsSovereign({ is_admin: true, role: 'admin' })).toBe(false);
  });

  it('returns false for the observer role', () => {
    expect(deriveIsSovereign({ role: 'observer' })).toBe(false);
  });

  it('returns false for the JWT-fallback shape (no role/is_sovereign claims)', () => {
    expect(deriveIsSovereign({ is_admin: true })).toBe(false);
  });

  it('returns false for an empty user', () => {
    expect(deriveIsSovereign({})).toBe(false);
  });
});

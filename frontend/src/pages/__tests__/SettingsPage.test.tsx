import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { describe, it, expect, beforeEach, vi } from 'vitest';

// ── Mocks ─────────────────────────────────────────────────────────────────────

vi.mock('@/services/api', () => ({
  api: {
    get: vi.fn().mockResolvedValue({ data: {} }),
    post: vi.fn().mockResolvedValue({ data: {} }),
    put: vi.fn().mockResolvedValue({ data: {} }),
    delete: vi.fn().mockResolvedValue({ data: {} }),
  },
  rawFetch: vi.fn().mockResolvedValue({}),
}));

vi.mock('@/hooks/useToast', () => ({
  showToast: { success: vi.fn(), error: vi.fn(), info: vi.fn() },
}));

import { SettingsPage } from '@/pages/SettingsPage';
import { useAuthStore } from '@/store/authStore';

// ── Helpers ───────────────────────────────────────────────────────────────────

const ADMIN_USER = {
  id: '1',
  username: 'sovereign',
  is_admin: true,
  isAuthenticated: true,
  isSovereign: true,
  role: 'primary_sovereign' as const,
  last_login_at: '2026-09-20T10:00:00Z',
  avatar_url: null,
};

const REGULAR_USER = {
  id: '2',
  username: 'testuser',
  is_admin: false,
  isAuthenticated: true,
  isSovereign: false,
  role: 'user' as const,
  last_login_at: '2026-09-22T14:30:00Z',
  avatar_url: null,
};

function renderSettings(userOverride?: typeof ADMIN_USER) {
  useAuthStore.setState({
    user: userOverride ?? ADMIN_USER,
    isLoading: false,
    error: null,
    changePassword: vi.fn().mockResolvedValue(true),
    updateAvatar: vi.fn(),
  } as any);

  return render(
    <MemoryRouter>
      <SettingsPage />
    </MemoryRouter>,
  );
}

// ── 12.3.1 — SettingsPage renders all settings sections ───────────────────────

describe('12.3.1 — SettingsPage renders all settings sections', () => {
  beforeEach(() => vi.clearAllMocks());

  it('renders the page header', () => {
    renderSettings();
    expect(screen.getByText('Settings')).toBeInTheDocument();
    expect(screen.getByText('Manage your account and system preferences.')).toBeInTheDocument();
  });

  it('renders the Account Settings tab button', () => {
    renderSettings();
    expect(screen.getByText('Account Settings')).toBeInTheDocument();
  });

  it('renders the Account Card with username and role', () => {
    renderSettings();
    expect(screen.getByText('sovereign')).toBeInTheDocument();
    expect(screen.getByText('primary_sovereign')).toBeInTheDocument();
  });

  it('renders the Account Info section', () => {
    renderSettings();
    expect(screen.getByText('Account Info')).toBeInTheDocument();
    expect(screen.getByText('User ID')).toBeInTheDocument();
    expect(screen.getByText('Permissions')).toBeInTheDocument();
    expect(screen.getByText('2FA Status')).toBeInTheDocument();
  });

  it('renders the permission label based on role', () => {
    renderSettings();
    // primary_sovereign maps to "Full Access" in ROLE_PERMISSION_LABELS
    expect(screen.getByText('Full Access')).toBeInTheDocument();
  });

  it('renders the Change Password form', () => {
    renderSettings();
    expect(screen.getByText('Change Password')).toBeInTheDocument();
    expect(screen.getByLabelText('Current Password')).toBeInTheDocument();
    expect(screen.getByLabelText('New Password')).toBeInTheDocument();
    expect(screen.getByLabelText('Confirm New Password')).toBeInTheDocument();
    expect(screen.getByText('Update Password')).toBeInTheDocument();
  });

  it('renders the Sovereign Security notice', () => {
    renderSettings();
    expect(screen.getByText('Sovereign Security')).toBeInTheDocument();
  });

  it('renders the last login date', () => {
    renderSettings();
    // "2026-09-20T10:00:00Z" → "Sep 20, 2026"
    expect(screen.getByText('Sep 20, 2026')).toBeInTheDocument();
  });

  it('renders Account Status as Active', () => {
    renderSettings();
    expect(screen.getByText('Account Status')).toBeInTheDocument();
    expect(screen.getByText('Active')).toBeInTheDocument();
  });

  it('renders avatar upload button', () => {
    renderSettings();
    expect(screen.getByText('Upload picture')).toBeInTheDocument();
  });

  it('admin user sees User Management tab', () => {
    renderSettings(ADMIN_USER);
    expect(screen.getByText('User Management')).toBeInTheDocument();
  });

  it('non-admin user does NOT see User Management tab', () => {
    renderSettings(REGULAR_USER);
    expect(screen.queryByText('User Management')).not.toBeInTheDocument();
  });
});

// ── 12.3.2 — User preferences save and persist ───────────────────────────────

describe('12.3.2 — User preferences save and persist (password change)', () => {
  beforeEach(() => vi.clearAllMocks());

  it('password change form submits successfully', async () => {
    const mockChangePassword = vi.fn().mockResolvedValue(true);
    useAuthStore.setState({
      user: ADMIN_USER,
      isLoading: false,
      error: null,
      changePassword: mockChangePassword,
      updateAvatar: vi.fn(),
    } as any);

    render(
      <MemoryRouter>
        <SettingsPage />
      </MemoryRouter>,
    );

    const user = userEvent.setup();

    await user.type(screen.getByLabelText('Current Password'), 'OldPass123!');
    await user.type(screen.getByLabelText('New Password'), 'NewPass456!');
    await user.type(screen.getByLabelText('Confirm New Password'), 'NewPass456!');
    await user.click(screen.getByText('Update Password'));

    await waitFor(() => {
      expect(mockChangePassword).toHaveBeenCalledWith('OldPass123!', 'NewPass456!');
    });
  });

  it('password strength indicator appears when typing new password', async () => {
    renderSettings();
    const user = userEvent.setup();

    await user.type(screen.getByLabelText('New Password'), 'StrongP@ss1');

    await waitFor(() => {
      expect(screen.getByText('Password Strength')).toBeInTheDocument();
    });
  });

  it('shows validation error when passwords do not match', async () => {
    renderSettings();
    const user = userEvent.setup();

    await user.type(screen.getByLabelText('Current Password'), 'OldPass123!');
    await user.type(screen.getByLabelText('New Password'), 'NewPass456!');
    await user.type(screen.getByLabelText('Confirm New Password'), 'Mismatch!');
    await user.click(screen.getByText('Update Password'));

    await waitFor(() => {
      expect(screen.getByText('Passwords do not match')).toBeInTheDocument();
    });
  });
});

// ── 12.3.2 — Preferences service layer ───────────────────────────────────────

describe('12.3.2 — Preferences service exports', () => {
  it('preferencesApi exports all required methods', async () => {
    const { preferencesApi } = await import('@/services/preferences');
    expect(typeof preferencesApi.getAll).toBe('function');
    expect(typeof preferencesApi.get).toBe('function');
    expect(typeof preferencesApi.create).toBe('function');
    expect(typeof preferencesApi.update).toBe('function');
    expect(typeof preferencesApi.delete).toBe('function');
    expect(typeof preferencesApi.bulkUpdate).toBe('function');
    expect(typeof preferencesApi.getDefaults).toBe('function');
    expect(typeof preferencesApi.initializeDefaults).toBe('function');
  });

  it('exports all preference categories', async () => {
    const { CATEGORY_LABELS } = await import('@/services/preferences');
    const expectedCategories = ['ui', 'chat', 'notifications', 'agents', 'tasks', 'models', 'tools', 'privacy', 'custom'];
    for (const cat of expectedCategories) {
      expect(CATEGORY_LABELS).toHaveProperty(cat);
    }
  });
});

// ── 12.3.3 — Dark/light theme toggle ─────────────────────────────────────────

describe('12.3.3 — Theme toggle utility', () => {
  it('theme utility exports all required functions', async () => {
    const theme = await import('@/utils/theme');
    expect(typeof theme.isDarkMode).toBe('function');
    expect(typeof theme.setDarkMode).toBe('function');
    expect(typeof theme.toggleTheme).toBe('function');
  });
});

// ── 12.3.4 — API key management ──────────────────────────────────────────────

describe('12.3.4 — API key management service', () => {
  it('apiKeysService exports deleteKey, getSpendHistory, testFailover', async () => {
    const mod = await import('@/services/apiKeysService');
    const service = mod.default;
    expect(typeof service.deleteKey).toBe('function');
    expect(typeof service.getSpendHistory).toBe('function');
    expect(typeof service.testFailover).toBe('function');
  });
});

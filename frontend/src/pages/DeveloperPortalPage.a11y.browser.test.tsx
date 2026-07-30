// frontend/src/pages/DeveloperPortalPage.a11y.browser.test.tsx
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import { auditRoute } from '@/test/a11yBrowser';
import DeveloperPortalPage from '@/pages/DeveloperPortalPage';
import { useAuthStore } from '@/store/authStore';
import { useWebSocketStore } from '@/store/websocketStore';

describe('DeveloperPortalPage color-contrast', () => {
  beforeEach(() => {
    useAuthStore.setState({
      user: { isAuthenticated: true, username: 'test', is_admin: false, isSovereign: false },
      isLoading: false,
    });
    useWebSocketStore.setState({
      connectionPhase: 'active',
      isConnected: true,
      error: null,
      connectionStats: null,
      unreadCount: 0,
      messageHistory: [],
      lastMessage: null,
      genesisJustCompleted: false,
    } as any);
  });

  it('passes in light theme', async () => {
    const result = await auditRoute(<MemoryRouter><DeveloperPortalPage /></MemoryRouter>, 'light');
    expect(result).toHaveNoViolations();
  });

  it('passes in dark theme', async () => {
    const result = await auditRoute(<MemoryRouter><DeveloperPortalPage /></MemoryRouter>, 'dark');
    expect(result).toHaveNoViolations();
  });
});
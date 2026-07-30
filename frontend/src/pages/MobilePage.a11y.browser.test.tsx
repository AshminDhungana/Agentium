// frontend/src/pages/MobilePage.a11y.browser.test.tsx
import { vi, describe, it, expect, beforeEach } from 'vitest';
import { MemoryRouter } from 'react-router-dom';

vi.mock('@/services/api', () => ({
  api: {
    get: vi.fn().mockResolvedValue({
      data: {
        status: 'online',
        active_agents: 5,
        tasks: { pending: 2, failed: 0 },
        active_votes: 1,
        role: 'user',
        unread_notifications: 3
      }
    }),
    post: vi.fn().mockResolvedValue({ data: {} }),
    put: vi.fn().mockResolvedValue({ data: {} }),
    delete: vi.fn().mockResolvedValue({ data: {} }),
  },
  rawFetch: vi.fn().mockResolvedValue({}),
}));

import { auditRoute } from '@/test/a11yBrowser';
import { MobilePage } from '@/pages/MobilePage';
import { useAuthStore } from '@/store/authStore';
import { useWebSocketStore } from '@/store/websocketStore';

describe('MobilePage color-contrast', () => {
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

  function formatViolations(violations: any[]) {
  return violations.map((v: any) => ({
    id: v.id,
    impact: v.impact,
    description: v.description,
    helpUrl: v.helpUrl,
    nodes: v.nodes.map((n: any) => ({
      html: n.html,
      target: n.target,
      impact: n.impact,
      any: n.any?.map((a: any) => ({
        id: a.id,
        message: a.message,
        data: a.data,
      })),
    })),
  }));
}

it('passes in light theme', async () => {
    const result = await auditRoute(<MemoryRouter><MobilePage /></MemoryRouter>, 'light');
    if (result.violations.length > 0) {
      console.log('=== LIGHT THEME VIOLATIONS ===');
      console.log(JSON.stringify(formatViolations(result.violations), null, 2));
    }
    expect(result).toHaveNoViolations();
  });

  it('passes in dark theme', async () => {
    const result = await auditRoute(<MemoryRouter><MobilePage /></MemoryRouter>, 'dark');
    if (result.violations.length > 0) {
      console.log('=== DARK THEME VIOLATIONS ===');
      console.log(JSON.stringify(formatViolations(result.violations), null, 2));
    }
    expect(result).toHaveNoViolations();
  });
});
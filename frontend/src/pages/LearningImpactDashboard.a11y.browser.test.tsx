// frontend/src/pages/LearningImpactDashboard.a11y.browser.test.tsx
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import { auditRoute } from '@/test/a11yBrowser';
import { LearningImpactDashboard } from '@/pages/LearningImpactDashboard';
import { useAuthStore } from '@/store/authStore';
import { useWebSocketStore } from '@/store/websocketStore';

vi.mock('@/services/improvements', () => ({
  improvementsApi: {
    getImpactStats: vi.fn().mockResolvedValue({
      success_rate_delta: 5.2,
      tools_generated: 10,
      anti_patterns_warned: 3,
      history: [{ date: '2024-01-01', success_rate: 0.85 }],
    }),
    getPatterns: vi.fn().mockResolvedValue({ patterns: [] }),
    triggerConsolidation: vi.fn().mockResolvedValue(undefined),
  },
}));

vi.mock('@/hooks/useToast', () => ({
  showToast: {
    error: vi.fn(),
    success: vi.fn(),
  },
}));

describe('LearningImpactDashboard color-contrast', () => {
  beforeEach(() => {
    useAuthStore.setState({
      user: { isAuthenticated: true, username: 'test', is_admin: false, isSovereign: false },
      isLoading: false,
    });
    useWebSocketStore.setState({
      connectionPhase: 'active',
      error: null,
      connectionStats: {
        reconnectAttempts: 0,
        lastPingTime: null,
        latencyMs: null,
      },
      lastMessage: null,
      unreadCount: 0,
      messageHistory: [],
      lastWorkspace: null,
      apiKeyAddedAt: null,
      genesisAwaitingName: false,
      genesisNamePrompt: '',
      genesisNameTimeout: 0,
      genesisJustCompleted: false,
    } as any);
  });

  it('passes in light theme', async () => {
    const result = await auditRoute(<MemoryRouter><LearningImpactDashboard /></MemoryRouter>, 'light');
    expect(result).toHaveNoViolations();
  });

  it('passes in dark theme', async () => {
    const result = await auditRoute(<MemoryRouter><LearningImpactDashboard /></MemoryRouter>, 'dark');
    expect(result).toHaveNoViolations();
  });
});
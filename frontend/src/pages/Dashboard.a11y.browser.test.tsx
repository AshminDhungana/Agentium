import { describe, it, expect, vi } from 'vitest';
import { MemoryRouter, Routes, Route } from 'react-router-dom';

vi.mock('@/hooks/useDashboardData', () => ({
  useDashboardData: () => ({
    stats: {}, recentTasks: [], activeAgentsList: [],
    isAgentsLoading: false, isTasksLoading: false,
    isAgentsError: false, isTasksError: false,
    refetchAgents: vi.fn(), refetchTasks: vi.fn(),
  }),
}));
vi.mock('@/services/api', () => ({
  api: { get: vi.fn().mockResolvedValue({ data: {} }) },
  rawFetch: vi.fn().mockResolvedValue({}),
}));
vi.mock('@/services/admin', () => ({
  adminService: {
    getBudgetStatus: vi.fn().mockResolvedValue({ data: {} }),
    getBudgetHistory: vi.fn().mockResolvedValue({ data: [] }),
  },
}));

import { auditRoute } from '@/test/a11yBrowser';
import Dashboard from '@/pages/Dashboard';
import { useBackendStore } from '@/store/backendStore';

describe('Dashboard page color-contrast', () => {
  beforeEach(() => {
    useBackendStore.setState({
      status: { status: 'connected', version: '1.0.0', lastChecked: new Date(), latency: 100 },
      fetchChannelMetrics: vi.fn(),
      startPolling: vi.fn(),
    } as any);
  });

  it('passes in light theme', async () => {
    const result = await auditRoute(
      <MemoryRouter>
        <Routes>
          <Route path="/" element={<Dashboard />} />
        </Routes>
      </MemoryRouter>,
      'light'
    );
    expect(result).toHaveNoViolations();
  });

  it('passes in dark theme', async () => {
    const result = await auditRoute(
      <MemoryRouter>
        <Routes>
          <Route path="/" element={<Dashboard />} />
        </Routes>
      </MemoryRouter>,
      'dark'
    );
    expect(result).toHaveNoViolations();
  });
});

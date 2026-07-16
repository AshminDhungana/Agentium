import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, it, expect, beforeEach, vi } from 'vitest';

vi.mock('@/hooks/useDashboardData', () => ({
  useDashboardData: () => ({
    stats: {}, recentTasks: [], activeAgentsList: [],
    isAgentsLoading: false, isTasksLoading: false,
    isAgentsError: false, isTasksError: false,
    refetchAgents: vi.fn(), refetchTasks: vi.fn(),
  }),
}));
// Confirmed module paths from prior tasks:
vi.mock('@/services/api', () => ({ api: { get: vi.fn().mockResolvedValue({ data: {} }) } }));
vi.mock('@/services/admin', () => ({
  adminService: {
    getBudgetStatus: vi.fn().mockResolvedValue({ data: {} }),
    getBudgetHistory: vi.fn().mockResolvedValue({ data: [] }),
  },
}));

import Dashboard from '@/pages/Dashboard';
import { useBackendStore } from '@/store/backendStore';

describe('Dashboard page', () => {
  beforeEach(() => { vi.clearAllMocks(); });

  it('shows the skeleton while backend is disconnected', () => {
    useBackendStore.setState({ status: { status: 'disconnected' }, fetchChannelMetrics: vi.fn() } as any);
    render(<MemoryRouter><Dashboard /></MemoryRouter>);
    expect(screen.getByTestId('dashboard-skeleton')).toBeInTheDocument();
  });

  it('renders widgets in regions when connected', () => {
    useBackendStore.setState({ status: { status: 'connected' }, fetchChannelMetrics: vi.fn() } as any);
    render(<MemoryRouter><Dashboard /></MemoryRouter>);
    expect(screen.getByRole('region', { name: 'Recent tasks' })).toBeInTheDocument();
    expect(screen.getByRole('region', { name: 'System health' })).toBeInTheDocument();
    expect(screen.getByRole('region', { name: 'Provider analytics' })).toBeInTheDocument();
  });
});

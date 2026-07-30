// frontend/src/pages/ABTestingPage.a11y.browser.test.tsx
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import { auditRoute } from '@/test/a11yBrowser';
import { ABTestingPage } from '@/pages/ABTestingPage';
import { useAuthStore } from '@/store/authStore';
import { useWebSocketStore } from '@/store/websocketStore';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

// Mock all API services used by ABTestingPage to avoid 500 errors in browser tests
vi.mock('@/services/api', () => ({
  api: vi.fn().mockImplementation(() => Promise.resolve({ data: [] })),
  rawFetch: vi.fn().mockResolvedValue({}),
}));

vi.mock('@/services/abTesting', () => ({
  abTestingApi: {
    listExperiments: vi.fn().mockResolvedValue({ data: [], total: 0, page: 1, pageSize: 10 }),
    getExperiment: vi.fn().mockResolvedValue({}),
    getExperimentResults: vi.fn().mockResolvedValue({}),
    getModelComparison: vi.fn().mockResolvedValue([]),
    createExperiment: vi.fn().mockResolvedValue({}),
    updateExperiment: vi.fn().mockResolvedValue({}),
    deleteExperiment: vi.fn().mockResolvedValue({}),
    startExperiment: vi.fn().mockResolvedValue({}),
    stopExperiment: vi.fn().mockResolvedValue({}),
  },
  ExperimentStatus: {
    DRAFT: 'draft',
    RUNNING: 'running',
    COMPLETED: 'completed',
    STOPPED: 'stopped',
    FAILED: 'failed',
  },
}));

describe('ABTestingPage color-contrast', () => {
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

  const renderWithQueryClient = (ui: React.ReactElement) => {
    const queryClient = new QueryClient({
      defaultOptions: {
        queries: { retry: false },
      },
    });
    return <QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>;
  };

  it('passes in light theme', async () => {
    const result = await auditRoute(
      <MemoryRouter>{renderWithQueryClient(<ABTestingPage />)}</MemoryRouter>,
      'light'
    );
    expect(result).toHaveNoViolations();
  });

  it('passes in dark theme', async () => {
    const result = await auditRoute(
      <MemoryRouter>{renderWithQueryClient(<ABTestingPage />)}</MemoryRouter>,
      'dark'
    );
    expect(result).toHaveNoViolations();
  });
});
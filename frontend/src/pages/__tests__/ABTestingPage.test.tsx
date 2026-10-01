// frontend/src/pages/__tests__/ABTestingPage.test.tsx
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { describe, it, expect, beforeEach, vi } from 'vitest';

// ── Mocks ─────────────────────────────────────────────────────────────────────

vi.mock('@/services/api', () => ({
  api: {
    get: vi.fn().mockResolvedValue({ data: [] }),
    post: vi.fn().mockResolvedValue({ data: {} }),
    delete: vi.fn().mockResolvedValue({ data: {} }),
  },
}));

vi.mock('@/hooks/useToast', () => ({
  showToast: { success: vi.fn(), error: vi.fn(), info: vi.fn() },
}));

vi.mock('@/store/websocketStore', () => ({
  useWebSocketStore: vi.fn(() => null),
}));

// Mock recharts components to avoid canvas/SVG rendering in JSDOM
vi.mock('recharts', () => ({
  BarChart: ({ children }: any) => <div data-testid="bar-chart">{children}</div>,
  Bar: () => <div />,
  XAxis: () => <div />,
  YAxis: () => <div />,
  CartesianGrid: () => <div />,
  Tooltip: () => <div />,
  ResponsiveContainer: ({ children }: any) => <div>{children}</div>,
  Legend: () => <div />,
  RadarChart: ({ children }: any) => <div data-testid="radar-chart">{children}</div>,
  PolarGrid: () => <div />,
  PolarAngleAxis: () => <div />,
  Radar: () => <div />,
  Cell: () => <div />,
}));

vi.mock('@/services/abTesting', () => ({
  abTestingApi: {
    listExperiments: vi.fn(),
    getExperiment: vi.fn(),
    createExperiment: vi.fn(),
    deleteExperiment: vi.fn(),
    cancelExperiment: vi.fn(),
    quickTest: vi.fn(),
    getStats: vi.fn(),
    getRecommendations: vi.fn(),
  },
}));

import { ABTestingPage } from '@/pages/ABTestingPage';
import { abTestingApi } from '@/services/abTesting';
import { useAuthStore } from '@/store/authStore';
import { showToast } from '@/hooks/useToast';

// ── Test Data ─────────────────────────────────────────────────────────────────

const ADMIN_USER = {
  id: 'usr-uuid-1',
  username: 'sovereign',
  is_admin: true,
  isAuthenticated: true,
  isSovereign: true,
  role: 'primary_sovereign' as const,
};

const NON_ADMIN_USER = {
  id: 'usr-uuid-2',
  username: 'viewer',
  is_admin: false,
  isAuthenticated: true,
  isSovereign: false,
  role: 'user' as const,
};

const MOCK_STATS = {
  total_experiments: 5,
  completed_experiments: 3,
  running_experiments: 1,
  total_model_runs: 20,
  cached_recommendations: 2,
};

const MOCK_EXPERIMENT = {
  id: 'exp-001',
  name: 'GPT-4o vs Claude 3.5',
  description: 'Summarisation comparison',
  status: 'completed' as const,
  models_tested: 2,
  progress: 100,
  total_runs: 4,
  completed_runs: 4,
  failed_runs: 0,
  created_at: '2026-09-28T10:00:00Z',
  started_at: '2026-09-28T10:00:01Z',
  completed_at: '2026-09-28T10:05:00Z',
};

const MOCK_EXPERIMENT_DETAIL = {
  ...MOCK_EXPERIMENT,
  task_template: 'Summarise this document in 3 bullet points.',
  system_prompt: null,
  test_iterations: 1,
  runs: [
    {
      id: 'run-001',
      model: 'gpt-4o',
      config_id: 'cfg-001',
      iteration: 1,
      status: 'completed' as const,
      tokens: 150,
      latency_ms: 1200,
      cost_usd: 0.0032,
      quality_score: 85,
      critic_plan_score: 80,
      critic_code_score: 70,
      critic_output_score: 90,
      constitutional_violations: 0,
      output_preview: 'Here are the 3 bullet points...',
      error_message: null,
      started_at: '2026-09-28T10:00:01Z',
      completed_at: '2026-09-28T10:00:03Z',
    },
    {
      id: 'run-002',
      model: 'claude-3.5-sonnet',
      config_id: 'cfg-002',
      iteration: 1,
      status: 'completed' as const,
      tokens: 180,
      latency_ms: 950,
      cost_usd: 0.0028,
      quality_score: 92,
      critic_plan_score: 88,
      critic_code_score: 75,
      critic_output_score: 95,
      constitutional_violations: 0,
      output_preview: 'Summary: 1) First point...',
      error_message: null,
      started_at: '2026-09-28T10:00:01Z',
      completed_at: '2026-09-28T10:00:02Z',
    },
  ],
  comparison: {
    winner: {
      config_id: 'cfg-002',
      model: 'claude-3.5-sonnet',
      reason: 'Higher quality score with lower latency and cost',
      confidence: 87.5,
    },
    model_comparisons: {
      models: [
        {
          config_id: 'cfg-001',
          model_name: 'gpt-4o',
          avg_tokens: 150,
          avg_cost_usd: 0.0032,
          avg_latency_ms: 1200,
          avg_quality_score: 85,
          success_rate: 100,
          total_runs: 2,
          completed_runs: 2,
          failed_runs: 0,
        },
        {
          config_id: 'cfg-002',
          model_name: 'claude-3.5-sonnet',
          avg_tokens: 180,
          avg_cost_usd: 0.0028,
          avg_latency_ms: 950,
          avg_quality_score: 92,
          success_rate: 100,
          total_runs: 2,
          completed_runs: 2,
          failed_runs: 0,
        },
      ],
    },
    created_at: '2026-09-28T10:05:00Z',
  },
};

const MOCK_PAGINATED = {
  items: [MOCK_EXPERIMENT],
  total: 1,
  limit: 18,
  offset: 0,
};

const MOCK_RECOMMENDATIONS = {
  recommendations: [
    {
      task_category: 'summarisation',
      recommended_model: 'claude-3.5-sonnet',
      avg_quality_score: 92,
      avg_cost_usd: 0.0028,
      avg_latency_ms: 950,
      success_rate: 100,
      sample_size: 4,
      last_updated: '2026-09-28T10:05:00Z',
    },
  ],
  total_categories: 1,
};

// ── Helpers ───────────────────────────────────────────────────────────────────

function renderPage(user = ADMIN_USER) {
  useAuthStore.setState({
    user,
    isLoading: false,
    error: null,
  } as any);

  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
    },
  });

  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <ABTestingPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

// ── 12.7.1 — ABTestingPage displays experiments ──────────────────────────────

describe('12.7.1 — ABTestingPage displays experiments', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(abTestingApi.listExperiments).mockResolvedValue(MOCK_PAGINATED);
    vi.mocked(abTestingApi.getStats).mockResolvedValue(MOCK_STATS);
    vi.mocked(abTestingApi.getRecommendations).mockResolvedValue(MOCK_RECOMMENDATIONS);
  });

  it('renders Access Denied for non-admin users', () => {
    renderPage(NON_ADMIN_USER);
    expect(screen.getByText('Access Denied')).toBeInTheDocument();
    expect(screen.getByText(/only admin users/i)).toBeInTheDocument();
  });

  it('renders header, stats row, and experiment grid for admins', async () => {
    renderPage();

    // Header
    expect(screen.getByText('A/B Model Testing')).toBeInTheDocument();

    // Stats cards load
    await waitFor(() => {
      expect(screen.getByText('Total Experiments')).toBeInTheDocument();
    });
    expect(screen.getByText('5')).toBeInTheDocument();   // total_experiments
    expect(screen.getByText('3')).toBeInTheDocument();   // completed_experiments
    expect(screen.getByText('20')).toBeInTheDocument();  // total_model_runs

    // Experiment card
    await waitFor(() => {
      expect(screen.getByText('GPT-4o vs Claude 3.5')).toBeInTheDocument();
    });
  });

  it('status filter buttons change the query', async () => {
    const user = userEvent.setup();
    renderPage();

    // Wait for initial load
    await waitFor(() => {
      expect(abTestingApi.listExperiments).toHaveBeenCalledWith(undefined, 18, 0);
    });

    // Click "running" filter
    const runningBtn = screen.getByRole('button', { name: /^running$/i });
    await user.click(runningBtn);

    await waitFor(() => {
      expect(abTestingApi.listExperiments).toHaveBeenCalledWith('running', 18, 0);
    });
  });

  it('shows empty state when no experiments exist', async () => {
    vi.mocked(abTestingApi.listExperiments).mockResolvedValue({
      items: [],
      total: 0,
      limit: 18,
      offset: 0,
    });

    renderPage();

    await waitFor(() => {
      expect(screen.getByText('No experiments yet')).toBeInTheDocument();
    });
    expect(screen.getByText(/create your first a\/b test/i)).toBeInTheDocument();
  });

  it('pagination controls appear when total > PAGE_SIZE', async () => {
    const manyItems = Array.from({ length: 18 }, (_, i) => ({
      ...MOCK_EXPERIMENT,
      id: `exp-${i}`,
      name: `Experiment ${i}`,
    }));
    vi.mocked(abTestingApi.listExperiments).mockResolvedValue({
      items: manyItems,
      total: 36,  // 2 pages
      limit: 18,
      offset: 0,
    });

    renderPage();

    await waitFor(() => {
      expect(screen.getByText('Page 1 of 2')).toBeInTheDocument();
    });
    expect(screen.getByText(/next/i)).toBeInTheDocument();
  });
});

// ── 12.7.2 — Create/edit/delete experiments works ────────────────────────────

describe('12.7.2 — Create/edit/delete experiments works', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(abTestingApi.listExperiments).mockResolvedValue(MOCK_PAGINATED);
    vi.mocked(abTestingApi.getStats).mockResolvedValue(MOCK_STATS);
    vi.mocked(abTestingApi.getRecommendations).mockResolvedValue(MOCK_RECOMMENDATIONS);
    vi.mocked(abTestingApi.createExperiment).mockResolvedValue(MOCK_EXPERIMENT);
    vi.mocked(abTestingApi.deleteExperiment).mockResolvedValue({ message: 'deleted' });
    vi.mocked(abTestingApi.quickTest).mockResolvedValue(MOCK_EXPERIMENT);
    vi.mocked(abTestingApi.getExperiment).mockResolvedValue(MOCK_EXPERIMENT_DETAIL);
  });

  it('opens create experiment modal with required fields', async () => {
    const user = userEvent.setup();
    renderPage();

    const newBtn = screen.getByRole('button', { name: /new experiment/i });
    await user.click(newBtn);

    expect(screen.getByRole('heading', { name: 'New Experiment' })).toBeInTheDocument();
    expect(screen.getByPlaceholderText(/gpt-4o vs claude/i)).toBeInTheDocument();
    expect(screen.getByPlaceholderText(/exact prompt/i)).toBeInTheDocument();
    expect(screen.getByText(/models to compare/i)).toBeInTheDocument();
    expect(screen.getByText(/iterations per model/i)).toBeInTheDocument();
  });

  it('delete shows confirmation modal and calls API', async () => {
    const user = userEvent.setup();
    renderPage();

    // Wait for card to render
    await waitFor(() => {
      expect(screen.getByText('GPT-4o vs Claude 3.5')).toBeInTheDocument();
    });

    // Hover to reveal delete button
    const deleteBtn = screen.getByRole('button', { name: /delete experiment/i });
    await user.click(deleteBtn);

    // Confirm modal appears
    expect(screen.getByText('Delete Experiment')).toBeInTheDocument();
    expect(screen.getByText(/cannot be undone/i)).toBeInTheDocument();

    // Confirm
    const confirmBtn = screen.getByRole('button', { name: /^delete$/i });
    await user.click(confirmBtn);

    await waitFor(() => {
      expect(abTestingApi.deleteExperiment).toHaveBeenCalledWith('exp-001');
    });
  });

  it('quick test modal opens and shows models', async () => {
    const user = userEvent.setup();
    renderPage();

    const quickBtn = screen.getByRole('button', { name: /quick test/i });
    await user.click(quickBtn);

    expect(screen.getByText('Quick A/B Test')).toBeInTheDocument();
    expect(screen.getByPlaceholderText(/enter the prompt/i)).toBeInTheDocument();
  });
});

// ── 12.7.3 — Experiment results and metrics display correctly ────────────────

describe('12.7.3 — Experiment results and metrics display correctly', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(abTestingApi.listExperiments).mockResolvedValue(MOCK_PAGINATED);
    vi.mocked(abTestingApi.getStats).mockResolvedValue(MOCK_STATS);
    vi.mocked(abTestingApi.getRecommendations).mockResolvedValue(MOCK_RECOMMENDATIONS);
    vi.mocked(abTestingApi.getExperiment).mockResolvedValue(MOCK_EXPERIMENT_DETAIL);
  });

  it('experiment detail panel shows winner and metrics', async () => {
    const user = userEvent.setup();
    renderPage();

    // Wait for card, then click to open detail
    await waitFor(() => {
      expect(screen.getByText('GPT-4o vs Claude 3.5')).toBeInTheDocument();
    });

    // Click the card (not the delete button)
    const card = screen.getByText('GPT-4o vs Claude 3.5');
    await user.click(card);

    // Detail panel shows winner
    await waitFor(() => {
      expect(screen.getByText(/winner: claude-3.5-sonnet/i)).toBeInTheDocument();
    });

    // Confidence score
    expect(screen.getByText('87.5')).toBeInTheDocument();

    // Model comparison table
    expect(screen.getByText('Model Comparison')).toBeInTheDocument();
    expect(screen.getAllByText('gpt-4o').length).toBeGreaterThan(0);

    // Individual runs section
    expect(screen.getByText(/individual runs/i)).toBeInTheDocument();
  });

  it('recommendations tab displays model recommendations', async () => {
    const user = userEvent.setup();
    renderPage();

    // Switch to recommendations tab
    const recsTab = screen.getByRole('button', { name: /recommendations/i });
    await user.click(recsTab);

    await waitFor(() => {
      expect(screen.getByText('Model Recommendations')).toBeInTheDocument();
    });

    // Recommendation entry
    await waitFor(() => {
      expect(screen.getByText('summarisation')).toBeInTheDocument();
    });
    expect(screen.getByText('claude-3.5-sonnet')).toBeInTheDocument();
    expect(screen.getByText('92.0')).toBeInTheDocument();  // quality score pill
  });

  it('detail panel shows task template at bottom', async () => {
    const user = userEvent.setup();
    renderPage();

    await waitFor(() => {
      expect(screen.getByText('GPT-4o vs Claude 3.5')).toBeInTheDocument();
    });

    await user.click(screen.getByText('GPT-4o vs Claude 3.5'));

    await waitFor(() => {
      expect(screen.getByText('Task Template')).toBeInTheDocument();
    });
    expect(screen.getByText('Summarise this document in 3 bullet points.')).toBeInTheDocument();
  });
});

// frontend/src/pages/__tests__/LearningImpactDashboard.test.tsx
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, beforeEach, vi } from 'vitest';

// ── Mocks ─────────────────────────────────────────────────────────────────────

const mockGetImpactStats = vi.fn();
const mockGetPatterns = vi.fn();
const mockTriggerConsolidation = vi.fn();

vi.mock('@/services/improvements', () => ({
  improvementsApi: {
    getImpactStats: (...args: any[]) => mockGetImpactStats(...args),
    getPatterns: (...args: any[]) => mockGetPatterns(...args),
    triggerConsolidation: (...args: any[]) => mockTriggerConsolidation(...args),
  },
}));

vi.mock('@/hooks/useToast', () => ({
  showToast: { success: vi.fn(), error: vi.fn(), info: vi.fn() },
}));

// Mock recharts
vi.mock('recharts', () => ({
  LineChart: ({ children, data }: any) => (
    <div data-testid="line-chart" data-points={data?.length ?? 0}>
      {children}
    </div>
  ),
  Line: () => <div data-testid="line" />,
  XAxis: () => <div data-testid="xaxis" />,
  YAxis: () => <div data-testid="yaxis" />,
  CartesianGrid: () => <div data-testid="cartesian-grid" />,
  Tooltip: () => <div data-testid="tooltip" />,
  ResponsiveContainer: ({ children }: any) => <div data-testid="responsive-container">{children}</div>,
}));

import { LearningImpactDashboard } from '@/pages/LearningImpactDashboard';
import { useAuthStore } from '@/store/authStore';
import { showToast } from '@/hooks/useToast';

// ── Test Data ─────────────────────────────────────────────────────────────────

const ADMIN_USER = {
  id: 'usr-admin-1',
  username: 'admin',
  is_admin: true,
  isAuthenticated: true,
  isSovereign: true,
  role: 'primary_sovereign' as const,
};

const REGULAR_USER = {
  id: 'usr-regular-1',
  username: 'observer',
  is_admin: false,
  isAuthenticated: true,
  isSovereign: false,
  role: 'observer' as const,
};

const MOCK_STATS = {
  success_rate_delta: 3.5,
  tools_generated: 12,
  anti_patterns_warned: 4,
  total_reviews_processed: 85,
  history: [
    { date: '2026-09-27', success_rate: 82.5 },
    { date: '2026-09-28', success_rate: 84.0 },
    { date: '2026-09-29', success_rate: 85.0 },
    { date: '2026-09-30', success_rate: 86.0 },
  ],
};

const MOCK_PATTERNS = [
  {
    id: 'bp_task_123',
    type: 'best_practice',
    content: 'Always use indexed fields when performing database lookups.',
    confidence: 0.95,
  },
  {
    id: 'ap_task_456',
    type: 'anti_pattern',
    content: 'Unbounded query results cause memory exhaustion.',
    confidence: 0.85,
  },
];

function setAuth(user: typeof ADMIN_USER | typeof REGULAR_USER) {
  useAuthStore.setState({ user, isLoading: false } as any);
}

describe('LearningImpactDashboard', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    setAuth(ADMIN_USER);
    mockGetImpactStats.mockResolvedValue(MOCK_STATS);
    mockGetPatterns.mockResolvedValue({ patterns: MOCK_PATTERNS });
    mockTriggerConsolidation.mockResolvedValue(undefined);
  });

  it('renders heading and subtitle correctly', async () => {
    render(<LearningImpactDashboard />);

    await waitFor(() => {
      expect(screen.getByText('Continuous Self-Improvement Engine')).toBeInTheDocument();
    });
    expect(
      screen.getByText('Real-time learning metrics, anti-pattern detection, and knowledge consolidation.')
    ).toBeInTheDocument();
  });

  it('renders all 4 KPI metric cards with correct values', async () => {
    render(<LearningImpactDashboard />);

    await waitFor(() => {
      expect(screen.getByText('Success Rate Delta (7d)')).toBeInTheDocument();
    });
    expect(screen.getByText('+3.5%')).toBeInTheDocument();

    expect(screen.getByText('Auto-Generated Tools')).toBeInTheDocument();
    expect(screen.getByText('12')).toBeInTheDocument();

    expect(screen.getByText('Anti-Patterns Prevented')).toBeInTheDocument();
    expect(screen.getByText('4')).toBeInTheDocument();

    expect(screen.getByText('Total Reviews Processed')).toBeInTheDocument();
    expect(screen.getByText('85')).toBeInTheDocument();
  });

  it('renders success rate trend chart with fetched history points', async () => {
    render(<LearningImpactDashboard />);

    await waitFor(() => {
      expect(screen.getByText('Success Rate Trend (7-Day History)')).toBeInTheDocument();
    });
    const chart = screen.getByTestId('line-chart');
    expect(chart).toBeInTheDocument();
    expect(chart).toHaveAttribute('data-points', '4');
  });

  it('renders patterns list with correct badges and contents', async () => {
    render(<LearningImpactDashboard />);

    await waitFor(() => {
      expect(screen.getByText('Recent Pattern Discoveries')).toBeInTheDocument();
    });

    expect(screen.getByText('BEST PRACTICE')).toBeInTheDocument();
    expect(screen.getByText('ANTI-PATTERN')).toBeInTheDocument();
    expect(screen.getByText(/Always use indexed fields/i)).toBeInTheDocument();
    expect(screen.getByText(/Unbounded query results/i)).toBeInTheDocument();
    expect(screen.getByText('ID: bp_task_123')).toBeInTheDocument();
    expect(screen.getByText('ID: ap_task_456')).toBeInTheDocument();
  });

  it('renders empty state when patterns list is empty', async () => {
    mockGetPatterns.mockResolvedValueOnce({ patterns: [] });
    render(<LearningImpactDashboard />);

    await waitFor(() => {
      expect(screen.getByText('No patterns discovered')).toBeInTheDocument();
    });
  });

  it('re-fetches data when Refresh button is clicked', async () => {
    const user = userEvent.setup();
    render(<LearningImpactDashboard />);

    await waitFor(() => {
      expect(mockGetImpactStats).toHaveBeenCalledTimes(1);
    });

    const refreshBtn = screen.getByRole('button', { name: /Refresh/i });
    await user.click(refreshBtn);

    expect(mockGetImpactStats).toHaveBeenCalledTimes(2);
    expect(mockGetPatterns).toHaveBeenCalledTimes(2);
  });

  it('allows admin / sovereign user to trigger consolidation', async () => {
    const user = userEvent.setup();
    setAuth(ADMIN_USER);
    render(<LearningImpactDashboard />);

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Trigger Consolidation/i })).toBeEnabled();
    });

    const triggerBtn = screen.getByRole('button', { name: /Trigger Consolidation/i });
    await user.click(triggerBtn);

    expect(mockTriggerConsolidation).toHaveBeenCalledTimes(1);
    await waitFor(() => {
      expect(showToast.success).toHaveBeenCalledWith(
        'Manual knowledge consolidation triggered successfully!'
      );
    });
  });

  it('disables Trigger Consolidation button for non-admin user', async () => {
    setAuth(REGULAR_USER);
    render(<LearningImpactDashboard />);

    await waitFor(() => {
      const triggerBtn = screen.getByRole('button', { name: /Trigger Consolidation/i });
      expect(triggerBtn).toBeDisabled();
    });
    expect(mockTriggerConsolidation).not.toHaveBeenCalled();
  });

  it('shows error banner when initial fetch fails and allows retry', async () => {
    const user = userEvent.setup();
    mockGetImpactStats.mockRejectedValueOnce(new Error('Network connection timeout'));
    render(<LearningImpactDashboard />);

    await waitFor(() => {
      expect(screen.getByText('Network connection timeout')).toBeInTheDocument();
    });
    expect(showToast.error).toHaveBeenCalledWith('Failed to load learning impact data');

    // Clicking retry button attempts refetch
    mockGetImpactStats.mockResolvedValueOnce(MOCK_STATS);
    mockGetPatterns.mockResolvedValueOnce({ patterns: MOCK_PATTERNS });
    const retryBtn = screen.getByRole('button', { name: /Retry/i });
    await user.click(retryBtn);

    await waitFor(() => {
      expect(screen.getByText('+3.5%')).toBeInTheDocument();
    });
  });
});

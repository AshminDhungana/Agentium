// frontend/src/pages/__tests__/ScalingDashboard.test.tsx
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { describe, it, expect, beforeEach, vi } from 'vitest';

// ── Mocks ─────────────────────────────────────────────────────────────────────

const mockGet = vi.fn();
const mockPost = vi.fn();

vi.mock('@/services/api', () => ({
  api: {
    get: (...args: any[]) => mockGet(...args),
    post: (...args: any[]) => mockPost(...args),
  },
}));

vi.mock('@/hooks/useToast', () => ({
  showToast: { success: vi.fn(), error: vi.fn(), info: vi.fn() },
}));

vi.mock('@/store/websocketStore', () => ({
  useWebSocketStore: vi.fn(() => null),
}));

// Mock recharts to avoid canvas/SVG rendering in JSDOM
vi.mock('recharts', () => ({
  LineChart: ({ children }: any) => <div data-testid="line-chart">{children}</div>,
  Line: () => <div />,
  XAxis: () => <div />,
  YAxis: () => <div />,
  CartesianGrid: () => <div />,
  Tooltip: () => <div />,
  ResponsiveContainer: ({ children }: any) => <div>{children}</div>,
}));

import { ScalingDashboard } from '@/pages/ScalingDashboard';
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

const MOCK_PREDICTIONS = {
  next_1h: 5.4,
  next_6h: 7.2,
  next_24h: 4.1,
  current_capacity: 3,
  recommendation: 'neutral',
  token_spend: 2.75,
  budget_limit: 10.0,
};

const MOCK_PREDICTIONS_SPAWN = {
  ...MOCK_PREDICTIONS,
  recommendation: 'spawn',
};

const MOCK_HISTORY_EVENT = {
  id: 'audit-001',
  agentium_id: 'A123456789',
  created_at: '2026-09-30T12:00:00Z',
  updated_at: '2026-09-30T12:00:00Z',
  is_active: true,
  level: 'info',
  category: 'governance',
  actor: { type: 'system', id: 'Predictive Auto-Scaler' },
  action: 'auto_scale_predictive_spawn',
  description: 'Predictive scale spawned 2 agents.',
  target: null,
  result: { success: true, message: null, error: null },
  timestamp: '2026-09-30T12:00:00Z',
  duration_ms: null,
  metadata: null,
  screenshot_url: null,
};

// ── Helpers ───────────────────────────────────────────────────────────────────

function setAuth(user: typeof ADMIN_USER | typeof NON_ADMIN_USER) {
  useAuthStore.setState({ user, isLoading: false } as any);
}

function setupApiMocks(opts?: {
  predictions?: object;
  history?: object[];
}) {
  const preds = opts?.predictions ?? MOCK_PREDICTIONS;
  const hist = opts?.history ?? [];
  mockGet.mockImplementation((url: string) => {
    if (url.includes('/scaling/predictions/load')) {
      return Promise.resolve({ data: preds });
    }
    if (url.includes('/scaling/history')) {
      return Promise.resolve({ data: { history: hist } });
    }
    return Promise.resolve({ data: {} });
  });
  mockPost.mockResolvedValue({ data: { status: 'success', spawned: 1 } });
}

function renderDashboard() {
  return render(
    <MemoryRouter>
      <ScalingDashboard />
    </MemoryRouter>
  );
}

// ── Tests ─────────────────────────────────────────────────────────────────────

describe('ScalingDashboard', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.useFakeTimers({ shouldAdvanceTime: true });
    setAuth(ADMIN_USER);
    setupApiMocks();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  // ── 12.8.1: Auto-scaling metrics ──────────────────────────────────────────

  it('renders heading "Predictive Auto-Scaling" on mount', async () => {
    renderDashboard();
    expect(screen.getByText('Predictive Auto-Scaling')).toBeInTheDocument();
  });

  it('fetches predictions and history from API on mount', async () => {
    renderDashboard();
    await waitFor(() => {
      expect(mockGet).toHaveBeenCalledWith('/api/v1/scaling/predictions/load');
      expect(mockGet).toHaveBeenCalledWith('/api/v1/scaling/history');
    });
  });

  it('displays 4 metric summary cards with data from predictions', async () => {
    renderDashboard();
    await waitFor(() => {
      // Active Agents card
      expect(screen.getByText('Active Agents')).toBeInTheDocument();
      expect(screen.getByText('3')).toBeInTheDocument();
      // Predicted (1h) card
      expect(screen.getByText('Predicted (1h)')).toBeInTheDocument();
      expect(screen.getByText('5.4')).toBeInTheDocument();
      // Token Budget card — now shows live data instead of $0.00
      expect(screen.getByText('Token Budget')).toBeInTheDocument();
      expect(screen.getByText('$2.75')).toBeInTheDocument();
      // System Mode card
      expect(screen.getByText('System Mode')).toBeInTheDocument();
      expect(screen.getByText('Auto-Scaling Active')).toBeInTheDocument();
    });
  });

  it('shows recommendation banner when recommendation is not neutral', async () => {
    setupApiMocks({ predictions: MOCK_PREDICTIONS_SPAWN });
    renderDashboard();
    await waitFor(() => {
      expect(screen.getByText(/System Recommendation:/)).toBeInTheDocument();
      expect(screen.getByText(/SPAWN/)).toBeInTheDocument();
    });
  });

  it('hides recommendation banner when recommendation is neutral', async () => {
    setupApiMocks({ predictions: MOCK_PREDICTIONS });
    renderDashboard();
    // Wait for data fetch to complete
    await waitFor(() => {
      expect(mockGet).toHaveBeenCalled();
    });
    expect(screen.queryByText(/System Recommendation:/)).not.toBeInTheDocument();
  });

  it('shows EmptyState when scaling history is empty', async () => {
    setupApiMocks({ history: [] });
    renderDashboard();
    await waitFor(() => {
      expect(screen.getByText('No scaling history')).toBeInTheDocument();
      expect(screen.getByText('No recent scaling events recorded.')).toBeInTheDocument();
    });
  });

  it('renders scaling history table with event data', async () => {
    setupApiMocks({ history: [MOCK_HISTORY_EVENT] });
    renderDashboard();
    await waitFor(() => {
      expect(screen.getByText('Scaling Activity Log')).toBeInTheDocument();
      expect(screen.getAllByText('auto_scale_predictive_spawn').length).toBeGreaterThan(0);
      expect(screen.getAllByText('Predictive scale spawned 2 agents.').length).toBeGreaterThan(0);
    });
  });

  // ── 12.8.2: Manual scaling controls ───────────────────────────────────────

  it('shows manual override panel for admin users', async () => {
    setAuth(ADMIN_USER);
    renderDashboard();
    expect(screen.getByText('Manual Override')).toBeInTheDocument();
    expect(screen.getByText('Agent Count')).toBeInTheDocument();
    expect(screen.getByText('Agent Tier Target')).toBeInTheDocument();
    expect(screen.getByText(/Spawn/)).toBeInTheDocument();
    expect(screen.getByText(/Liquidate/)).toBeInTheDocument();
  });

  it('shows non-admin message for regular users', async () => {
    setAuth(NON_ADMIN_USER);
    renderDashboard();
    expect(screen.getByText(/Administrator or Sovereign/)).toBeInTheDocument();
    expect(screen.queryByText('Agent Count')).not.toBeInTheDocument();
  });

  it('spawn button calls API with correct payload', async () => {
    vi.useRealTimers();
    const user = userEvent.setup();
    setAuth(ADMIN_USER);
    renderDashboard();

    await waitFor(() => {
      expect(mockGet).toHaveBeenCalled();
    });

    const spawnBtn = screen.getByText(/Spawn/).closest('button')!;
    await user.click(spawnBtn);

    await waitFor(() => {
      expect(mockPost).toHaveBeenCalledWith('/api/v1/scaling/override', {
        action: 'spawn',
        count: 1,
        tier: 3,
      });
      expect(showToast.success).toHaveBeenCalledWith(
        expect.stringContaining('spawn')
      );
    });
  });

  it('liquidate button calls API with correct payload', async () => {
    vi.useRealTimers();
    const user = userEvent.setup();
    setAuth(ADMIN_USER);
    renderDashboard();

    await waitFor(() => {
      expect(mockGet).toHaveBeenCalled();
    });

    const liquidateBtn = screen.getByText(/Liquidate/).closest('button')!;
    await user.click(liquidateBtn);

    await waitFor(() => {
      expect(mockPost).toHaveBeenCalledWith('/api/v1/scaling/override', {
        action: 'liquidate',
        count: 1,
        tier: 3,
      });
      expect(showToast.success).toHaveBeenCalledWith(
        expect.stringContaining('liquidate')
      );
    });
  });
});

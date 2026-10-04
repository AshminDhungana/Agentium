import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import BudgetControl from '../BudgetControl';

// Mock api
const mockGet = vi.fn();
const mockPost = vi.fn();
vi.mock('@/services/api', () => ({
  api: {
    get: (...args: any[]) => mockGet(...args),
    post: (...args: any[]) => mockPost(...args),
  },
}));

// Mock authStore
vi.mock('@/store/authStore', () => ({
  useAuthStore: () => ({ user: { role: 'admin' } }),
}));

// Mock toast — inline to avoid hoisting issues with vi.mock
vi.mock('@/hooks/useToast', () => ({
  showToast: { success: vi.fn(), error: vi.fn() },
}));

import { showToast } from '@/hooks/useToast';
const mockShowToast = vi.mocked(showToast);

const baseBudget = {
  current_limits: { daily_token_limit: 100000, daily_cost_limit: 10.0 },
  usage: {
    tokens_used_today: 25000,
    tokens_remaining: 75000,
    cost_used_today_usd: 2.5,
    cost_remaining_usd: 7.5,
    cost_percentage_used: 25,
    cost_percentage_tokens: 25,
  },
  can_modify: true,
  optimizer_status: {
    idle_mode_active: false,
    time_since_last_activity_seconds: 120,
  },
};

function makeBudget(overrides: Record<string, any> = {}) {
  return {
    ...baseBudget,
    ...overrides,
    usage: { ...baseBudget.usage, ...(overrides.usage || {}) },
    optimizer_status: { ...baseBudget.optimizer_status, ...(overrides.optimizer_status || {}) },
    current_limits: { ...baseBudget.current_limits, ...(overrides.current_limits || {}) },
  };
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe('BudgetControl', () => {
  it('shows loading state before API resolves', () => {
    mockGet.mockReturnValue(new Promise(() => {})); // never resolves
    render(<BudgetControl />);
    expect(screen.getByText(/loading budget control/i)).toBeInTheDocument();
  });

  it('renders token and cost cards after data loads', async () => {
    mockGet.mockResolvedValue({ data: makeBudget() });
    render(<BudgetControl />);
    // "Token Limit" appears in both the stat card and the admin form label
    await waitFor(() => {
      expect(screen.getAllByText('Token Limit').length).toBeGreaterThanOrEqual(1);
    });
    expect(screen.getAllByText(/cost limit/i).length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText('100,000')).toBeInTheDocument();
    expect(screen.getByText('$10.00')).toBeInTheDocument();
  });

  it('shows idle mode banner when active', async () => {
    mockGet.mockResolvedValue({
      data: makeBudget({ optimizer_status: { idle_mode_active: true, time_since_last_activity_seconds: 300 } }),
    });
    render(<BudgetControl />);
    await waitFor(() => {
      expect(screen.getByText(/idle mode/i)).toBeInTheDocument();
    });
  });

  it('shows red banner when cost_percentage_used > 90', async () => {
    mockGet.mockResolvedValue({
      data: makeBudget({ usage: { cost_percentage_used: 95, cost_percentage_tokens: 95 } }),
    });
    render(<BudgetControl />);
    await waitFor(() => {
      expect(screen.getByText(/critical/i)).toBeInTheDocument();
    });
  });

  it('shows amber warning when cost_percentage_used > 75 and ≤ 90', async () => {
    mockGet.mockResolvedValue({
      data: makeBudget({ usage: { cost_percentage_used: 80, cost_percentage_tokens: 80 } }),
    });
    render(<BudgetControl />);
    await waitFor(() => {
      expect(screen.getByText(/warning/i)).toBeInTheDocument();
    });
  });

  it('shows admin form when can_modify is true', async () => {
    mockGet.mockResolvedValue({ data: makeBudget() });
    render(<BudgetControl />);
    await waitFor(() => {
      expect(screen.getByText('Update Budget Settings')).toBeInTheDocument();
    });
    expect(screen.getByLabelText('Token Limit')).toBeInTheDocument();
    expect(screen.getByLabelText('Cost Limit (USD)')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /update budget/i })).toBeInTheDocument();
  });

  it('shows read-only message when can_modify is false', async () => {
    mockGet.mockResolvedValue({ data: makeBudget({ can_modify: false }) });
    render(<BudgetControl />);
    await waitFor(() => {
      expect(screen.getByText(/only administrators/i)).toBeInTheDocument();
    });
    expect(screen.queryByText('Update Budget Settings')).not.toBeInTheDocument();
  });

  it('handles successful budget update', async () => {
    mockGet.mockResolvedValue({ data: makeBudget() });
    mockPost.mockResolvedValue({ data: { ok: true } });
    render(<BudgetControl />);
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /update budget/i })).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole('button', { name: /update budget/i }));

    await waitFor(() => {
      expect(mockPost).toHaveBeenCalledWith('/api/v1/admin/budget', {
        daily_token_limit: 100000,
        daily_cost_limit: 10.0,
      });
    });
    expect(mockShowToast.success).toHaveBeenCalledWith('Budget updated successfully!');
  });

  it('handles failed budget update with error toast and inline banner', async () => {
    mockGet.mockResolvedValue({ data: makeBudget() });
    mockPost.mockRejectedValue({ response: { data: { detail: 'Permission denied' } } });
    render(<BudgetControl />);
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /update budget/i })).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole('button', { name: /update budget/i }));

    await waitFor(() => {
      expect(screen.getByText('Permission denied')).toBeInTheDocument();
    });
    expect(mockShowToast.error).toHaveBeenCalledWith('Permission denied');
  });

  it('shows loading spinner in button during update', async () => {
    mockGet.mockResolvedValue({ data: makeBudget() });
    // Never-resolving post to keep the loading state active
    mockPost.mockReturnValue(new Promise(() => {}));
    render(<BudgetControl />);
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /update budget/i })).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole('button', { name: /update budget/i }));

    await waitFor(() => {
      expect(screen.getByText(/updating/i)).toBeInTheDocument();
    });
  });
});

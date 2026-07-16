import { render, screen } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
// Real module path used by the component is '@/services/admin'
vi.mock('@/services/admin', () => ({
  adminService: {
    getBudgetStatus: vi.fn().mockResolvedValue({ data: {} }),
    getBudgetHistory: vi.fn().mockResolvedValue({ data: [] }),
  },
}));
import { FinancialBurnDashboard } from './FinancialBurnDashboard';

describe('FinancialBurnDashboard', () => {
  it('renders in an accessible region', () => {
    render(<FinancialBurnDashboard />);
    expect(screen.getByRole('region', { name: /budget/i })).toBeInTheDocument();
  });
});

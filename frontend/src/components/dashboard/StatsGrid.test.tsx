import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { StatsGrid } from './StatsGrid';

const stats = { totalAgents: 10, activeAgents: 4, pendingTasks: 2, completedTasks: 8, failedTasks: 0, inProgressTasks: 1, successRate: 95 } as any;

describe('StatsGrid', () => {
  it('renders inside an accessible region', () => {
    render(<StatsGrid stats={stats} isLoading={false} />);
    expect(screen.getByRole('region', { name: 'System statistics' })).toBeInTheDocument();
    expect(screen.getByText('Active Agents')).toBeInTheDocument();
  });
});

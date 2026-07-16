import { render, screen } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { RecentTasks } from './RecentTasks';

describe('RecentTasks', () => {
  it('shows the shared empty state when there are no tasks', () => {
    render(<RecentTasks tasks={[]} isLoading={false} isError={false} onRetry={vi.fn()} />);
    expect(screen.getByText('No tasks yet')).toBeInTheDocument();
  });
  it('renders in an accessible region', () => {
    render(<RecentTasks tasks={[]} isLoading={false} isError={false} onRetry={vi.fn()} />);
    expect(screen.getByRole('region', { name: 'Recent tasks' })).toBeInTheDocument();
  });
});

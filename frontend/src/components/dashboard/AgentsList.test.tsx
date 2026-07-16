import { render, screen } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { AgentsList } from './AgentsList';

describe('AgentsList', () => {
  it('shows the shared empty state when no agents', () => {
    render(<AgentsList agents={[]} isLoading={false} isError={false} onRetry={vi.fn()} />);
    expect(screen.getByText('No active agents')).toBeInTheDocument();
  });
  it('renders in an accessible region', () => {
    render(<AgentsList agents={[]} isLoading={false} isError={false} onRetry={vi.fn()} />);
    expect(screen.getByRole('region', { name: 'Active agents' })).toBeInTheDocument();
  });
});

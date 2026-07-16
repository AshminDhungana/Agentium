import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { DashboardHeader } from './DashboardHeader';
import { useBackendStore } from '@/store/backendStore'; // use confirmed path

describe('DashboardHeader', () => {
  it('announces backend disconnect with an alert role', () => {
    useBackendStore.setState({ status: { status: 'disconnected' } } as any);
    render(<DashboardHeader />);
    expect(screen.getByRole('alert', { name: /backend/i })).toBeInTheDocument();
  });

  it('greets the user', () => {
    useBackendStore.setState({ status: { status: 'connected' } } as any);
    render(<DashboardHeader />);
    expect(screen.getByRole('heading', { level: 1 })).toBeInTheDocument();
  });
});

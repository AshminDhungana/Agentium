import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { DashboardSkeleton } from './DashboardSkeleton';

describe('DashboardSkeleton', () => {
  it('exposes a testid for the page gate', () => {
    render(<DashboardSkeleton />);
    expect(screen.getByTestId('dashboard-skeleton')).toBeInTheDocument();
  });
});

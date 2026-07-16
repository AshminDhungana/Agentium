import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { SystemHealth } from './SystemHealth';
import { useBackendStore } from '@/store/backendStore';

describe('SystemHealth', () => {
  it('shows the real constitution version from the store', () => {
    useBackendStore.setState({ status: { status: 'connected', constitutionVersion: 'v2.3.1' } } as any);
    render(<SystemHealth />);
    expect(screen.getByText('v2.3.1')).toBeInTheDocument();
    expect(screen.queryByText('v1.0.0')).not.toBeInTheDocument();
  });
});

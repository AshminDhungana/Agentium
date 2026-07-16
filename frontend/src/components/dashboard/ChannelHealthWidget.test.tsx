import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, it, expect, vi } from 'vitest';
import { ChannelHealthWidget } from './ChannelHealthWidget';
import { useBackendStore } from '@/store/backendStore';

describe('ChannelHealthWidget', () => {
  it('shows the shared empty state when no channels', () => {
    useBackendStore.setState({ channelMetrics: [], isLoadingChannelMetrics: false, fetchChannelMetrics: vi.fn() } as any);
    render(
      <MemoryRouter>
        <ChannelHealthWidget />
      </MemoryRouter>
    );
    expect(screen.getByText('No channels configured')).toBeInTheDocument();
  });
});

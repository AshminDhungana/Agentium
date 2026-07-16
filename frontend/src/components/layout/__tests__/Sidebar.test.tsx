import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, it, expect } from 'vitest';
import { Sidebar } from '../Sidebar';
import { NAV_GROUPS, SOVEREIGN_ITEM } from '../navConfig';
import { useWebSocketStore } from '@/store/websocketStore';

const noop = () => {};

function renderSidebar(props: Partial<React.ComponentProps<typeof Sidebar>> = {}) {
  return render(
    <MemoryRouter>
      <Sidebar
        groups={NAV_GROUPS}
        sovereignItem={SOVEREIGN_ITEM}
        collapsed={false}
        mobileOpen={false}
        onCloseMobile={noop}
        {...props}
      />
    </MemoryRouter>
  );
}

describe('Sidebar', () => {
  it('renders a labeled primary navigation landmark', () => {
    renderSidebar();
    expect(screen.getByRole('navigation', { name: /main navigation/i })).toBeInTheDocument();
  });

  it('renders every non-admin group label and item', () => {
    renderSidebar();
    expect(screen.getByText('Workspace')).toBeInTheDocument();
    expect(screen.getByText('Governance')).toBeInTheDocument();
    expect(screen.getByText('Integrations')).toBeInTheDocument();
    expect(screen.getByText('System')).toBeInTheDocument();
    expect(screen.getByText('Dashboard')).toBeInTheDocument();
    expect(screen.getByText('Sovereign Control')).toBeInTheDocument();
  });

  it('hides labels when collapsed and exposes them as tooltips', () => {
    renderSidebar({ collapsed: true });
    expect(screen.queryByText('Dashboard')).not.toBeInTheDocument();
    expect(screen.getByTitle('Dashboard')).toBeInTheDocument();
  });

  it('shows the unread badge on Command Interface', () => {
    useWebSocketStore.setState({ unreadCount: 3 });
    renderSidebar();
    expect(screen.getByText('3')).toBeInTheDocument();
  });

  it('marks the active item with aria-current', () => {
    renderSidebar();
    const link = screen.getByRole('link', { name: /dashboard/i });
    expect(link).toHaveAttribute('aria-current', 'page');
  });
});

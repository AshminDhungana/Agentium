import { render, screen, fireEvent } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { MainLayout } from '../MainLayout';
import { useAuthStore } from '@/store/authStore';

vi.mock('@/components/VoiceIndicator', () => ({ VoiceIndicator: () => null }));

let desktop = true;
beforeEach(() => {
  desktop = true;
  window.matchMedia = vi.fn().mockImplementation((q: string) => ({
    matches: desktop, media: q, onchange: null,
    addEventListener: vi.fn(), removeEventListener: vi.fn(),
    addListener: vi.fn(), removeListener: vi.fn(), dispatchEvent: vi.fn(),
  }));
  useAuthStore.setState({ user: { isSovereign: false, is_admin: false, username: 'tester', role: 'member' } });
  localStorage.clear();
});

function renderMain(path = '/') {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/" element={<MainLayout />}>
          <Route index element={<div>Dashboard page</div>} />
          <Route path="agents" element={<div>Agents page</div>} />
        </Route>
      </Routes>
    </MemoryRouter>
  );
}

describe('MainLayout', () => {
  it('renders the sidebar nav and a page title heading', () => {
    renderMain('/');
    expect(screen.getByRole('navigation', { name: /main navigation/i })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Dashboard' })).toBeInTheDocument();
    expect(screen.getByText('Dashboard page')).toBeInTheDocument();
  });

  it('collapses the sidebar and hides labels when the collapse toggle is clicked', () => {
    renderMain('/');
    // "Dashboard" texts when expanded: TopBar title (heading) + Sidebar nav label,
    // and the NavLink <a> wrapper (its text content is also "Dashboard") = 3.
    expect(screen.getAllByText('Dashboard')).toHaveLength(3);
    fireEvent.click(screen.getByRole('button', { name: /collapse sidebar/i }));
    // After collapse the Sidebar label is hidden (exposed as a tooltip instead);
    // the TopBar title and the page-load overlay label remain.
    expect(screen.getAllByText('Dashboard')).toHaveLength(2);
    expect(screen.getByTitle('Dashboard')).toBeInTheDocument();
    expect(localStorage.getItem('agentium:sidebar-collapsed')).toBe('true');
  });

  it('opens the mobile drawer from the hamburger and closes it on Escape', () => {
    desktop = false;
    renderMain('/');
    const hamburger = screen.getByRole('button', { name: /open navigation menu/i });
    fireEvent.click(hamburger);
    expect(screen.getByText('Dashboard page')).toBeInTheDocument();
    fireEvent.keyDown(window, { key: 'Escape' });
    expect(screen.getByRole('button', { name: /open navigation menu/i })).toBeInTheDocument();
  });
});

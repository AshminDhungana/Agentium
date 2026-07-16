import { render, screen } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { TopBar } from '../TopBar';

describe('TopBar', () => {
  it('shows the current page title as a heading', () => {
    render(<TopBar title="Agents" collapsed={false} onToggleCollapse={vi.fn()} onOpenMobile={vi.fn()} />);
    expect(screen.getByRole('heading', { name: 'Agents' })).toBeInTheDocument();
  });

  it('fires onOpenMobile from the mobile hamburger', () => {
    const onOpenMobile = vi.fn();
    render(<TopBar title="Dashboard" collapsed={false} onToggleCollapse={vi.fn()} onOpenMobile={onOpenMobile} />);
    screen.getByRole('button', { name: /open navigation menu/i }).click();
    expect(onOpenMobile).toHaveBeenCalled();
  });

  it('fires onToggleCollapse and reflects aria-pressed', () => {
    const onToggleCollapse = vi.fn();
    render(<TopBar title="Dashboard" collapsed={true} onToggleCollapse={onToggleCollapse} onOpenMobile={vi.fn()} />);
    const btn = screen.getByRole('button', { name: /expand sidebar/i });
    expect(btn).toHaveAttribute('aria-pressed', 'true');
    btn.click();
    expect(onToggleCollapse).toHaveBeenCalled();
  });
});

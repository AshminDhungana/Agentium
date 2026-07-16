import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { WidgetCard } from './WidgetCard';
import { Cpu } from 'lucide-react';

describe('WidgetCard', () => {
  it('renders an accessible region with title and icon', () => {
    render(<WidgetCard title="System Health" icon={Cpu}><p>body</p></WidgetCard>);
    expect(screen.getByRole('region', { name: 'System Health' })).toBeInTheDocument();
    expect(screen.getByText('body')).toBeInTheDocument();
  });

  it('renders the action slot', () => {
    render(<WidgetCard title="T" icon={Cpu} action={<button>Go</button>}><p>x</p></WidgetCard>);
    expect(screen.getByRole('button', { name: 'Go' })).toBeInTheDocument();
  });

  it('applies the contentClassName to the body', () => {
    const { container } = render(<WidgetCard title="T" icon={Cpu} contentClassName="p-4"><p>x</p></WidgetCard>);
    expect(container.querySelector('.p-4')).toBeInTheDocument();
  });
});

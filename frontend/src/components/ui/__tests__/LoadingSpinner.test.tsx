import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { LoadingSpinner } from '../LoadingSpinner';

// Helper: Lucide renders SVGs where className is an SVGAnimatedString,
// so we use getAttribute('class') instead of .className
function getClasses(el: Element): string {
  return el.getAttribute('class') ?? '';
}

describe('LoadingSpinner', () => {
  it('renders with default md size and aria-label', () => {
    const { container } = render(<LoadingSpinner />);
    const svg = container.querySelector('svg');
    expect(svg).not.toBeNull();
    expect(svg?.getAttribute('aria-label')).toBe('Loading');
    expect(getClasses(svg!)).toContain('w-6');
    expect(getClasses(svg!)).toContain('h-6');
  });

  it('applies animate-spin class', () => {
    const { container } = render(<LoadingSpinner />);
    const svg = container.querySelector('svg')!;
    expect(getClasses(svg)).toContain('animate-spin');
  });

  it.each([
    ['xs', 'w-3', 'h-3'],
    ['sm', 'w-4', 'h-4'],
    ['md', 'w-6', 'h-6'],
    ['lg', 'w-8', 'h-8'],
    ['xl', 'w-12', 'h-12'],
  ] as const)('applies correct classes for size="%s"', (size, expectedW, expectedH) => {
    const { container } = render(<LoadingSpinner size={size} />);
    const svg = container.querySelector('svg')!;
    expect(getClasses(svg)).toContain(expectedW);
    expect(getClasses(svg)).toContain(expectedH);
  });

  it('renders label text when provided', () => {
    render(<LoadingSpinner label="Loading agents..." />);
    expect(screen.getByText('Loading agents...')).toBeInTheDocument();
  });

  it('does not render label span when label is not provided', () => {
    const { container } = render(<LoadingSpinner />);
    expect(container.querySelector('span')).toBeNull();
  });

  it('merges custom className onto the icon', () => {
    const { container } = render(<LoadingSpinner className="text-red-500" />);
    const svg = container.querySelector('svg')!;
    expect(getClasses(svg)).toContain('text-red-500');
  });
});

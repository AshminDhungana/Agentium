import { describe, it, expect } from 'vitest';
import { render } from '@testing-library/react';
import { SignatureMark } from '../SignatureMark';

describe('SignatureMark', () => {
  it('renders an SVG with correct viewBox', () => {
    const { container } = render(<SignatureMark />);
    const svg = container.querySelector('svg');
    expect(svg).not.toBeNull();
    expect(svg?.getAttribute('viewBox')).toBe('0 0 1571 800');
  });

  it('uses currentColor for fill', () => {
    const { container } = render(<SignatureMark />);
    const svg = container.querySelector('svg')!;
    expect(svg.getAttribute('fill')).toBe('currentColor');
  });

  it('has aria-hidden="true" for decorative purposes', () => {
    const { container } = render(<SignatureMark />);
    const svg = container.querySelector('svg')!;
    expect(svg.getAttribute('aria-hidden')).toBe('true');
  });

  it('passes className to the SVG element', () => {
    const { container } = render(<SignatureMark className="w-44 text-red-500" />);
    const svg = container.querySelector('svg')!;
    expect(svg.className.baseVal).toContain('w-44');
    expect(svg.className.baseVal).toContain('text-red-500');
  });
});

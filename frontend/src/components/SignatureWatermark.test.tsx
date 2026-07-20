import { describe, it, expect, vi } from 'vitest';
import { render } from '@testing-library/react';
import { SignatureWatermark } from './SignatureWatermark';

vi.mock('framer-motion', async (importOriginal) => {
  const actual = await importOriginal<typeof import('framer-motion')>();
  return {
    ...actual,
    useReducedMotion: () => {
      if (typeof window === 'undefined' || !window.matchMedia) return false;
      return window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    },
  };
});

describe('SignatureWatermark', () => {
  it('renders the signature SVG', () => {
    const { container } = render(<SignatureWatermark className="absolute" />);
    const svg = container.querySelector('svg');
    expect(svg).not.toBeNull();
    expect(svg?.getAttribute('viewBox')).toBe('0 0 1571 800');
    expect(svg?.getAttribute('aria-hidden')).toBe('true');
  });

  it('animates a left-to-right clip-path reveal on mount (not reduced motion)', () => {
    const { container } = render(<SignatureWatermark className="absolute" />);
    const wrapper = container.firstElementChild as HTMLElement;
    expect(wrapper.style.clipPath).toContain('inset');
    expect(wrapper.style.opacity).toBe('0');
  });

  it('shows the signature instantly at full opacity under reduced motion', () => {
    const original = window.matchMedia;
    window.matchMedia = (query: string) =>
      ({
        matches: true,
        media: query,
        onchange: null,
        addEventListener: () => {},
        removeEventListener: () => {},
        addListener: () => {},
        removeListener: () => {},
        dispatchEvent: () => false,
      }) as unknown as MediaQueryList;
    const { container } = render(<SignatureWatermark className="absolute" />);
    window.matchMedia = original;
    const wrapper = container.firstElementChild as HTMLElement;
    expect(wrapper.style.clipPath).toBe('');
    expect(wrapper.className).toContain('opacity-30');
  });
});

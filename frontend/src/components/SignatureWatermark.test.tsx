import { describe, it, expect } from 'vitest';
import { render } from '@testing-library/react';
import { MotionConfig } from 'framer-motion';
import { SignatureWatermark } from './SignatureWatermark';

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
    const { container } = render(
      <MotionConfig reducedMotion="always">
        <SignatureWatermark className="absolute" />
      </MotionConfig>
    );
    const wrapper = container.firstElementChild as HTMLElement;
    expect(wrapper.style.clipPath).toBe('');
    expect(wrapper.className).toContain('opacity-30');
  });
});

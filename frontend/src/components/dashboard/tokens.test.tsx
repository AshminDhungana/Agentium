import { describe, it, expect } from 'vitest';
import tailwindConfig from '../../../tailwind.config.js';

describe('design tokens', () => {
  it('defines semantic color tokens bound to CSS variables', () => {
    const colors = (tailwindConfig.theme as any).extend.colors;
    expect(colors.canvas).toBe('var(--c-canvas)');
    expect(colors.panel).toBe('var(--c-panel)');
    expect(colors.hairline).toBe('var(--c-hairline)');
    expect(colors.subtle).toBe('var(--c-subtle)');
    expect(colors.brand.DEFAULT).toBe('var(--c-brand)');
    expect(colors.brand.soft).toBe('var(--c-brand-soft)');
    expect(colors.brand.fg).toBe('var(--c-brand-fg)');
  });
});

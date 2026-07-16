import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';

describe('design tokens', () => {
  it('exposes semantic color utilities', () => {
    const el = document.createElement('div');
    el.className = 'bg-canvas border-hairline text-brand bg-brand-soft';
    document.body.appendChild(el);
    const styles = getComputedStyle(el);
    expect(styles.backgroundColor).not.toBe('');
    expect(styles.borderColor).not.toBe('');
    expect(styles.color).not.toBe('');
  });
});

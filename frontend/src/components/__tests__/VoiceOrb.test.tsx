import { describe, it, expect, vi } from 'vitest';
import { render } from '@testing-library/react';
import { VoiceOrb } from '../VoiceOrb';

// Canvas getContext is not implemented in jsdom — suppress the error for this suite
beforeEach(() => {
  vi.spyOn(console, 'error').mockImplementation(() => {});
});
afterEach(() => {
  vi.restoreAllMocks();
});

describe('VoiceOrb', () => {
  it('renders a canvas element with correct dimensions', () => {
    const { container } = render(<VoiceOrb size={320} voiceState="idle" micLevel={0} />);
    const canvas = container.querySelector('canvas');
    expect(canvas).toBeTruthy();
    expect(canvas?.getAttribute('width')).toBe('320');
    expect(canvas?.getAttribute('height')).toBe('320');
  });
});

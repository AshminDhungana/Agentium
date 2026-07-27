import { render, screen } from '@testing-library/react';
import { VoiceControls } from '../VoiceControls';
import { vi } from 'vitest';

vi.mock('@/components/voice-bridge/hooks/useReducedMotion', () => ({
  useReducedMotion: () => ({ prefersReduced: false }),
}));

describe('VoiceControls glass pill', () => {
  test('renders glass pill background when glassPill prop is true', () => {
    render(<VoiceControls isConnected glassPill={true} onRecord={vi.fn()} onStop={vi.fn()} onMuteToggle={vi.fn()} onSettings={vi.fn()} />);
    const glassBg = screen.getByTestId('controls-glass-bg');
    expect(glassBg).toBeInTheDocument();
    expect(glassBg).toHaveClass('bg-[var(--c-glass-bg)]');
    expect(glassBg).toHaveClass('backdrop-blur-2xl');
    expect(glassBg).toHaveClass('rounded-3xl');
  });

  test('does not render glass pill background when glassPill is false', () => {
    render(<VoiceControls isConnected glassPill={false} onRecord={vi.fn()} onStop={vi.fn()} onMuteToggle={vi.fn()} onSettings={vi.fn()} />);
    expect(screen.queryByTestId('controls-glass-bg')).not.toBeInTheDocument();
  });

  test('renders all three control buttons', () => {
    render(<VoiceControls isConnected onRecord={vi.fn()} onStop={vi.fn()} onMuteToggle={vi.fn()} onSettings={vi.fn()} />);
    expect(screen.getByRole('button', { name: /mute microphone/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /start recording/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /open voice settings/i })).toBeInTheDocument();
  });
});
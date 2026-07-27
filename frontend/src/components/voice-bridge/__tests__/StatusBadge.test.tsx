import { render, screen } from '@testing-library/react';
import { StatusBadge } from '../StatusBadge';
import { vi } from 'vitest';

vi.mock('@/components/voice-bridge/hooks/useReducedMotion', () => ({
  useReducedMotion: () => ({ prefersReduced: false }),
}));

describe('StatusBadge', () => {
  test('renders connected state with green dot', () => {
    render(<StatusBadge status="connected" />);
    const badge = screen.getByText('Connected');
    expect(badge).toBeInTheDocument();
    expect(badge.closest('.glass-pill')).toBeInTheDocument();
    const dot = badge.previousElementSibling;
    expect(dot).toHaveStyle({ backgroundColor: 'var(--c-success)' });
  });

  test('renders connecting state with animated pulse', () => {
    render(<StatusBadge status="connecting" />);
    expect(screen.getByText('Connecting')).toBeInTheDocument();
    const dot = screen.getByText('Connecting').previousElementSibling;
    expect(dot).toHaveStyle({ backgroundColor: 'var(--c-warning)' });
  });

  test('animates pulse when voiceState is listening', () => {
    render(<StatusBadge status="connected" voiceState="listening" />);
    const dot = screen.getByText('Connected').previousElementSibling;
    expect(dot).toBeInTheDocument();
  });

  test('renders error state with red dot', () => {
    render(<StatusBadge status="error" />);
    expect(screen.getByText('Error')).toBeInTheDocument();
    const dot = screen.getByText('Error').previousElementSibling;
    expect(dot).toHaveStyle({ backgroundColor: 'var(--c-error)' });
  });

  test('renders reconnecting state with voice-listening color', () => {
    render(<StatusBadge status="reconnecting" />);
    expect(screen.getByText('Reconnecting')).toBeInTheDocument();
    const dot = screen.getByText('Reconnecting').previousElementSibling;
    expect(dot).toHaveStyle({ backgroundColor: 'var(--c-voice-listening)' });
  });

  test('renders disconnected state with muted color', () => {
    render(<StatusBadge status="disconnected" />);
    expect(screen.getByText('Disconnected')).toBeInTheDocument();
    const dot = screen.getByText('Disconnected').previousElementSibling;
    expect(dot).toHaveStyle({ backgroundColor: 'var(--color-text-muted)' });
  });
});
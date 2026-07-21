import { render, screen } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { VoiceIndicator } from '../../VoiceIndicator';
import { useAuthStore } from '@/store/authStore';

vi.mock('@/services/voiceBridge', () => ({
  voiceBridgeService: {
    status: 'offline',
    onStatusChange: vi.fn(() => () => {}),
    onStateChange: vi.fn(() => () => {}),
    connect: vi.fn(() => Promise.resolve()),
    disconnect: vi.fn(),
  },
}));

beforeEach(() => {
  useAuthStore.setState({
    user: { isAuthenticated: true, username: 'tester', role: 'member' } as never,
  });
});

describe('VoiceIndicator', () => {
  it('renders the mic button', () => {
    render(<VoiceIndicator />);
    expect(screen.getByRole('button', { name: 'Voice offline' })).toBeTruthy();
  });

  it('shows offline state when bridge is not connected', () => {
    render(<VoiceIndicator />);
    expect(screen.getByText('Voice offline')).toBeTruthy();
  });
});

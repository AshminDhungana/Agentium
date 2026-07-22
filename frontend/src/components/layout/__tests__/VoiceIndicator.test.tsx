import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { VoiceIndicator } from '../../VoiceIndicator';
import { useAuthStore } from '@/store/authStore';

vi.mock('@/services/voiceBridge', () => ({
  voiceBridgeService: {
    status: 'offline',
    onStatusChange: vi.fn(() => () => {}),
    onStateChange: vi.fn(() => () => {}),
    onErrorChange: vi.fn(() => () => {}),
    connect: vi.fn(() => Promise.resolve()),
    disconnect: vi.fn(),
    connectionError: null,
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

  it('shows offline state text when not iconOnly', () => {
    render(<VoiceIndicator />);
    expect(screen.getByText('Voice offline')).toBeTruthy();
  });

  it('shows chevron button when offline', () => {
    render(<VoiceIndicator />);
    expect(screen.getByLabelText('Voice options')).toBeTruthy();
  });

  it('opens dropdown panel on chevron click', () => {
    render(<VoiceIndicator />);
    fireEvent.click(screen.getByLabelText('Voice options'));
    expect(screen.getByRole('dialog', { name: 'Voice options' })).toBeTruthy();
  });
});

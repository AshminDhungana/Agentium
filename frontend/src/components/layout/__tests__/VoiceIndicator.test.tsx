import { render, screen } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { VoiceIndicator } from '../../VoiceIndicator';
import { useAuthStore } from '@/store/authStore';

// The notification only appears after an auto-connect attempt resolves to a
// non-connected status. Mock the singleton so status stays 'offline'.
vi.mock('@/services/voiceBridge', () => ({
  voiceBridgeService: {
    status: 'offline',
    onStatusChange: vi.fn(() => () => {}),
    connect: vi.fn(() => Promise.resolve()),
    disconnect: vi.fn(),
  },
}));

const REAL_UA = navigator.userAgent;
function setUserAgent(ua: string) {
  Object.defineProperty(navigator, 'userAgent', { value: ua, configurable: true });
}

beforeEach(() => {
  // Authenticated user triggers the auto-connect + notification flow.
  useAuthStore.setState({
    user: { isAuthenticated: true, username: 'tester', role: 'member' } as never,
  });
});

afterEach(() => {
  setUserAgent(REAL_UA);
  vi.clearAllMocks();
});

describe('VoiceIndicator install notification', () => {
  it('renders the notification as a direct child of document.body (portaled)', async () => {
    render(<VoiceIndicator />);
    const alert = await screen.findByRole('alert');
    expect(alert.parentElement).toBe(document.body);
  });

  it('shows the current Windows launcher command, not the legacy run-prompt.cmd', async () => {
    setUserAgent('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36');
    render(<VoiceIndicator />);
    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('bootstrap-voice.cmd');
    expect(alert).not.toHaveTextContent('run-prompt.cmd');
  });
});

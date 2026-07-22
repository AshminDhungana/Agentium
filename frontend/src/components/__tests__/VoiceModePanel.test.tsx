import { render, screen } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { VoiceModePanel } from '../VoiceModePanel';

vi.mock('@/services/voiceBridge', () => ({
  voiceBridgeService: {
    status: 'offline',
    onStatusChange: vi.fn(() => () => {}),
    onStateChange: vi.fn(() => () => {}),
    onTranscript: vi.fn(() => () => {}),
    connect: vi.fn(() => Promise.resolve()),
    disconnect: vi.fn(),
  },
}));

vi.mock('@/components/voice-bridge/VoiceOrb', () => ({
  VoiceOrb: vi.fn(() => <div data-testid="voice-orb" />),
}));

describe('VoiceModePanel', () => {
  it('renders the voice mode panel', () => {
    render(<VoiceModePanel onClose={vi.fn()} />);
    expect(screen.getByText('Voice Bridge Offline')).toBeTruthy();
  });

  it('renders the close button', () => {
    render(<VoiceModePanel onClose={vi.fn()} />);
    expect(screen.getByLabelText('Close voice mode')).toBeTruthy();
  });

  it('renders the voice orb', () => {
    render(<VoiceModePanel onClose={vi.fn()} />);
    expect(screen.getByTestId('voice-orb')).toBeTruthy();
  });

  it('renders the settings button', () => {
    render(<VoiceModePanel onClose={vi.fn()} />);
    expect(screen.getByText('Voice Settings')).toBeTruthy();
  });

  it('shows offline state when bridge is not connected', () => {
    render(<VoiceModePanel onClose={vi.fn()} />);
    expect(screen.getByText('Run the voice bridge to start speaking')).toBeTruthy();
  });
});

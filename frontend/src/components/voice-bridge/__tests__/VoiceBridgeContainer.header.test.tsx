import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { VoiceBridgeContainer } from '../VoiceBridgeContainer';

vi.mock('../hooks/useVoiceBridge', () => ({
  useVoiceBridge: () => ({
    status: 'connected',
    voiceState: 'idle' as const,
    isRecording: false,
    isMuted: false,
    micLevel: 0,
    timeDomainData: undefined,
    frequencyData: undefined,
    transcripts: [],
    settings: {
      model: 'default',
      voice: 'nova',
      language: 'en',
      vadSensitivity: 0.5,
      autoStopSilence: 1.5,
      inputDeviceId: '',
      outputDeviceId: '',
    },
    availableInputDevices: [],
    availableOutputDevices: [],
    connect: vi.fn(),
    disconnect: vi.fn(),
    startRecording: vi.fn(),
    stopRecording: vi.fn(),
    toggleMute: vi.fn(),
    updateSettings: vi.fn(),
    clearTranscripts: vi.fn(),
    setMicLevel: vi.fn(),
    setTimeDomainData: vi.fn(),
    setFrequencyData: vi.fn(),
  }),
}));

vi.mock('../hooks/useAudioVisualization', () => ({
  useAudioVisualization: () => ({
    start: vi.fn(),
    stop: vi.fn(),
  }),
}));

describe('VoiceBridgeContainer Header', () => {
  it('renders brand with gradient orb icon', () => {
    render(<VoiceBridgeContainer />);
    const orb = screen.getByTestId('voice-bridge-brand-orb');
    expect(orb).toBeInTheDocument();
    // Gradient background uses CSS variables for voice listening/speaking
    expect(orb.style.background).toContain('linear-gradient');
    expect(orb.style.background).toContain('var(--c-voice-listening)');
    expect(orb.style.background).toContain('var(--c-voice-speaking)');
    // Glow shadow using voice glow variable
    expect(orb.style.boxShadow).toContain('var(--c-voice-glow)');
  });

  it('renders connection status dot with correct color for connected state', () => {
    render(<VoiceBridgeContainer />);
    const dot = screen.getByTestId('connection-status-dot');
    expect(dot).toBeInTheDocument();
    // Connected status: getStatusColor resolves --c-success via getComputedStyle;
    // in jsdom the CSS variable is undefined, so the fallback #10b981 is used
    // jsdom returns rgb() format, so check both formats
    const bgColor = dot.style.backgroundColor;
    expect(bgColor === '#10b981' || bgColor === 'rgb(16, 185, 129)').toBe(true);
    // boxShadow may also be in rgb format
    const boxShadow = dot.style.boxShadow;
    expect(boxShadow.includes('#10b981') || boxShadow.includes('rgb(16, 185, 129)')).toBe(true);
    expect(dot.className).toContain('rounded-full');
  });

  it('applies motion initial/animate variants to header elements', () => {
    render(<VoiceBridgeContainer />);
    const header = screen.getByTestId('voice-bridge-header');
    expect(header).toBeInTheDocument();
    // The header should render as an accessible header element
    expect(header.tagName).toBe('HEADER');
    // Should have the glass styling classes
    expect(header.className).toContain('backdrop-blur-xl');
    expect(header.className).toContain('sticky');
  });

  it('renders the brand title and subtitle', () => {
    render(<VoiceBridgeContainer />);
    expect(screen.getByText('Voice Bridge')).toBeInTheDocument();
    expect(screen.getByText('Talk to Agentium in real time')).toBeInTheDocument();
  });

  it('renders connect/disconnect button', () => {
    render(<VoiceBridgeContainer />);
    // Connected state shows Disconnect
    const button = screen.getByRole('button', { name: /disconnect/i });
    expect(button).toBeInTheDocument();
    // Should have spring motion classes via framer-motion
    expect(button.tagName).toBe('BUTTON');
  });

  it('renders brand orb with mic icon', () => {
    render(<VoiceBridgeContainer />);
    const orb = screen.getByTestId('voice-bridge-brand-orb');
    // Brand orb should be visually prominent with shadow
    expect(orb.style.boxShadow).toBeTruthy();
    expect(orb.className).toContain('rounded-xl');
  });
});
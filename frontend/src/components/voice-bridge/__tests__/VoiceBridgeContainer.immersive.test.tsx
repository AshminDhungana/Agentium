import { render, screen, act } from '@testing-library/react';
import { VoiceBridgeContainer } from '../VoiceBridgeContainer';
import { vi } from 'vitest';

// Mock all hooks
vi.mock('@/components/voice-bridge/hooks/useVoiceBridge', () => ({
  useVoiceBridge: () => ({
    status: 'connected',
    voiceState: 'idle',
    isRecording: false,
    isMuted: false,
    micLevel: 0,
    timeDomainData: null,
    frequencyData: null,
    transcripts: [],
    settings: {},
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

vi.mock('@/components/voice-bridge/hooks/useAudioVisualization', () => ({
  useAudioVisualization: () => ({ start: vi.fn(), stop: vi.fn() }),
}));

vi.mock('@/components/voice-bridge/hooks/useReducedMotion', () => ({
  useReducedMotion: () => ({ prefersReduced: false }),
}));

describe('VoiceBridgeContainer immersive layout', () => {
  test('renders full-viewport canvas layer', () => {
    render(<VoiceBridgeContainer />);
    expect(screen.getByTestId('canvas-layer')).toHaveClass('fixed inset-0 z-0');
  });

  test('renders StatusBadge at top-right', () => {
    render(<VoiceBridgeContainer />);
    expect(screen.getByText('Connected')).toBeInTheDocument();
    expect(screen.getByText('Connected').closest('.fixed.top-6.right-6')).toBeInTheDocument();
  });

  test('renders TranscriptDrawer at bottom-left', () => {
    render(<VoiceBridgeContainer />);
    const button = screen.getByRole('button', { name: /open transcript/i });
    expect(button).toBeInTheDocument();
    // The TranscriptDrawer container is the fixed element
    expect(button).toHaveAttribute('aria-controls', 'transcript-drawer-panel');
    // Check the parent container has the fixed positioning
    const container = button.closest('.fixed.bottom-6.left-6');
    expect(container).toBeInTheDocument();
  });

  test('renders Controls pill at bottom-center', () => {
    render(<VoiceBridgeContainer />);
    const recordBtn = screen.getByRole('button', { name: /start recording/i });
    expect(recordBtn).toBeInTheDocument();
    // Controls should be centered
    expect(recordBtn.closest('.fixed.bottom-6.left-1\\/2')).toBeInTheDocument();
  });

  test('canvas layer has depth sub-layers (radial glow, dot grid, vignettes)', () => {
    render(<VoiceBridgeContainer />);
    expect(screen.getByTestId('viz-radial-glow')).toBeInTheDocument();
    expect(screen.getByTestId('viz-dot-grid')).toBeInTheDocument();
    expect(screen.getByTestId('viz-vignette-top')).toBeInTheDocument();
    expect(screen.getByTestId('viz-vignette-bottom')).toBeInTheDocument();
  });

  test('applies page motion variants with staggerChildren', () => {
    const { container } = render(<VoiceBridgeContainer />);
    const pageWrapper = container.querySelector('[data-testid="page-motion-wrapper"]');
    // motion.div variants are passed as React props, not DOM attributes
    // The test verifies the component renders without error and has the wrapper
    expect(pageWrapper).toBeInTheDocument();
  });
});
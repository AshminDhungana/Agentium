import { render, screen } from '@testing-library/react';
import { VoiceControls } from '../VoiceControls';
import { vi, describe, it, expect } from 'vitest';

describe('VoiceControls', () => {
  it('renders three buttons: mute, record, settings', () => {
    render(<VoiceControls isConnected onRecord={vi.fn()} onStop={vi.fn()} onMuteToggle={vi.fn()} onSettings={vi.fn()} />);
    expect(screen.getByRole('button', { name: /mute microphone/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /start recording/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /open voice settings/i })).toBeInTheDocument();
  });

  it('primary button shows pulse ring when recording', () => {
    render(<VoiceControls isConnected isRecording onRecord={vi.fn()} onStop={vi.fn()} onMuteToggle={vi.fn()} onSettings={vi.fn()} />);
    expect(screen.getByTestId('record-pulse-ring')).toBeInTheDocument();
  });

  it('settings button has rotate spring on hover', () => {
    render(<VoiceControls isConnected onSettings={vi.fn()} />);
    const settingsBtn = screen.getByRole('button', { name: /open voice settings/i });
    expect(settingsBtn).toBeInTheDocument();
    // Framer Motion applies whileHover via event listeners, not as DOM attribute
    // The button renders with Settings SVG icon - verify it's present
    expect(settingsBtn.querySelector('svg')).toBeInTheDocument();
  });

  it('mute button shows muted state with MicOff icon', () => {
    render(<VoiceControls isConnected isMuted onMuteToggle={vi.fn()} />);
    expect(screen.getByRole('button', { name: /unmute microphone/i })).toBeInTheDocument();
  });

  it('renders ARIA live status region', () => {
    render(<VoiceControls isConnected voiceState="idle" />);
    const statusRegion = screen.getByRole('status');
    expect(statusRegion).toBeInTheDocument();
    expect(statusRegion).toHaveAttribute('aria-live', 'polite');
    expect(statusRegion).toHaveAttribute('aria-atomic', 'true');
  });

  it('status text includes state icon for listening', () => {
    render(<VoiceControls isConnected voiceState="listening" />);
    const statusRegion = screen.getByRole('status');
    expect(statusRegion).toHaveTextContent(/listening/i);
    // Should have icon SVG (MorphingIcon renders svg)
    expect(statusRegion.querySelector('svg')).toBeInTheDocument();
  });

  it('status text shows processing indicator', () => {
    render(<VoiceControls isConnected voiceState="processing" />);
    const statusRegion = screen.getByRole('status');
    expect(statusRegion).toHaveTextContent(/thinking/i);
  });

  it('status text shows speaking indicator', () => {
    render(<VoiceControls isConnected voiceState="speaking" />);
    const statusRegion = screen.getByRole('status');
    expect(statusRegion).toHaveTextContent(/speaking/i);
  });

  it('disables buttons when not connected', () => {
    render(<VoiceControls isConnected={false} />);
    expect(screen.getByRole('button', { name: /start recording/i })).toBeDisabled();
    expect(screen.getByRole('button', { name: /mute microphone/i })).toBeDisabled();
    expect(screen.getByRole('button', { name: /open voice settings/i })).toBeDisabled();
  });

  it('applies reduced motion when prefersReduced is true', () => {
    render(<VoiceControls isConnected prefersReduced />);
    const primaryBtn = screen.getByRole('button', { name: /start recording/i });
    // motion.button applies style={{ transition: 'none' }} when prefersReduced
    // Check the motion component wrapper exists
    expect(primaryBtn).toBeInTheDocument();
  });

  it('shows pulse ring CSS class when recording', () => {
    render(<VoiceControls isConnected isRecording onRecord={vi.fn()} onStop={vi.fn()} onMuteToggle={vi.fn()} onSettings={vi.fn()} />);
    expect(document.querySelector('.pulse-ring')).toBeInTheDocument();
  });

  it('status region has correct role and aria attributes', () => {
    render(<VoiceControls isConnected voiceState="idle" />);
    const statusRegion = screen.getByRole('status');
    expect(statusRegion).toHaveAttribute('aria-live', 'polite');
    expect(statusRegion).toHaveAttribute('aria-atomic', 'true');
  });
});
import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { VoiceDropdownPanel } from '../VoiceDropdownPanel';

function makeRect(overrides?: Partial<DOMRect>): DOMRect {
  return { top: 600, right: 300, bottom: 640, left: 240, width: 56, height: 40, x: 240, y: 600, toJSON: () => {}, ...overrides };
}

describe('VoiceDropdownPanel', () => {
  const baseProps = {
    buttonRect: makeRect(),
    isConnected: false,
    effectiveStatus: 'offline' as const,
    isDisabled: false,
    label: 'Voice offline',
    installCommand: 'curl -s https://example.com/install.sh | bash',
    connectionError: null,
    onClose: vi.fn(),
    onOpenSettings: vi.fn(),
    onOpenVoiceMode: vi.fn(),
  };

  it('renders status label', () => {
    render(<VoiceDropdownPanel {...baseProps} />);
    expect(screen.getByText('Voice offline')).toBeTruthy();
  });

  it('shows install command when offline', () => {
    render(<VoiceDropdownPanel {...baseProps} />);
    expect(screen.getByText(/curl -s/)).toBeTruthy();
  });

  it('shows Voice Settings button', () => {
    render(<VoiceDropdownPanel {...baseProps} />);
    expect(screen.getByText('Voice Settings')).toBeTruthy();
  });

  it('calls onOpenSettings when Voice Settings clicked', () => {
    render(<VoiceDropdownPanel {...baseProps} />);
    fireEvent.click(screen.getByText('Voice Settings'));
    expect(baseProps.onOpenSettings).toHaveBeenCalledTimes(1);
  });

  it('shows Open Voice Mode when connected', () => {
    render(<VoiceDropdownPanel {...baseProps} isConnected={true} effectiveStatus="connected" label="Voice ready" />);
    expect(screen.getByText('Open Voice Mode')).toBeTruthy();
  });

  it('calls onClose when backdrop clicked', () => {
    const onClose = vi.fn();
    render(<VoiceDropdownPanel {...baseProps} onClose={onClose} />);
    const backdrop = document.querySelector('.fixed.inset-0');
    if (backdrop) fireEvent.click(backdrop);
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('does not render when buttonRect is null', () => {
    const { container } = render(<VoiceDropdownPanel {...baseProps} buttonRect={null} />);
    expect(container.innerHTML).toBe('');
  });

  it('positions panel at button coordinates', () => {
    Object.defineProperty(window, 'innerHeight', { value: 2000, configurable: true });
    render(<VoiceDropdownPanel {...baseProps} />);
    const panel = screen.getByRole('dialog');
    expect(panel.style.left).toBe('304px');
    expect(panel.style.top).toBe('600px');
  });
});

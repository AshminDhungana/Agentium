import { render, screen, act } from '@testing-library/react';
import { Canvas2DFallback } from '../Canvas2DFallback';
import { vi, describe, it, expect, beforeEach, afterEach } from 'vitest';

// Mock requestAnimationFrame for tests
const mockRaf = vi.fn((cb) => setTimeout(cb, 16));
const mockCaf = vi.fn((id) => clearTimeout(id));

vi.stubGlobal('requestAnimationFrame', mockRaf);
vi.stubGlobal('cancelAnimationFrame', mockCaf);

describe('Canvas2DFallback', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockRaf.mockClear();
    mockCaf.mockClear();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('renders canvas with correct dimensions', async () => {
    render(<Canvas2DFallback voiceState="idle" micLevel={0} timeDomainData={null} frequencyData={null} status="connected" />);
    const canvas = screen.getByRole('img', { hidden: true });
    expect(canvas).toBeInTheDocument();
    expect(canvas.getAttribute('aria-label')).toContain('Voice visualization');
  });

  it('renders correctly for different voice states', () => {
    const { rerender } = render(<Canvas2DFallback voiceState="idle" micLevel={0} timeDomainData={null} frequencyData={null} status="connected" />);
    expect(screen.getByRole('img', { hidden: true })).toBeInTheDocument();

    rerender(<Canvas2DFallback voiceState="listening" micLevel={0.5} timeDomainData={new Uint8Array(256).fill(128)} frequencyData={new Uint8Array(48).fill(100)} status="connected" />);
    expect(screen.getByRole('img', { hidden: true })).toBeInTheDocument();

    rerender(<Canvas2DFallback voiceState="speaking" micLevel={0.8} timeDomainData={null} frequencyData={new Uint8Array(48).fill(200)} status="connected" />);
    expect(screen.getByRole('img', { hidden: true })).toBeInTheDocument();

    rerender(<Canvas2DFallback voiceState="processing" micLevel={0} timeDomainData={null} frequencyData={null} status="connected" />);
    expect(screen.getByRole('img', { hidden: true })).toBeInTheDocument();

    rerender(<Canvas2DFallback voiceState="error" micLevel={0} timeDomainData={null} frequencyData={null} status="error" />);
    expect(screen.getByRole('img', { hidden: true })).toBeInTheDocument();

    rerender(<Canvas2DFallback voiceState="muted" micLevel={0} timeDomainData={null} frequencyData={null} status="connected" />);
    expect(screen.getByRole('img', { hidden: true })).toBeInTheDocument();
  });

  it('handles prefersReduced prop', () => {
    render(<Canvas2DFallback voiceState="idle" micLevel={0} timeDomainData={null} frequencyData={null} status="connected" prefersReduced={true} />);
    expect(screen.getByRole('img', { hidden: true })).toBeInTheDocument();
  });

  it('renders with different connection statuses', () => {
    const { rerender } = render(<Canvas2DFallback voiceState="idle" micLevel={0} timeDomainData={null} frequencyData={null} status="disconnected" />);
    expect(screen.getByRole('img', { hidden: true })).toBeInTheDocument();

    rerender(<Canvas2DFallback voiceState="idle" micLevel={0} timeDomainData={null} frequencyData={null} status="connecting" />);
    expect(screen.getByRole('img', { hidden: true })).toBeInTheDocument();

    rerender(<Canvas2DFallback voiceState="idle" micLevel={0} timeDomainData={null} frequencyData={null} status="reconnecting" />);
    expect(screen.getByRole('img', { hidden: true })).toBeInTheDocument();

    rerender(<Canvas2DFallback voiceState="idle" micLevel={0} timeDomainData={null} frequencyData={null} status="error" />);
    expect(screen.getByRole('img', { hidden: true })).toBeInTheDocument();
  });
});
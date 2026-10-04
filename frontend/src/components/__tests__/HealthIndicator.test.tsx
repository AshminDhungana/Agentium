import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { HealthIndicator } from '../HealthIndicator';

// Mock the backend store
const mockStartPolling = vi.fn();
const mockStopPolling = vi.fn();

vi.mock('@/store/backendStore', () => ({
  useBackendStore: () => ({
    status: { status: 'connected' },
    startPolling: mockStartPolling,
    stopPolling: mockStopPolling,
  }),
}));

beforeEach(() => {
  vi.clearAllMocks();
});

describe('HealthIndicator', () => {
  it('renders green dot for status="connected"', () => {
    const { container } = render(<HealthIndicator status="connected" />);
    const dot = container.querySelector('[role="img"]')!;
    expect(dot.className).toContain('bg-green-500');
    expect(dot.getAttribute('aria-label')).toBe('Connected');
  });

  it('renders green dot for status="healthy"', () => {
    const { container } = render(<HealthIndicator status="healthy" />);
    const dot = container.querySelector('[role="img"]')!;
    expect(dot.className).toContain('bg-green-500');
    expect(dot.getAttribute('aria-label')).toBe('Healthy');
  });

  it('renders yellow pulsing dot for status="connecting"', () => {
    const { container } = render(<HealthIndicator status="connecting" />);
    const dot = container.querySelector('[role="img"]')!;
    expect(dot.className).toContain('bg-yellow-500');
    expect(dot.className).toContain('animate-pulse');
  });

  it('renders red dot for status="disconnected"', () => {
    const { container } = render(<HealthIndicator status="disconnected" />);
    const dot = container.querySelector('[role="img"]')!;
    expect(dot.className).toContain('bg-red-500');
    expect(dot.getAttribute('aria-label')).toBe('Disconnected');
  });

  it('renders red dot for status="critical"', () => {
    const { container } = render(<HealthIndicator status="critical" />);
    const dot = container.querySelector('[role="img"]')!;
    expect(dot.className).toContain('bg-red-500');
  });

  it('renders yellow dot (no pulse) for status="warning"', () => {
    const { container } = render(<HealthIndicator status="warning" />);
    const dot = container.querySelector('[role="img"]')!;
    expect(dot.className).toContain('bg-yellow-500');
    expect(dot.className).not.toContain('animate-pulse');
  });

  it('uses custom label for aria-label and tooltip', () => {
    render(<HealthIndicator status="connected" label="Backend OK" />);
    const dot = screen.getByRole('img');
    expect(dot.getAttribute('aria-label')).toBe('Backend OK');
  });

  it.each([
    ['sm', 'w-2', 'h-2'],
    ['md', 'w-3', 'h-3'],
    ['lg', 'w-4', 'h-4'],
  ] as const)('applies correct size classes for size="%s"', (size, expectedW, expectedH) => {
    const { container } = render(<HealthIndicator status="connected" size={size} />);
    const dot = container.querySelector('[role="img"]')!;
    expect(dot.className).toContain(expectedW);
    expect(dot.className).toContain(expectedH);
  });

  it('does NOT start polling when status prop is provided', () => {
    render(<HealthIndicator status="connected" />);
    expect(mockStartPolling).not.toHaveBeenCalled();
  });

  it('starts polling when no status prop is provided (uses backend store)', () => {
    render(<HealthIndicator />);
    expect(mockStartPolling).toHaveBeenCalled();
  });
});

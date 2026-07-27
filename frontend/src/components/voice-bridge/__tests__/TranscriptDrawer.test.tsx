import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { TranscriptDrawer } from '../TranscriptDrawer';
import { vi } from 'vitest';

vi.mock('@/components/voice-bridge/hooks/useReducedMotion', () => ({
  useReducedMotion: () => ({ prefersReduced: false }),
}));

vi.mock('@/components/voice-bridge/hooks/useBreakpoint', () => ({
  useBreakpoint: () => 'desktop-lg',
}));

vi.mock('@/components/dashboard/WidgetCard', () => ({
  WidgetCard: ({ children, className, ...props }: any) => (
    <section className={className} {...props} data-testid="widget-card">
      {children}
    </section>
  ),
}));

vi.mock('@/components/voice-bridge/TranscriptDisplay', () => ({
  TranscriptDisplay: ({ transcripts, ...props }: any) => (
    <div data-testid="transcript-display" {...props}>
      {transcripts?.map((t: any) => (
        <div key={t.id} data-testid="transcript-entry">
          {t.text}
        </div>
      ))}
    </div>
  ),
}));

describe('TranscriptDrawer', () => {
  const mockTranscripts = [
    { id: '1', speaker: 'user' as const, text: 'Hello', timestamp: new Date(), isStreaming: false },
    { id: '2', speaker: 'agent' as const, text: 'Hi there!', timestamp: new Date(), isStreaming: false },
  ];

  test('renders collapsed handle button when closed', () => {
    render(<TranscriptDrawer transcripts={mockTranscripts} />);
    const button = screen.getByRole('button', { name: /open transcript/i });
    expect(button).toBeInTheDocument();
    expect(button).toHaveClass('glass-pill');
    expect(screen.queryByRole('region', { name: /conversation transcript/i })).not.toBeInTheDocument();
  });

  test('expands panel on click', async () => {
    render(<TranscriptDrawer transcripts={mockTranscripts} />);
    const button = screen.getByRole('button', { name: /open transcript/i });
    fireEvent.click(button);
    const panel = await screen.findByRole('region', { name: /conversation transcript/i });
    expect(panel).toBeInTheDocument();
    // Panel should have responsive width (384px for desktop-lg)
    expect(panel).toHaveStyle({ width: '384px' });
  });

  test('collapses panel on second click', async () => {
    render(<TranscriptDrawer transcripts={mockTranscripts} />);
    const button = screen.getByRole('button', { name: /open transcript/i });
    fireEvent.click(button);
    await screen.findByRole('region', { name: /conversation transcript/i });
    fireEvent.click(button);
    await screen.findByRole('button', { name: /open transcript/i }); // wait for toggle back
    await waitFor(() => {
      expect(screen.queryByRole('region', { name: /conversation transcript/i })).not.toBeInTheDocument();
    });
  });

  test('shows transcript content when expanded', async () => {
    render(<TranscriptDrawer transcripts={mockTranscripts} />);
    const button = screen.getByRole('button', { name: /open transcript/i });
    fireEvent.click(button);
    await screen.findByText('Hello');
    expect(screen.getByText('Hi there!')).toBeInTheDocument();
  });
});
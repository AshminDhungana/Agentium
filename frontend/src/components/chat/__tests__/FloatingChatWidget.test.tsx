import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import { FloatingChatWidget } from '@/components/chat';
import { useChatStore } from '@/store/chatStore';
import { useWebSocketStore } from '@/store/websocketStore';
import { useAuthStore } from '@/store/authStore';
import { voiceBridgeService } from '@/services/voiceBridge';

vi.mock('@/store/chatStore');
vi.mock('@/store/websocketStore', () => ({
  useWebSocketStore: vi.fn().mockImplementation((selector: (state: any) => any) => selector({
    unreadCount: 0,
    connectionPhase: 'active',
  })),
}));
vi.mock('@/store/authStore');
vi.mock('@/services/voiceBridge', () => ({
  voiceBridgeService: {
    status: 'connected',
    voiceMode: 'system',
    setVoiceMode: vi.fn(),
    onStatusChange: vi.fn(() => vi.fn()),
    onInteraction: vi.fn(() => vi.fn()),
    onStateChange: vi.fn(() => vi.fn()),
    onTranscript: vi.fn(() => vi.fn()),
    connect: vi.fn().mockResolvedValue(undefined),
    disconnect: vi.fn(),
  },
}));

const mockUseChatStore = useChatStore as vi.Mock;
const mockUseAuthStore = useAuthStore as vi.Mock;

beforeEach(() => {
  mockUseChatStore.mockImplementation((selector: (state: any) => any) => selector({ messages: [], setMessages: vi.fn() }));
  mockUseAuthStore.mockImplementation((selector: (state: any) => any) => selector({ user: { isAuthenticated: true } }));
  vi.clearAllMocks();
});

describe('FloatingChatWidget', () => {
  test('renders collapsed dot when not hidden', () => {
    render(<FloatingChatWidget hidden={false} />);
    const dot = screen.getByRole('button', { name: /open agentium chat/i });
    expect(dot).toBeInTheDocument();
    // Component uses inline Tailwind classes, not floating-chat-collapsed CSS class
    expect(dot).toHaveClass('fixed');
    expect(dot).toHaveClass('h-3');
    expect(dot).toHaveClass('w-3');
    expect(dot).toHaveClass('rounded-full');
    expect(dot).toHaveClass('bg-[var(--color-primary)]');
  });

  test('hidden when hidden prop is true', () => {
    render(<FloatingChatWidget hidden={true} />);
    expect(screen.queryByRole('button', { name: /open agentium chat/i })).not.toBeInTheDocument();
  });

  test('renders button regardless of auth (auth handled by parent via hidden prop)', () => {
    mockUseAuthStore.mockImplementation((selector: (state: any) => any) => selector({ user: null }));
    render(<FloatingChatWidget hidden={false} />);
    // The component itself doesn't check auth - it relies on parent to pass hidden={true} when unauthenticated
    // So with hidden={false}, the button renders even if user is null
    const dot = screen.queryByRole('button', { name: /open agentium chat/i });
    expect(dot).toBeInTheDocument();
  });

  test('hover dot -> hovered icon (expanded button state)', async () => {
    render(<FloatingChatWidget hidden={false} />);
    const dot = screen.getByRole('button', { name: /open agentium chat/i });
    expect(dot).toBeInTheDocument();
    expect(dot).toHaveClass('h-3');
    expect(dot).toHaveClass('w-3');

    fireEvent.mouseEnter(dot);
    await waitFor(() => {
      // After hover, state changes to 'hovered' which renders a larger button (h-14 w-14)
      const hoveredBtn = screen.getByRole('button', { name: /open agentium chat/i });
      expect(hoveredBtn).toHaveClass('h-14');
      expect(hoveredBtn).toHaveClass('w-14');
    });
  });
});
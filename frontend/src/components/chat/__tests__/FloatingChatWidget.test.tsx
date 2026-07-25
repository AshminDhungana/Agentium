import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { FloatingChatWidget } from '@/components/chat';
import { useChatStore } from '@/store/chatStore';
import { useWebSocketStore } from '@/store/websocketStore';
import { useAuthStore } from '@/store/authStore';
import { useLocation } from 'react-router-dom';
import { voiceBridgeService } from '@/services/voiceBridge';

vi.mock('@/store/chatStore');
vi.mock('@/store/websocketStore', () => ({
  useWebSocketStore: vi.fn().mockImplementation((selector: (state: any) => any) => selector({ 
    unreadCount: 0,
    connectionPhase: 'active',
  })),
}));
vi.mock('@/store/authStore');
vi.mock('react-router-dom', () => ({
  ...vi.importActual('react-router-dom'),
  useLocation: vi.fn(),
}));
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
const mockUseLocation = useLocation as vi.Mock;

beforeEach(() => {
  mockUseChatStore.mockImplementation((selector: (state: any) => any) => selector({ messages: [], setMessages: vi.fn() }));
  mockUseAuthStore.mockImplementation((selector: (state: any) => any) => selector({ user: { isAuthenticated: true } }));
  mockUseLocation.mockReturnValue({ pathname: '/dashboard' });
  vi.clearAllMocks();
});

describe('FloatingChatWidget', () => {
  test('renders collapsed dot when not on /chat', () => {
    render(<FloatingChatWidget />);
    const dot = screen.getByRole('button', { name: /open agentium chat/i });
    expect(dot).toBeInTheDocument();
    expect(dot).toHaveClass('floating-chat-collapsed');
  });

  test('hidden on /chat route', () => {
    mockUseLocation.mockReturnValue({ pathname: '/chat' });
    render(<FloatingChatWidget />);
    expect(screen.queryByRole('button', { name: /open agentium chat/i })).not.toBeInTheDocument();
  });

  test('hidden when not authenticated', () => {
    mockUseAuthStore.mockImplementation((selector: (state: any) => any) => selector({ user: null }));
    render(<FloatingChatWidget />);
    expect(screen.queryByRole('button', { name: /open agentium chat/i })).not.toBeInTheDocument();
  });

  test('hover dot -> hovered icon', async () => {
    render(<FloatingChatWidget />);
    const dot = screen.getByRole('button', { name: /open agentium chat/i });
    expect(dot).toHaveClass('floating-chat-collapsed');
    fireEvent.mouseEnter(dot);
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /open agentium chat/i })).toHaveClass('floating-chat-hovered');
    });
  });
});
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { useWebSocketStore } from '../websocketStore';
import { showToast } from '@/hooks/useToast';

vi.mock('@/hooks/useToast', () => ({
  showToast: {
    success: vi.fn(),
    error: vi.fn(),
    warning: vi.fn(),
    info: vi.fn(),
    dismiss: vi.fn(),
  },
}));

// Mock WebSocket
class FakeWS {
  static readonly OPEN = 1;
  static readonly CONNECTING = 0;
  static readonly CLOSED = 3;
  readyState = FakeWS.OPEN;
  send = vi.fn();
  close = vi.fn();
  onopen: any;
  onclose: any;
  onerror: any;
  onmessage: any;
  constructor(public url: string) {}
}
vi.stubGlobal('WebSocket', FakeWS as any);

describe('13.2 WebSocket Event Types in websocketStore', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.setItem('access_token', 'test-token-mock');
    useWebSocketStore.setState({
      connectionPhase: 'active',
      unreadCount: 0,
      messageHistory: [],
      toolCount: 0,
      toolNames: [],
    });
  });

  afterEach(() => {
    localStorage.clear();
  });

  it('13.2.6: system_alert triggers toast error for critical severity', () => {
    useWebSocketStore.getState()._openSocket();
    const ws = useWebSocketStore.getState()._ws as any;
    expect(ws).toBeTruthy();
    expect(typeof ws.onmessage).toBe('function');

    const alertEvent = {
      data: JSON.stringify({
        type: 'system_alert',
        message: 'Database storage quota at 95%',
        severity: 'critical',
        timestamp: new Date().toISOString(),
      }),
    };

    ws.onmessage(alertEvent);

    expect(showToast.error).toHaveBeenCalledWith('🚨 Database storage quota at 95%');
    expect(useWebSocketStore.getState().lastMessage?.type).toBe('system_alert');
  });

  it('13.2.6: system_alert triggers toast warning for warning severity', () => {
    useWebSocketStore.getState()._openSocket();
    const ws = useWebSocketStore.getState()._ws as any;

    const alertEvent = {
      data: JSON.stringify({
        type: 'system_alert',
        message: 'High CPU utilization',
        severity: 'warning',
        timestamp: new Date().toISOString(),
      }),
    };

    ws.onmessage(alertEvent);

    expect(showToast.warning).toHaveBeenCalledWith('⚠️ High CPU utilization');
  });

  it('13.2.8: tool_execution updates toolCount and toolNames in store', () => {
    useWebSocketStore.getState()._openSocket();
    const ws = useWebSocketStore.getState()._ws as any;

    const toolEvent = {
      data: JSON.stringify({
        type: 'tool_execution',
        tool_name: 'web_search',
        tool_names: ['web_search', 'fetch_url'],
        tool_count: 2,
        status: 'in_progress',
        timestamp: new Date().toISOString(),
      }),
    };

    ws.onmessage(toolEvent);

    expect(useWebSocketStore.getState().toolCount).toBe(2);
    expect(useWebSocketStore.getState().toolNames).toEqual(['web_search', 'fetch_url']);
  });

  it('13.2.3: chat_message from head_of_council updates messageHistory and bumps unread', () => {
    useWebSocketStore.getState()._openSocket();
    const ws = useWebSocketStore.getState()._ws as any;

    const chatMsgEvent = {
      data: JSON.stringify({
        type: 'chat_message',
        role: 'head_of_council',
        content: 'Greetings Sovereign, all systems are operating nominally.',
        message_id: 'msg-abc-123',
        timestamp: new Date().toISOString(),
      }),
    };

    ws.onmessage(chatMsgEvent);

    const history = useWebSocketStore.getState().messageHistory;
    expect(history.length).toBeGreaterThan(0);
    expect(history[history.length - 1].content).toContain('Greetings Sovereign');
    expect(useWebSocketStore.getState().lastMessage?.type).toBe('chat_message');
  });
});

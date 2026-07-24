import { describe, it, expect, vi, beforeEach } from 'vitest';
import { useWebSocketStore } from '../websocketStore';

describe('Send-failure queue', () => {
  beforeEach(() => {
    useWebSocketStore.setState({
      _ws: null,
      _messageQueue: [],
      _orphanRetryInFlight: false,
    });
  });

  it('should queue message when send throws', () => {
    const mockWs = {
      readyState: WebSocket.OPEN,
      send: vi.fn().mockImplementation(() => { throw new Error('socket closed'); }),
    } as any;
    useWebSocketStore.setState({ _ws: mockWs });

    const store = useWebSocketStore.getState();
    const result = store.sendMessage('hello world');

    expect(result).toBe(false);
    const queue = useWebSocketStore.getState()._messageQueue;
    expect(queue).toHaveLength(1);
    expect(queue[0].content).toBe('hello world');
  });

  it('should queue message when not connected', () => {
    useWebSocketStore.setState({ _ws: null });

    const store = useWebSocketStore.getState();
    const result = store.sendMessage('hello world');

    expect(result).toBe(false);
    const queue = useWebSocketStore.getState()._messageQueue;
    expect(queue).toHaveLength(1);
    expect(queue[0].content).toBe('hello world');
  });

  it('should send message directly when connected', () => {
    const mockWs = {
      readyState: WebSocket.OPEN,
      send: vi.fn(),
    } as any;
    useWebSocketStore.setState({ _ws: mockWs });

    const store = useWebSocketStore.getState();
    const result = store.sendMessage('hello world');

    expect(result).toBe(true);
    expect(mockWs.send).toHaveBeenCalledTimes(1);
    const sent = JSON.parse(mockWs.send.mock.calls[0][0]);
    expect(sent.type).toBe('message');
    expect(sent.content).toBe('hello world');
  });
});

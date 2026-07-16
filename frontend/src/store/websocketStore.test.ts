import { describe, it, expect, beforeEach, vi } from 'vitest';
import { useWebSocketStore } from './websocketStore';
import { canReconnect } from './connectionPhase';
import { websocketReplayApi } from '@/services/websocketReplay';

// jsdom has no real WebSocket; stub it so connect()/disconnect() don't throw.
class FakeWS {
  static readonly OPEN = 1; static readonly CONNECTING = 0; static readonly CLOSED = 3;
  readyState = FakeWS.CONNECTING;
  send = vi.fn();
  close = vi.fn(() => { this.readyState = FakeWS.CLOSED; });
  onopen: any; onclose: any; onerror: any; onmessage: any;
  constructor(public url: string) {
    setTimeout(() => { this.readyState = FakeWS.OPEN; this.onopen?.({}); }, 0);
  }
}
vi.stubGlobal('WebSocket', FakeWS as any);

beforeEach(() => {
  useWebSocketStore.setState({ connectionPhase: 'offline', _genesisGraceCount: 0, error: null });
});

describe('websocketStore phase', () => {
  it('connect_start -> connecting; system -> active (P2: no error used for progress)', () => {
    useWebSocketStore.getState()._transition({ type: 'connect_start' });
    expect(useWebSocketStore.getState().connectionPhase).toBe('connecting');
    expect(useWebSocketStore.getState().isConnecting()).toBe(true);
    useWebSocketStore.getState()._transition({ type: 'system' });
    expect(useWebSocketStore.getState().connectionPhase).toBe('active');
    expect(useWebSocketStore.getState().isConnected()).toBe(true);
  });

  it('transient not_started stays genesis_running within grace (P5)', () => {
    useWebSocketStore.getState()._transition({ type: 'system_not_ready', genesisTriggered: true });
    expect(useWebSocketStore.getState().connectionPhase).toBe('genesis_running');
    for (let i = 0; i < 5; i++) {
      useWebSocketStore.getState()._transition({ type: 'poll', status: 'not_started' });
    }
    expect(useWebSocketStore.getState().connectionPhase).toBe('genesis_running');
    // After grace exhausted (6th not_started), flips to waiting_for_key.
    useWebSocketStore.getState()._transition({ type: 'poll', status: 'not_started' });
    expect(useWebSocketStore.getState().connectionPhase).toBe('waiting_for_key');
  });

  it('poll failed -> genesis_failed and is reconnectable (P9)', () => {
    useWebSocketStore.getState()._transition({ type: 'system_not_ready', genesisTriggered: true });
    useWebSocketStore.getState()._transition({ type: 'poll', status: 'failed' });
    expect(useWebSocketStore.getState().connectionPhase).toBe('genesis_failed');
    expect(canReconnect('genesis_failed')).toBe(true);
  });

  it('notifyApiKeyAdded leaves waiting_for_key -> connecting (P3 escape)', () => {
    useWebSocketStore.getState()._transition({ type: 'system_not_ready', genesisTriggered: false });
    expect(useWebSocketStore.getState().connectionPhase).toBe('waiting_for_key');
    useWebSocketStore.getState()._transition({ type: 'notify_key_added' });
    expect(useWebSocketStore.getState().connectionPhase).toBe('connecting');
  });
});

describe('genesis awaiting name', () => {
  beforeEach(() => {
    useWebSocketStore.setState({
      genesisAwaitingName: false,
      genesisNamePrompt: '',
      genesisNameTimeout: 0,
      connectionPhase: 'genesis_running',
    });
  });

  it('submitCountryName clears the awaiting flag on success', async () => {
    const spy = vi
      .spyOn(websocketReplayApi, 'submitCountryName')
      .mockResolvedValue({ accepted: true });
    const ok = await useWebSocketStore.getState().submitCountryName('Veridia');
    expect(ok).toBe(true);
    expect(useWebSocketStore.getState().genesisAwaitingName).toBe(false);
    spy.mockRestore();
  });

  it('submitCountryName returns false and keeps flag cleared on rejected', async () => {
    const spy = vi
      .spyOn(websocketReplayApi, 'submitCountryName')
      .mockResolvedValue({ accepted: false });
    const ok = await useWebSocketStore.getState().submitCountryName('Veridia');
    expect(ok).toBe(false);
    expect(useWebSocketStore.getState().genesisAwaitingName).toBe(false);
    spy.mockRestore();
  });
});

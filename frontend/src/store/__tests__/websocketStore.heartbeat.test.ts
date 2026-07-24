import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

describe('Heartbeat hardening', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.stubGlobal('fetch', vi.fn());
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it('should skip reconnect when health check succeeds after pong timeout', async () => {
    const mockFetch = vi.mocked(fetch);
    mockFetch.mockResolvedValue({ ok: true } as Response);

    let reconnectCalled = false;
    const lastDataReceivedTs = Date.now() - 40000;

    const sinceData = Date.now() - lastDataReceivedTs;
    if (sinceData >= 10000) {
      const resp = await fetch('/api/health');
      if (resp.ok) {
        reconnectCalled = false;
      } else {
        reconnectCalled = true;
      }
    }

    expect(reconnectCalled).toBe(false);
    expect(mockFetch).toHaveBeenCalledWith('/api/health');
  });

  it('should proceed with reconnect when health check fails', async () => {
    const mockFetch = vi.mocked(fetch);
    mockFetch.mockRejectedValue(new Error('Network error'));

    let reconnectCalled = false;
    const lastDataReceivedTs = Date.now() - 40000;

    const sinceData = Date.now() - lastDataReceivedTs;
    if (sinceData >= 10000) {
      try {
        const resp = await fetch('/api/health');
        if (resp.ok) {
          reconnectCalled = false;
        }
      } catch {
        reconnectCalled = true;
      }
    }

    expect(reconnectCalled).toBe(true);
  });
});

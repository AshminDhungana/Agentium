import { describe, it, expect, vi } from 'vitest';

describe('voiceBridgeService', () => {
  it('exports TranscriptEvent type', async () => {
    const mod = await import('../voiceBridge');
    const handler = vi.fn();
    const unsub = mod.voiceBridgeService.onTranscript(handler);
    expect(typeof unsub).toBe('function');
  });

  it('registers and fires transcript handlers', async () => {
    const mod = await import('../voiceBridge');
    const handler = vi.fn();
    const unsub = mod.voiceBridgeService.onTranscript(handler);

    // Simulate internal handler dispatch
    const handlers = (mod.voiceBridgeService as any).transcriptHandlers as Set<Function>;
    handlers.forEach(h => h({ role: 'user', text: 'hello', ts: 100 }));

    expect(handler).toHaveBeenCalledWith({ role: 'user', text: 'hello', ts: 100 });
    expect(handler).toHaveBeenCalledTimes(1);
    unsub();
    handlers.forEach(h => h({ role: 'user', text: 'hello', ts: 100 }));
    expect(handler).toHaveBeenCalledTimes(1);
  });
});

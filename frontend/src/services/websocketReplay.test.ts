import { websocketReplayApi, type GenesisStatusResponse } from './websocketReplay';

describe('websocketReplay genesis types', () => {
  it('GenesisStatusResponse allows awaiting_name', () => {
    const r: GenesisStatusResponse = {
      status: 'awaiting_name',
      prompt: 'Name your nation',
      timeout_seconds: 60,
    };
    expect(r.status).toBe('awaiting_name');
    expect(r.prompt).toBe('Name your nation');
    expect(r.timeout_seconds).toBe(60);
  });
});

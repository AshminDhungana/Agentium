import { describe, it, expect, beforeEach, vi, beforeAll, afterAll } from 'vitest';
import { useChatStore } from './chatStore';

beforeAll(() => {
  vi.stubGlobal('matchMedia', (query: string) => ({
    matches: query === '(prefers-reduced-motion: reduce)',
    media: query,
    onchange: null,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent: vi.fn(),
  }));
});
afterAll(() => {
  vi.unstubAllGlobals();
});

describe('chatStore streaming', () => {
  beforeEach(() => {
    useChatStore.setState({ messages: [], activeStreamId: null, currentStreamingMessage: '' });
  });

  it('beginStream inserts a streaming placeholder with server id', () => {
    useChatStore.getState().beginStream('m1', 'head_of_council');
    const msgs = useChatStore.getState().messages;
    expect(msgs).toHaveLength(1);
    expect(msgs[0].id).toBe('m1');
    expect(msgs[0].status).toBe('streaming');
    expect(useChatStore.getState().activeStreamId).toBe('m1');
  });

  it('appendDelta accrues content by stream_id', () => {
    useChatStore.getState().beginStream('m1', 'head_of_council');
    useChatStore.getState().appendDelta('m1', 'Hello ');
    useChatStore.getState().appendDelta('m1', 'world');
    expect(useChatStore.getState().messages[0].content).toBe('Hello world');
  });

  it('endStream finalizes content, metadata, and status', () => {
    useChatStore.getState().beginStream('m1', 'head_of_council');
    useChatStore.getState().appendDelta('m1', 'Hi');
    useChatStore.getState().endStream('m1', 'Hi', { model: 'gpt-test', tokens_used: 3 });
    const m = useChatStore.getState().messages[0];
    expect(m.content).toBe('Hi');
    expect(m.status).toBe('sent');
    expect(m.metadata?.model).toBe('gpt-test');
    expect(useChatStore.getState().activeStreamId).toBeNull();
  });
});

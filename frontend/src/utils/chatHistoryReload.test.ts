import { describe, it, expect } from 'vitest';
import { shouldReloadChatOnActive } from './chatHistoryReload';

describe('shouldReloadChatOnActive', () => {
  it('reloads when phase becomes active and no messages', () => {
    expect(shouldReloadChatOnActive('genesis_running', 'active', false)).toBe(true);
  });

  it('does not reload when already active (no transition)', () => {
    expect(shouldReloadChatOnActive('active', 'active', false)).toBe(false);
  });

  it('does not reload when becoming active but messages exist', () => {
    expect(shouldReloadChatOnActive('genesis_running', 'active', true)).toBe(false);
  });

  it('does not reload for non-active transitions', () => {
    expect(shouldReloadChatOnActive('connecting', 'genesis_running', false)).toBe(false);
  });
});

import { describe, it, expect, beforeEach } from 'vitest';
import { useWebSocketStore, isHeadMessageUnreadEligible } from '../websocketStore';

describe('unread counter', () => {
  beforeEach(() => {
    useWebSocketStore.setState({ unreadCount: 0 });
  });

  it('treats /chat as ineligible for unread counting', () => {
    expect(isHeadMessageUnreadEligible('/chat')).toBe(false);
  });

  it('treats any other route as eligible for unread counting', () => {
    expect(isHeadMessageUnreadEligible('/agents')).toBe(true);
    expect(isHeadMessageUnreadEligible('/')).toBe(true);
  });

  it('markAsRead resets the counter to zero', () => {
    useWebSocketStore.setState({ unreadCount: 4 });
    useWebSocketStore.getState().markAsRead();
    expect(useWebSocketStore.getState().unreadCount).toBe(0);
  });

  it('_incrementUnread adds one to the counter', () => {
    useWebSocketStore.setState({ unreadCount: 2 });
    useWebSocketStore.getState()._incrementUnread();
    expect(useWebSocketStore.getState().unreadCount).toBe(3);
  });
});

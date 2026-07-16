import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Routes, Route, NavLink } from 'react-router-dom';
import { describe, it, expect } from 'vitest';
import { ChatPage } from '../ChatPage';
import { KeepAliveOutlet } from '@/components/layout/KeepAliveOutlet';
import { useWebSocketStore } from '@/store/websocketStore';

function Harness() {
  return (
    <MemoryRouter initialEntries={['/chat']}>
      <NavLink to="/chat">go-chat</NavLink>
      <NavLink to="/other">go-other</NavLink>
      <Routes>
        <Route path="/" element={<KeepAliveOutlet />}>
          <Route path="chat" element={<ChatPage />} />
          <Route path="other" element={<div>other page</div>} />
        </Route>
      </Routes>
    </MemoryRouter>
  );
}

describe('ChatPage unread counter', () => {
  it('re-clears the counter on the second visit to /chat (keep-alive)', async () => {
    const user = userEvent.setup();
    useWebSocketStore.setState({ unreadCount: 5 });
    render(<Harness />);
    // First visit clears it.
    await waitFor(() => expect(useWebSocketStore.getState().unreadCount).toBe(0));
    // Leave, then a new Head message arrives while away.
    await user.click(screen.getByText('go-other'));
    useWebSocketStore.setState({ unreadCount: 3 });
    expect(useWebSocketStore.getState().unreadCount).toBe(3);
    // Returning to /chat must clear it again (the bug: it stayed at 3).
    await user.click(screen.getByText('go-chat'));
    await waitFor(() => expect(useWebSocketStore.getState().unreadCount).toBe(0));
  });
});

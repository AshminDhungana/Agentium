import type { ConnectionPhase } from '@/store/connectionPhase';

/**
 * Decide whether ChatPage should (re)load chat history when the WebSocket
 * connection phase changes.
 *
 * We reload exactly once, at the moment the connection becomes 'active'
 * (genesis just finished), and only if we have no messages yet. This surfaces
 * the Head-of-Council welcome message that genesis persists to chat history
 * but that the in-process broadcast cannot deliver live (the chat socket is
 * gated on Head 00001 existing and is closed until genesis completes).
 */
export function shouldReloadChatOnActive(
  prevPhase: ConnectionPhase,
  phase: ConnectionPhase,
  hasMessages: boolean,
): boolean {
  return phase === 'active' && prevPhase !== 'active' && !hasMessages;
}

import { useEffect } from 'react';
import { useWebSocketStore } from '@/store/websocketStore';
import { useChatStore } from '@/store/chatStore';
import { showToast } from '@/hooks/useToast';
import type { MessageMetadata } from '@/store/chatStore';

/**
 * Global (route-independent) handler for structured input cards.
 * Registers every incoming card so its lifecycle/answer state is tracked
 * regardless of which page is mounted, and raises a distinct, actionable
 * toast when the user is NOT on the chat page so a pending question is
 * never silently missed.
 */
export function useGlobalChatCards() {
  useEffect(() => {
    const unsub = useWebSocketStore.subscribe((state, prev) => {
      const msg = state.lastMessage;
      if (!msg || msg === prev.lastMessage) return;
      if (msg.type !== 'message' && msg.type !== 'message_end') return;

      const meta = (msg.metadata ?? (msg as any).message?.metadata) as MessageMetadata | undefined;
      const card = meta?.card;
      if (!card) return;

      useChatStore.getState().registerCard(card.card_id, true);

      if (window.location.pathname !== '/chat') {
        // NOTE: the project's `showToast.info` wrapper only accepts a single
        // `message` string — it does NOT support `duration` or `onClick` options,
        // and the installed react-hot-toast version has no `onClick` on its toast
        // options either. So we fall back to a distinct INFO toast whose message
        // itself is the actionable hint. The card is already registered globally
        // by the call above, so when the Sovereign opens /chat the question is
        // waiting — the toast just needs to be noticeable and self-explanatory.
        showToast.info('Head of Council asked you a question — open the Chat tab to answer');
      }
    });
    return unsub;
  }, []);
}

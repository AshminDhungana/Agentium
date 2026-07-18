import { useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
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
  const navigate = useNavigate();
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
        // A distinct, actionable INFO toast. Clicking it jumps straight to the
        // chat page where the question is already registered and waiting.
        showToast.info('Head of Council asked you a question — open the Chat tab to answer', {
          duration: 8000,
          onClick: () => navigate('/chat'),
        });
      }
    });
    return unsub;
  }, []);
}

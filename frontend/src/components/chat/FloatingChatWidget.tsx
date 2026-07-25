import { useState, useEffect, useRef, useCallback } from 'react';
import { motion, useReducedMotion, AnimatePresence } from 'motion/react';
import { MessageCircle } from 'lucide-react';
import { useChatStore } from '@/store/chatStore';
import type { Message as ChatMessage } from '@/store/chatStore';
import { useWebSocketStore } from '@/store/websocketStore';
import { voiceBridgeService, VoiceMode } from '@/services/voiceBridge';
import { ChatHeader } from './ChatHeader';
import { MessageList } from './MessageList';
import { ChatInput } from './ChatInput';
import { MinimizedWidget } from './MinimizedWidget';
import './FloatingChatWidget.styles.css';

type WidgetState = 'collapsed' | 'hovered' | 'expanded' | 'minimized';

const SPRING_GENTLE = [0.22, 1, 0.36, 1] as const;

const CHAT_POSITION = {
  bottom: 'bottom-6',   // 24px
  right: 'right-8',     // 32px
} as const;

const CHAT_POSITION_MOBILE = {
  bottom: 'bottom-4',   // 16px
  right: 'right-4',     // 16px
} as const;

// Single source of truth for widget placement, used by every state below.
// Desktop keeps the widget clear of the scrollbar and viewport edge;
// the max-[480px] variants fall back to the tighter mobile spacing.
const WIDGET_POSITION =
  `${CHAT_POSITION.bottom} ${CHAT_POSITION.right} ` +
  `max-[480px]:${CHAT_POSITION_MOBILE.bottom} max-[480px]:${CHAT_POSITION_MOBILE.right}`;

// NOTE: this component no longer checks auth state or the current route
// itself. Both were previously an internal `if (!isAuthenticated ||
// either check could silently hide the widget with no visible error.
// MainLayout now owns both concerns instead: it only renders
// <FloatingChatWidget /> at all on an authenticated route, and it excludes
// the /chat route at the call site. So whenever this component is mounted,
// it should show something.
export function FloatingChatWidget() {
  const reduceMotionPref = useReducedMotion();
  const reduceMotion = reduceMotionPref ?? false;

  const messages = useChatStore((s) => s.messages);
  const unreadCount = useWebSocketStore((s) => s.unreadCount);
  const wsSendMessage = useWebSocketStore((s) => s.sendMessage);

  const [state, setState] = useState<WidgetState>('collapsed');
  const [voiceMode, setVoiceMode] = useState<VoiceMode>('system');
  const panelRef = useRef<HTMLDivElement>(null);
  const closeButtonRef = useRef<HTMLButtonElement>(null);
  const previousActiveElement = useRef<HTMLElement | null>(null);

  // Sync voiceMode with bridge
  const syncVoiceMode = useCallback((mode: VoiceMode) => {
    setVoiceMode(mode);
    voiceBridgeService.setVoiceMode(mode);
  }, []);

  // Voice mode transitions based on widget state
  useEffect(() => {
    if (state === 'expanded') syncVoiceMode('popup');
    else if (state === 'minimized' || state === 'collapsed') syncVoiceMode('system');
  }, [state, syncVoiceMode]);

  // Focus management: save/restore focus around the expanded panel.
  useEffect(() => {
    if (state === 'expanded') {
      previousActiveElement.current = document.activeElement as HTMLElement;
      const t = setTimeout(() => closeButtonRef.current?.focus(), 0);
      return () => clearTimeout(t);
    }
    if (previousActiveElement.current) {
      previousActiveElement.current.focus();
      previousActiveElement.current = null;
    }
  }, [state]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Escape' && state === 'expanded') {
      setState('collapsed');
    }
  };

  // Previously, each widget state (collapsed / hovered / minimized /
  // expanded) was a separate early `return`, so switching between them
  // unmounted the whole tree instantly — including whatever AnimatePresence
  // instance happened to be inside that branch. Framer Motion never got a
  // chance to play an exit animation because the component it needed to
  // animate was already gone. A single AnimatePresence wrapping all four
  // variants fixes that: only one is ever rendered (via mode="wait"), so
  // switching state is a normal mount/unmount pair Framer can animate.
  return (
    <AnimatePresence mode="wait">
      {state === 'collapsed' && (
        <motion.button
          key="collapsed"
          className={`fixed ${WIDGET_POSITION} z-50 h-2 w-2 cursor-pointer rounded-full border-none bg-[var(--color-primary)] p-0 focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-[var(--color-primary)]`}
          aria-label="Open Agentium Chat"
          onMouseEnter={() => setState('hovered')}
          onClick={() => setState('expanded')}
          initial={reduceMotion ? false : { opacity: 0, scale: 0.6 }}
          animate={{ opacity: 1, scale: 1 }}
          exit={reduceMotion ? { opacity: 0 } : { opacity: 0, scale: 0.6 }}
          whileHover={{ scale: 1.1 }}
          whileTap={{ scale: 0.9 }}
          transition={{ duration: reduceMotion ? 0 : 0.2 }}
        >
          <motion.span
            className="block h-full w-full rounded-full bg-[var(--color-primary)]"
            animate={reduceMotion ? {} : { scale: [1, 1.3, 1], opacity: [0.6, 1, 0.6] }}
            transition={{ duration: 2, repeat: Infinity, ease: 'easeInOut' }}
          />
        </motion.button>
      )}

      {state === 'hovered' && (
        <motion.button
          key="hovered"
          className={`fixed ${WIDGET_POSITION} z-50 flex h-8 w-8 cursor-pointer items-center justify-center rounded-full border-none bg-[var(--color-primary)] text-white shadow-[0_10px_25px_rgba(0,0,0,0.15)] focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-[var(--color-primary)]`}
          aria-label="Open Agentium Chat"
          onMouseLeave={() => setState('collapsed')}
          onClick={() => setState('expanded')}
          initial={reduceMotion ? false : { opacity: 0, scale: 0.6 }}
          animate={{ opacity: 1, scale: 1 }}
          exit={reduceMotion ? { opacity: 0 } : { opacity: 0, scale: 0.6 }}
          whileHover={{ scale: 1.05 }}
          whileTap={{ scale: 0.92 }}
          transition={{ duration: reduceMotion ? 0 : 0.2 }}
        >
          <MessageCircle className="h-5 w-5" aria-hidden="true" />
        </motion.button>
      )}

      {state === 'minimized' && (
        <MinimizedWidget
          key="minimized"
          unreadCount={unreadCount}
          onClick={() => setState('expanded')}
          reduceMotion={reduceMotion}
        />
      )}

      {state === 'expanded' && (
        <motion.div
          key="expanded"
          ref={panelRef}
          role="dialog"
          aria-modal="false"
          aria-label="Agentium Chat"
          aria-describedby="chat-desc"
          onKeyDown={handleKeyDown}
          className={`fixed ${WIDGET_POSITION} z-50 flex max-h-[520px] w-[360px] flex-col overflow-hidden rounded-2xl bg-[var(--color-surface-elevated)] text-[var(--color-text-primary)] shadow-2xl max-[480px]:inset-x-4 max-[480px]:w-auto max-[480px]:max-h-[80vh] max-[480px]:landscape:max-h-[85vh]`}
          initial={reduceMotion ? false : { opacity: 0, scale: 0.95, y: 20 }}
          animate={{ opacity: 1, scale: 1, y: 0 }}
          exit={reduceMotion ? { opacity: 0 } : { opacity: 0, scale: 0.95, y: 20 }}
          transition={{ duration: reduceMotion ? 0 : 0.3, ease: SPRING_GENTLE }}
        >
          <p id="chat-desc" className="sr-only">
            Chat with Agentium Head of Council. Messages sync across pages.
          </p>

          <ChatHeader
            voiceStatus={voiceBridgeService.status}
            onMinimize={() => setState('minimized')}
            onClose={() => setState('collapsed')}
            closeButtonRef={closeButtonRef}
          />

          <MessageList messages={messages as ChatMessage[]} reduceMotion={reduceMotion} />

          <ChatInput
            onSend={(content, attachments) => {
              wsSendMessage(content, attachments);
            }}
            reduceMotion={reduceMotion}
          />
        </motion.div>
      )}
    </AnimatePresence>
  );
}
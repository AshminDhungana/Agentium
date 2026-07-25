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

type WidgetState = 'hidden' | 'collapsed' | 'hovered' | 'expanded' | 'minimized';

const EASE_GENTLE = [0.22, 1, 0.36, 1] as const;
// Confident, controlled motion for the panel — enterprise chrome shouldn't
// visibly overshoot. A little bounce is reserved for the launcher only.
const SPRING_PANEL = { type: 'spring', stiffness: 320, damping: 32, mass: 0.9 } as const;
const SPRING_LAUNCHER = { type: 'spring', stiffness: 260, damping: 20 } as const;

const CHAT_POSITION = {
  bottom: 'bottom-6', // 24px
  right: 'right-8',   // 32px
} as const;

const CHAT_POSITION_MOBILE = {
  bottom: 'bottom-4', // 16px
  right: 'right-4',   // 16px
} as const;

// Single source of truth for widget placement, used by every state below.
// Desktop keeps the widget clear of the scrollbar and viewport edge;
// the max-[480px] variants fall back to the tighter mobile spacing.
const WIDGET_POSITION =
  `${CHAT_POSITION.bottom} ${CHAT_POSITION.right} ` +
  `max-[480px]:${CHAT_POSITION_MOBILE.bottom} max-[480px]:${CHAT_POSITION_MOBILE.right}`;

interface FloatingChatWidgetProps {
  /**
   * True on routes (e.g. the full /chat page) where a floating duplicate of
   * the chat would be redundant. The component stays mounted regardless —
   * only its internal `state` becomes 'hidden' — so AnimatePresence can play
   * a genuine exit/entrance transition across navigation instead of the
   * widget instantly popping in or disappearing when the route changes.
   */
  hidden?: boolean;
}

export function FloatingChatWidget({ hidden = false }: FloatingChatWidgetProps) {
  const reduceMotionPref = useReducedMotion();
  const reduceMotion = reduceMotionPref ?? false;

  const messages = useChatStore((s) => s.messages);
  const unreadCount = useWebSocketStore((s) => s.unreadCount);
  const wsSendMessage = useWebSocketStore((s) => s.sendMessage);

  const [state, setState] = useState<WidgetState>(hidden ? 'hidden' : 'collapsed');
  const [voiceMode, setVoiceMode] = useState<VoiceMode>('system');
  const panelRef = useRef<HTMLDivElement>(null);
  const closeButtonRef = useRef<HTMLButtonElement>(null);
  const previousActiveElement = useRef<HTMLElement | null>(null);
  // Remembers what to restore to once `hidden` clears again. 'hovered' is
  // intentionally excluded — it's a transient mouse-over state, so it
  // resolves back to the resting 'collapsed' dot rather than reappearing
  // mid-hover on a page the cursor isn't even over.
  const restoreStateRef = useRef<'collapsed' | 'expanded' | 'minimized'>('collapsed');

  // React to the route-driven `hidden` prop without ever unmounting this
  // component. Reopening straight back into a full panel on the next page
  // would be jarring, so an expanded (or hovered) widget restores to the
  // resting dot; a minimized (unread-carrying) state is preserved as-is.
  useEffect(() => {
    if (hidden) {
      setState((prev) => {
        if (prev !== 'hidden') {
          restoreStateRef.current = prev === 'minimized' ? 'minimized' : 'collapsed';
        }
        return 'hidden';
      });
    } else {
      setState((prev) => (prev === 'hidden' ? restoreStateRef.current : prev));
    }
  }, [hidden]);

  // Sync voiceMode with bridge
  const syncVoiceMode = useCallback((mode: VoiceMode) => {
    setVoiceMode(mode);
    voiceBridgeService.setVoiceMode(mode);
  }, []);

  // Voice mode transitions based on widget state
  useEffect(() => {
    syncVoiceMode(state === 'expanded' ? 'popup' : 'system');
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

  // A single AnimatePresence wrapping all states means only one is ever
  // rendered (mode="wait"), so every transition — including 'hidden', which
  // renders nothing — is a normal mount/unmount pair Framer can animate.
  return (
    <AnimatePresence mode="wait">
      {state === 'collapsed' && (
        <motion.button
          key="collapsed"
          type="button"
          className={`fixed ${WIDGET_POSITION} z-50 flex h-3 w-3 cursor-pointer items-center justify-center rounded-full border-none bg-[var(--color-primary)] p-0 outline-none focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-[var(--color-primary)] focus-visible:ring-offset-2`}
          aria-label={
            unreadCount > 0
              ? `Open Agentium Chat, ${unreadCount} unread message${unreadCount === 1 ? '' : 's'}`
              : 'Open Agentium Chat'
          }
          onMouseEnter={() => setState('hovered')}
          onFocus={() => setState('hovered')}
          onClick={() => setState('expanded')}
          // The "beautiful dot" moment: pops in with a slight rotate + spring
          // overshoot when the widget (re)appears, e.g. navigating off /chat.
          initial={reduceMotion ? false : { opacity: 0, scale: 0.4, y: 24, rotate: -10 }}
          animate={{ opacity: 1, scale: 1, y: 0, rotate: 0 }}
          exit={
            reduceMotion
              ? { opacity: 0 }
              : { opacity: 0, scale: 0.5, y: 12, transition: { duration: 0.15, ease: EASE_GENTLE } }
          }
          whileTap={{ scale: 0.85 }}
          transition={reduceMotion ? { duration: 0 } : SPRING_LAUNCHER}
        >
          {/* Breathing pulse draws the eye to what is, by design, a small
              target — the same affordance the resting dot always had. */}
          <motion.span
            className="block h-full w-full rounded-full bg-[var(--color-primary)]"
            animate={reduceMotion ? {} : { scale: [1, 1.4, 1], opacity: [0.7, 1, 0.7] }}
            transition={{ duration: 2, repeat: Infinity, ease: 'easeInOut' }}
          />

          {unreadCount > 0 && (
            <motion.span
              className="absolute -top-1 -right-1 flex h-3.5 min-w-[14px] items-center justify-center rounded-full border-2 border-[var(--color-background)] bg-[var(--color-destructive)]"
              initial={{ scale: 0 }}
              animate={{ scale: 1 }}
              transition={{ type: 'spring', stiffness: 400, damping: 15 }}
              aria-hidden="true"
            />
          )}
        </motion.button>
      )}

      {state === 'hovered' && (
        <motion.button
          key="hovered"
          type="button"
          className={`fixed ${WIDGET_POSITION} z-50 flex h-14 w-14 items-center justify-center rounded-full border border-white/10 bg-[var(--color-primary)] text-white shadow-[0_2px_6px_rgba(15,23,42,0.12),0_16px_32px_-8px_rgba(15,23,42,0.35)] outline-none focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-[var(--color-primary)] focus-visible:ring-offset-2`}
          aria-label={
            unreadCount > 0
              ? `Open Agentium Chat, ${unreadCount} unread message${unreadCount === 1 ? '' : 's'}`
              : 'Open Agentium Chat'
          }
          onMouseLeave={() => setState('collapsed')}
          onBlur={() => setState('collapsed')}
          onClick={() => setState('expanded')}
          initial={reduceMotion ? false : { opacity: 0, scale: 0.4, rotate: -10 }}
          animate={{ opacity: 1, scale: 1, rotate: 0 }}
          exit={
            reduceMotion
              ? { opacity: 0 }
              : { opacity: 0, scale: 0.4, rotate: 10, transition: { duration: 0.15, ease: EASE_GENTLE } }
          }
          whileHover={reduceMotion ? {} : { scale: 1.06 }}
          whileTap={{ scale: 0.94 }}
          transition={reduceMotion ? { duration: 0 } : SPRING_LAUNCHER}
        >
          <MessageCircle className="h-6 w-6" aria-hidden="true" />

          {/* Presence indicator — signals the assistant is available, the
              way Intercom/Zendesk-style launchers do. */}
          <span
            className="absolute bottom-0 right-0 h-3.5 w-3.5 rounded-full border-2 border-[var(--color-surface-elevated)] bg-emerald-400"
            aria-hidden="true"
          />

          {unreadCount > 0 && (
            <motion.span
              className="absolute -top-1 -right-1 flex h-5 min-w-[20px] items-center justify-center rounded-full bg-[var(--color-destructive)] px-1 text-[11px] font-semibold leading-none text-white shadow-sm"
              initial={{ scale: 0 }}
              animate={{ scale: 1 }}
              transition={{ type: 'spring', stiffness: 400, damping: 15 }}
            >
              {unreadCount > 9 ? '9+' : unreadCount}
            </motion.span>
          )}
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
          className={`fixed ${WIDGET_POSITION} z-50 flex max-h-[600px] w-[384px] flex-col overflow-hidden rounded-[20px] border border-[var(--color-border)] bg-[var(--color-surface-elevated)] text-[var(--color-text-primary)] shadow-[0_24px_64px_-12px_rgba(15,23,42,0.45)] max-[480px]:inset-x-4 max-[480px]:w-auto max-[480px]:max-h-[80vh] max-[480px]:landscape:max-h-[85vh]`}
          initial={reduceMotion ? false : { opacity: 0, scale: 0.94, y: 16 }}
          animate={{ opacity: 1, scale: 1, y: 0 }}
          exit={
            reduceMotion
              ? { opacity: 0 }
              : { opacity: 0, scale: 0.96, y: 12, transition: { duration: 0.18, ease: EASE_GENTLE } }
          }
          transition={reduceMotion ? { duration: 0 } : SPRING_PANEL}
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
import { useState, useEffect, useRef, useCallback } from 'react';
import { useLocation } from 'react-router-dom';
import { motion, useReducedMotion, AnimatePresence } from 'motion/react';
import { MessageCircle, Minimize, Maximize, X, Bot, Mic } from 'lucide-react';
import { useChatStore } from '@/store/chatStore';
import type { Message as ChatMessage } from '@/store/chatStore';
import { useWebSocketStore } from '@/store/websocketStore';
import { useAuthStore } from '@/store/authStore';
import { voiceBridgeService, VoiceMode } from '@/services/voiceBridge';
import { ChatHeader } from './ChatHeader';
import { MessageList } from './MessageList';
import { ChatInput } from './ChatInput';
import { MinimizedWidget } from './MinimizedWidget';
import './FloatingChatWidget.styles.css';

type WidgetState = 'collapsed' | 'hovered' | 'expanded' | 'minimized';

export function FloatingChatWidget() {
  const location = useLocation();
  const isChatPage = location.pathname === '/chat';
  const isAuthenticated = useAuthStore((s) => s.user?.isAuthenticated);

  if (!isAuthenticated || isChatPage) return null;

  const messages = useChatStore((s) => s.messages);
  const unreadCount = useWebSocketStore((s) => s.unreadCount);
  const wsSendMessage = useWebSocketStore((s) => s.sendMessage);

  const [state, setState] = useState<WidgetState>('collapsed');
  const [voiceMode, setVoiceMode] = useState<VoiceMode>('system');
  const dialogRef = useRef<HTMLDialogElement>(null);
  const closeButtonRef = useRef<HTMLButtonElement>(null);
  const previousActiveElement = useRef<HTMLElement | null>(null);
  const reduceMotionPref = useReducedMotion();
  const reduceMotion = reduceMotionPref ?? false;

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

  // Route change handling
  useEffect(() => {
    if (isChatPage) {
      setState('collapsed');
      syncVoiceMode('chat');
    } else if (state === 'collapsed') {
      syncVoiceMode('system');
    }
  }, [isChatPage, state, syncVoiceMode]);

  // Focus management for dialog
  useEffect(() => {
    if (state === 'expanded') {
      previousActiveElement.current = document.activeElement as HTMLElement;
      setTimeout(() => closeButtonRef.current?.focus(), 0);
    } else if (previousActiveElement.current && state === 'collapsed') {
      previousActiveElement.current.focus();
      previousActiveElement.current = null;
    }
  }, [state]);

  // Handle Escape key on dialog
  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Escape' && state === 'expanded') {
      setState('collapsed');
    }
  };

  // Collapsed: 8px pulsing dot
  if (state === 'collapsed') {
    return (
      <motion.button
        className="floating-chat-collapsed"
        role="button"
        tabIndex={0}
        aria-label="Open Agentium Chat"
        onMouseEnter={() => setState('hovered')}
        onClick={() => setState('expanded')}
        whileHover={{ scale: 1.1 }}
        whileTap={{ scale: 0.9 }}
      >
        <motion.span
          className="floating-chat-dot"
          animate={reduceMotion ? {} : { scale: [1, 1.3, 1], opacity: [0.6, 1, 0.6] }}
          transition={{ duration: 2, repeat: Infinity, ease: 'easeInOut' }}
        />
      </motion.button>
    );
  }

  // Hovered: 32px chat icon with magnetic follow
  if (state === 'hovered') {
    return (
      <motion.button
        className="floating-chat-hovered"
        role="button"
        tabIndex={0}
        aria-label="Open Agentium Chat"
        onMouseLeave={() => setState('collapsed')}
        onClick={() => setState('expanded')}
        whileHover={{ scale: 1.05 }}
        whileTap={{ scale: 0.92 }}
      >
        <MessageCircle className="w-5 h-5" aria-hidden="true" />
      </motion.button>
    );
  }

  // Minimized: 48x48 pill with unread badge
  if (state === 'minimized') {
    return (
      <MinimizedWidget
        unreadCount={unreadCount}
        onClick={() => setState('expanded')}
        reduceMotion={reduceMotion}
      />
    );
  }

  // Expanded: native <dialog>
  return (
    <AnimatePresence mode="wait">
      <dialog
        ref={dialogRef}
        className="floating-chat-dialog"
        aria-label="Agentium Chat"
        aria-describedby="chat-desc"
        onKeyDown={handleKeyDown}
        open={state === 'expanded'}
        onClose={() => setState('collapsed')}
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
      </dialog>
    </AnimatePresence>
  );
}
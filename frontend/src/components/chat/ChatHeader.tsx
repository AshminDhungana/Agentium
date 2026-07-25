import { motion } from 'motion/react';
import { useRef } from 'react';
import { Bot, Minimize, Maximize, X, Wifi, WifiOff, Loader2 } from 'lucide-react';

interface ChatHeaderProps {
  voiceStatus: 'offline' | 'connecting' | 'connected' | 'error';
  onMinimize: () => void;
  onClose: () => void;
  closeButtonRef?: React.Ref<HTMLButtonElement>;
}

export function ChatHeader({ voiceStatus, onMinimize, onClose, closeButtonRef }: ChatHeaderProps) {
  const statusConfig = {
    connected: { color: 'var(--color-accent)', Icon: Wifi, pulse: true },
    connecting: { color: 'var(--color-warning)', Icon: Loader2, pulse: false },
    offline: { color: 'var(--color-text-muted)', Icon: WifiOff, pulse: false },
    error: { color: 'var(--color-destructive)', Icon: WifiOff, pulse: false },
  } as const;

  const { color, Icon, pulse } = statusConfig[voiceStatus];

  return (
    <header className="floating-chat-header">
      <div className="floating-chat-header-left">
        <div className="floating-chat-bot-icon">
          <Bot className="w-4 h-4" aria-hidden="true" />
        </div>
        <span className="floating-chat-title">Agentium</span>
      </div>

      <div className="floating-chat-header-right">
        <motion.span
          className="floating-chat-voice-dot"
          data-testid="voice-status-dot"
          style={{ backgroundColor: color }}
          animate={pulse ? { scale: [1, 1.3, 1] } : {}}
          transition={{ duration: 1.5, repeat: Infinity, ease: 'easeInOut' }}
        >
          <Icon className="w-3 h-3" aria-hidden="true" />
        </motion.span>

        <motion.button
          className="floating-chat-header-btn"
          onClick={onMinimize}
          aria-label="Minimize chat"
          whileTap={{ scale: 0.9 }}
        >
          <Minimize className="w-4 h-4" aria-hidden="true" />
        </motion.button>

        <motion.button
          ref={closeButtonRef}
          className="floating-chat-header-btn"
          onClick={onClose}
          aria-label="Close chat"
          whileTap={{ scale: 0.9 }}
        >
          <X className="w-4 h-4" aria-hidden="true" />
        </motion.button>
      </div>
    </header>
  );
}
import { motion } from 'motion/react';
import { User, Minimize2, X, Wifi, WifiOff, Loader2 } from 'lucide-react';

interface ChatHeaderProps {
  voiceStatus: 'offline' | 'connecting' | 'connected' | 'error';
  onMinimize: () => void;
  onClose: () => void;
  closeButtonRef?: React.Ref<HTMLButtonElement>;
}

const VOICE_STATUS_CONFIG = {
  connected: { color: 'var(--color-accent)', Icon: Wifi, pulse: true, label: 'Voice connected' },
  connecting: { color: 'var(--color-warning)', Icon: Loader2, pulse: false, label: 'Connecting voice…' },
  offline: { color: 'var(--color-text-muted)', Icon: WifiOff, pulse: false, label: 'Voice offline' },
  error: { color: 'var(--color-destructive)', Icon: WifiOff, pulse: false, label: 'Voice error' },
} as const;

export function ChatHeader({ voiceStatus, onMinimize, onClose, closeButtonRef }: ChatHeaderProps) {
  const { color, Icon, pulse, label } = VOICE_STATUS_CONFIG[voiceStatus];

  return (
    <header className="flex items-center justify-between gap-3 border-b border-[var(--color-border)] bg-[var(--color-surface)] px-4 py-3">
      <div className="flex min-w-0 items-center gap-2.5">
        <div className="relative flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-[var(--color-primary)] to-[var(--color-secondary)] text-white shadow-sm">
          <User className="h-4 w-4" aria-hidden="true" />
          <span
            className="absolute -bottom-0.5 -right-0.5 h-2.5 w-2.5 rounded-full border-2 border-[var(--color-surface)] bg-emerald-400"
            aria-hidden="true"
          />
        </div>
        <p className="truncate text-sm font-semibold leading-tight text-[var(--color-text-primary)]">
          Agentium
        </p>
      </div>

      <div className="flex shrink-0 items-center gap-0.5">
        <span
          className="flex h-7 w-7 items-center justify-center rounded-full"
          data-testid="voice-status-dot"
          title={label}
          aria-label={label}
        >
          <motion.span
            style={{ color }}
            className="flex"
            animate={pulse ? { scale: [1, 1.2, 1] } : {}}
            transition={{ duration: 1.5, repeat: Infinity, ease: 'easeInOut' }}
          >
            <Icon className={`h-4 w-4 ${voiceStatus === 'connecting' ? 'animate-spin' : ''}`} aria-hidden="true" />
          </motion.span>
        </span>

        <motion.button
          type="button"
          className="flex h-8 w-8 items-center justify-center rounded-lg text-[var(--color-text-muted)] transition-colors hover:bg-[var(--color-muted)] hover:text-[var(--color-text-primary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-primary)]"
          onClick={onMinimize}
          aria-label="Minimize chat"
          whileTap={{ scale: 0.9 }}
        >
          <Minimize2 className="h-4 w-4" aria-hidden="true" />
        </motion.button>

        <motion.button
          type="button"
          ref={closeButtonRef}
          className="flex h-8 w-8 items-center justify-center rounded-lg text-[var(--color-text-muted)] transition-colors hover:bg-[var(--color-muted)] hover:text-[var(--color-text-primary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-primary)]"
          onClick={onClose}
          aria-label="Close chat"
          whileTap={{ scale: 0.9 }}
        >
          <X className="h-4 w-4" aria-hidden="true" />
        </motion.button>
      </div>
    </header>
  );
}
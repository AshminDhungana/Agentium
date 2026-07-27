import { motion } from 'framer-motion';
import { useReducedMotion } from './hooks/useReducedMotion';
import type { ConnectionStatus, VoiceState } from './types';

interface StatusBadgeProps {
  status: ConnectionStatus;
  voiceState?: VoiceState;
  className?: string;
}

const statusConfig: Record<ConnectionStatus, { color: string; label: string }> = {
  connected: { color: 'var(--c-success)', label: 'Connected' },
  connecting: { color: 'var(--c-warning)', label: 'Connecting' },
  reconnecting: { color: 'var(--c-voice-listening)', label: 'Reconnecting' },
  error: { color: 'var(--c-error)', label: 'Error' },
  disconnected: { color: 'var(--color-text-muted)', label: 'Disconnected' },
};

const activeVoiceStates: VoiceState[] = ['listening', 'speaking', 'processing'];

export function StatusBadge({ status, voiceState, className = '' }: StatusBadgeProps) {
  const { prefersReduced } = useReducedMotion();
  const config = statusConfig[status];
  const isActive = voiceState && activeVoiceStates.includes(voiceState);

  return (
    <motion.div
      className={`fixed top-6 right-6 z-20 glass-pill px-4 py-2 flex items-center gap-2 ${className}`}
      initial={{ opacity: 0, y: -20, x: 20 }}
      animate={{ opacity: 1, y: 0, x: 0 }}
      transition={{ type: 'spring', stiffness: 300, damping: 30, delay: 0.1 }}
    >
      <motion.span
        className="relative w-2.5 h-2.5 rounded-full"
        style={{ backgroundColor: config.color }}
        animate={
          (status === 'connecting' || status === 'reconnecting' || isActive) && !prefersReduced
            ? {
                boxShadow: [
                  `0 0 6px ${config.color}`,
                  `0 0 18px ${config.color}80`,
                  `0 0 6px ${config.color}`,
                ],
                scale: [1, 1.2, 1],
              }
            : { scale: 1 }
        }
        transition={{
          duration: status === 'error' ? 0.3 : 1.5,
          repeat: Infinity,
          ease: status === 'error' ? 'easeInOut' : 'easeInOut',
        }}
        aria-hidden="true"
      />
      <span className="text-xs font-medium text-[var(--color-text-primary)] capitalize">
        {config.label}
      </span>
    </motion.div>
  );
}
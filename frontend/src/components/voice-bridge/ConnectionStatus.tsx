import { motion, type Variants } from 'framer-motion';
import { WifiOff, Loader2, AlertCircle, CheckCircle, XCircle } from 'lucide-react';
import type { ConnectionStatusProps, ConnectionStatus, ConnectionStatusConfig } from './types';

const STATUS_CONFIG: Record<ConnectionStatus, ConnectionStatusConfig> = {
  disconnected: {
    label: 'Disconnected',
    color: 'text-[var(--color-text-muted)]',
    icon: <WifiOff className="w-4 h-4" />,
    bgColor: 'bg-[var(--c-subtle)] dark:bg-[var(--c-subtle-dark)]',
    ringColor: 'border-[var(--c-hairline)] dark:border-[var(--c-hairline-dark)]',
    dotHex: '#9ca3af',
  },
  connecting: {
    label: 'Connecting...',
    color: 'text-[var(--c-warning)] dark:text-[var(--c-warning-light)]',
    icon: <Loader2 className="w-4 h-4 animate-spin" />,
    bgColor: 'bg-[var(--c-warning)]/15 dark:bg-[var(--c-warning)]/20',
    ringColor: 'border-[var(--c-warning)]/30 dark:border-[var(--c-warning)]/40',
    dotHex: '#f59e0b',
  },
  connected: {
    label: 'Connected',
    color: 'text-[var(--c-success)] dark:text-[var(--c-success-light)]',
    icon: <CheckCircle className="w-4 h-4" />,
    bgColor: 'bg-[var(--c-success)]/15 dark:bg-[var(--c-success)]/20',
    ringColor: 'border-[var(--c-success)]/30 dark:border-[var(--c-success)]/40',
    dotHex: '#10b981',
  },
  reconnecting: {
    label: 'Reconnecting...',
    color: 'text-[var(--c-warning)] dark:text-[var(--c-warning-light)]',
    icon: <Loader2 className="w-4 h-4 animate-spin" />,
    bgColor: 'bg-[var(--c-warning)]/15 dark:bg-[var(--c-warning)]/20',
    ringColor: 'border-[var(--c-warning)]/30 dark:border-[var(--c-warning)]/40',
    dotHex: '#f59e0b',
  },
  error: {
    label: 'Connection Error',
    color: 'text-[var(--c-error)] dark:text-[var(--c-error-light)]',
    icon: <AlertCircle className="w-4 h-4" />,
    bgColor: 'bg-[var(--c-error)]/15 dark:bg-[var(--c-error)]/20',
    ringColor: 'border-[var(--c-error)]/30 dark:border-[var(--c-error)]/40',
    dotHex: '#ef4444',
  },
};

const statusVariants: Variants = {
  hidden: { opacity: 0, y: -10, scale: 0.95 },
  visible: {
    opacity: 1,
    y: 0,
    scale: 1,
    transition: { type: 'spring' as const, stiffness: 400, damping: 30 },
  },
  exit: { opacity: 0, y: -10, scale: 0.95, transition: { duration: 0.2 } },
};

import { type TargetAndTransition } from 'framer-motion';

type DotAnimation = Record<ConnectionStatus, TargetAndTransition>;

const dotAnimation: DotAnimation = {
  connecting: { scale: [1, 1.2, 1], transition: { duration: 1, repeat: Infinity, ease: 'easeInOut' as const } },
  reconnecting: { scale: [1, 1.2, 1], transition: { duration: 1, repeat: Infinity, ease: 'easeInOut' as const } },
  connected: { scale: 1 },
  disconnected: { scale: 1 },
  error: { scale: 1 },
};

export function ConnectionStatus({
  status = 'disconnected',
  className = '',
  showLabel = true,
  compact = false,
  onConnect,
  onDisconnect,
}: ConnectionStatusProps) {
  const config = STATUS_CONFIG[status];
  const prefersReduced = typeof window !== 'undefined' && window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  if (compact) {
    return (
      <motion.div
        className={`flex items-center gap-2 px-3 py-1.5 rounded-full ${className}`}
        variants={statusVariants}
        initial="hidden"
        animate="visible"
        exit="exit"
      >
        <motion.span
          className={`w-2 h-2 rounded-full ${config.bgColor} ${config.ringColor} border-2 flex-shrink-0`}
          animate={dotAnimation[status]}
          transition={{ duration: prefersReduced ? 0 : 1 }}
        />
        {showLabel && <span className={`text-xs font-medium ${config.color}`}>{config.label}</span>}
      </motion.div>
    );
  }

  return (
    <motion.div
      className={`flex items-center gap-3 px-4 py-3 rounded-2xl bg-[var(--c-panel)] dark:bg-[var(--c-panel-dark)] border shadow-sm dark:shadow-none ${config.ringColor} ${className}`}
      variants={statusVariants}
      initial="hidden"
      animate="visible"
      exit="exit"
      role="status"
      aria-live="polite"
      aria-label={`Voice bridge connection status: ${config.label}`}
    >
      <div className="relative flex-shrink-0">
        <motion.span
          className="flex items-center justify-center w-3 h-3 rounded-full border-2 border-[var(--c-hairline)] dark:border-[var(--c-hairline-dark)]"
          animate={dotAnimation[status]}
          transition={{ duration: prefersReduced ? 0 : 1 }}
        >
          <span className={config.color}>{config.icon}</span>
        </motion.span>
        {(status === 'connecting' || status === 'reconnecting') && !prefersReduced && (
          <motion.div
            className="absolute inset-0 rounded-full border-2"
            style={{ borderColor: config.dotHex }}
            animate={{ scale: [1, 1.5], opacity: [0.6, 0] }}
            transition={{ duration: 1.5, repeat: Infinity, ease: 'easeOut' }}
            aria-hidden="true"
          />
        )}
      </div>

      <div className="flex-1 min-w-0">
        <p className={`text-sm font-medium ${config.color}`}>{config.label}</p>
        <p className="text-xs text-[var(--color-text-muted)] truncate">
          {status === 'connected'
            ? 'Voice bridge is active and ready'
            : status === 'connecting' || status === 'reconnecting'
            ? 'Establishing secure WebSocket connection...'
            : status === 'error'
            ? 'Unable to connect. Is the voice bridge running?'
            : 'Click connect to start voice bridge'}
        </p>
      </div>

      {(status === 'disconnected' || status === 'error') && onConnect && (
        <button
          onClick={onConnect}
          className="px-4 py-2 rounded-xl text-sm font-medium bg-[var(--c-brand)] text-white hover:bg-[var(--c-brand)]/90 transition-colors whitespace-nowrap"
          aria-label="Connect to voice bridge"
        >
          Connect
        </button>
      )}

      {status === 'connected' && onDisconnect && (
        <button
          onClick={onDisconnect}
          className="p-2 rounded-xl text-[var(--color-text-muted)] hover:text-[var(--color-text-primary)] dark:hover:text-white hover:bg-[var(--c-hairline)] dark:hover:bg-[var(--c-hairline-dark)] transition-colors"
          aria-label="Disconnect from voice bridge"
        >
          <XCircle className="w-5 h-5" />
        </button>
      )}
    </motion.div>
  );
}

export function ConnectionStatusCompact({
  status = 'disconnected',
  className = '',
}: Omit<ConnectionStatusProps, 'showLabel' | 'compact'>) {
  return <ConnectionStatus status={status} className={className} showLabel={false} compact={true} />;
}
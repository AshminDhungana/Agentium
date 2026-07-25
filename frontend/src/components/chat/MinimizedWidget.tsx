import { motion, useReducedMotion } from 'motion/react';
import { MessageCircle } from 'lucide-react';

interface MinimizedWidgetProps {
  unreadCount: number;
  onClick: () => void;
  reduceMotion: boolean;
}

export function MinimizedWidget({ unreadCount, onClick, reduceMotion }: MinimizedWidgetProps) {
  const reduceMotionPref = useReducedMotion();
  const shouldReduce = reduceMotion || reduceMotionPref;

  return (
    <motion.button
      type="button"
      className="fixed bottom-6 right-8 z-50 flex h-14 items-center gap-2 rounded-full border border-white/10 bg-[var(--color-surface-elevated)] pl-1.5 pr-4 text-[var(--color-text-primary)] shadow-[0_2px_6px_rgba(15,23,42,0.12),0_16px_32px_-8px_rgba(15,23,42,0.35)] outline-none focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-[var(--color-primary)] focus-visible:ring-offset-2 max-[480px]:bottom-4 max-[480px]:right-4"
      aria-label={
        unreadCount > 0
          ? `Resume Agentium Chat, ${unreadCount} unread message${unreadCount === 1 ? '' : 's'}`
          : 'Resume Agentium Chat'
      }
      onClick={onClick}
      whileHover={shouldReduce ? {} : { scale: 1.03 }}
      whileTap={{ scale: 0.96 }}
      initial={shouldReduce ? false : { opacity: 0, scale: 0.85, y: 12 }}
      animate={{ opacity: 1, scale: 1, y: 0 }}
      exit={
        shouldReduce
          ? { opacity: 0 }
          : { opacity: 0, scale: 0.85, y: 8, transition: { duration: 0.15 } }
      }
      transition={{ type: 'spring', stiffness: 300, damping: 26 }}
    >
      <span className="relative flex h-11 w-11 shrink-0 items-center justify-center rounded-full bg-[var(--color-primary)] text-white">
        <MessageCircle className="h-4 w-4" aria-hidden="true" />
        {unreadCount > 0 && (
          <motion.span
            className="absolute -top-1 -right-1 flex h-4 min-w-[16px] items-center justify-center rounded-full bg-[var(--color-destructive)] px-1 text-[10px] font-semibold leading-none text-white"
            animate={shouldReduce ? {} : { scale: [1, 1.15, 1] }}
            transition={{ duration: 1, repeat: Infinity, ease: 'easeInOut' }}
          >
            {unreadCount > 9 ? '9+' : unreadCount}
          </motion.span>
        )}
      </span>
      <span className="whitespace-nowrap text-sm font-medium">
        {unreadCount > 0 ? `${unreadCount} new message${unreadCount === 1 ? '' : 's'}` : 'Resume chat'}
      </span>
    </motion.button>
  );
}
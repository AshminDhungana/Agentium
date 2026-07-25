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
      className="floating-chat-minimized"
      role="button"
      tabIndex={0}
      aria-label="Open Agentium Chat"
      onClick={onClick}
      whileHover={{ scale: 1.05 }}
      whileTap={{ scale: 0.95 }}
      initial={shouldReduce ? undefined : { scale: 0, rotate: -90 }}
      animate={shouldReduce ? undefined : { scale: 1, rotate: 0 }}
      transition={{ type: 'spring', stiffness: 250, damping: 25 }}
    >
      <MessageCircle className="w-6 h-6" aria-hidden="true" />

      {unreadCount > 0 && (
        <motion.span
          className="floating-chat-badge"
          animate={shouldReduce ? {} : { scale: [1, 1.2, 1] }}
          transition={{ duration: 1, repeat: Infinity, ease: 'easeInOut' }}
        >
          {unreadCount > 9 ? '9+' : unreadCount}
        </motion.span>
      )}
    </motion.button>
  );
}
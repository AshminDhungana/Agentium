import { useState } from 'react';
import { motion, AnimatePresence, type Variant } from 'framer-motion';
import { MessageSquare, ChevronUp, X } from 'lucide-react';
import { WidgetCard } from '@/components/dashboard/WidgetCard';
import { TranscriptDisplay } from './TranscriptDisplay';
import { useReducedMotion } from './hooks/useReducedMotion';
import { useBreakpoint } from './hooks/useBreakpoint';
import type { TranscriptEntry } from './types';

interface TranscriptDrawerProps {
  transcripts: TranscriptEntry[];
  className?: string;
}

export function TranscriptDrawer({ transcripts, className = '' }: TranscriptDrawerProps) {
  const [isOpen, setIsOpen] = useState(false);
  const { prefersReduced } = useReducedMotion();
  const breakpoint = useBreakpoint();

  const handleToggle = () => setIsOpen(!isOpen);
  const handleClose = () => setIsOpen(false);

  // Responsive configuration per breakpoint
  const isMobile = breakpoint === 'mobile';
  const isTablet = breakpoint === 'tablet';
  const isDesktopSm = breakpoint === 'desktop-sm';
  const isDesktopLg = breakpoint === 'desktop-lg';

  // Responsive dimensions
  const panelWidth = isDesktopLg ? 384 : isDesktopSm ? 320 : isTablet ? '100%' : '100%';
  const panelHeight = isMobile ? '60vh' : isTablet ? '50vh' : '60vh';
  const panelBottom = isMobile ? 0 : isTablet ? '80px' : '24px';
  const panelLeft = isMobile ? 0 : isTablet ? 0 : '24px';
  const panelRight = isMobile ? 0 : isTablet ? 0 : undefined;
  const panelBorderRadius = (isMobile || isTablet) ? 'rounded-t-2xl' : 'rounded-2xl';

  // Spring transition config
  const springTransition = { type: 'spring' as const, stiffness: 300, damping: 30 };
  const tweenTransition = { type: 'tween' as const };

  // Animation variants
  const panelVariants = {
    hidden: { opacity: 0, y: isMobile ? '100%' : 30, scale: 0.98 },
    visible: {
      opacity: 1,
      y: 0,
      scale: 1,
      transition: prefersReduced ? tweenTransition : springTransition
    },
    exit: {
      opacity: 0,
      y: isMobile ? '100%' : 30,
      scale: 0.98,
      transition: { duration: prefersReduced ? 0.15 : 0.2 }
    },
  } satisfies Record<string, Variant>;

  const handleVariants = {
    hidden: { opacity: 0, x: -30 },
    visible: {
      opacity: 1,
      x: 0,
      transition: { ...(prefersReduced ? tweenTransition : springTransition), delay: 0.5 }
    },
  } satisfies Record<string, Variant>;

  return (
    <div className={`fixed bottom-6 left-6 z-20 ${className}`}>
      {/* Collapsed handle button - hidden on mobile/tablet when open */}
      {!isMobile && !isTablet && (
        <motion.button
          className="glass-pill flex items-center gap-2 px-4 py-2"
          variants={handleVariants}
          initial="hidden"
          animate="visible"
          onClick={handleToggle}
          aria-expanded={isOpen}
          aria-controls="transcript-drawer-panel"
          aria-label={isOpen ? 'Close transcript' : 'Open transcript'}
        >
          <MessageSquare className="w-5 h-5" aria-hidden="true" />
          <span className="hidden sm:inline ml-2 text-sm font-medium text-[var(--color-text-primary)]">Transcript</span>
          <motion.span
            className="ml-1"
            animate={{ rotate: isOpen ? 180 : 0 }}
            transition={{ type: prefersReduced ? 'tween' : 'spring', stiffness: 300, damping: 30 }}
          >
            <ChevronUp className="w-4 h-4" aria-hidden="true" />
          </motion.span>
        </motion.button>
      )}

      {/* Expanded floating panel / bottom sheet / modal drawer */}
      <AnimatePresence>
        {isOpen && (
          <motion.div
            id="transcript-drawer-panel"
            className={`fixed z-20 ${panelBorderRadius} transition-all duration-200 ${className}`}
            style={{
              width: typeof panelWidth === 'number' ? `${panelWidth}px` : panelWidth,
              maxHeight: panelHeight,
              bottom: panelBottom,
              left: panelLeft,
              right: panelRight,
            }}
            initial="hidden"
            animate="visible"
            exit="exit"
            variants={panelVariants}
            role="region"
            aria-label="Conversation transcript"
          >
            <WidgetCard title="Conversation" icon={MessageSquare} className={`flex flex-col h-full ${isMobile || isTablet ? 'bg-[var(--c-panel)] shadow-xl' : 'bg-[var(--c-glass-bg)] border border-[var(--c-glass-border)] backdrop-blur-xl'}`}>
              {isMobile && (
                <div className="flex items-center justify-between mb-2 pb-2 border-b border-[var(--c-hairline)]">
                  <span className="text-sm font-medium text-[var(--color-text-secondary)]">Conversation</span>
                  <motion.button
                    onClick={handleClose}
                    className="p-1 rounded-lg hover:bg-[var(--c-subtle)] transition-colors"
                    aria-label="Close transcript"
                    whileTap={{ scale: 0.9 }}
                  >
                    <X className="w-5 h-5" aria-hidden="true" />
                  </motion.button>
                </div>
              )}
              <TranscriptDisplay transcripts={transcripts} maxHeight={isMobile ? 320 : 400} className="flex-1" />
            </WidgetCard>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Mobile/Tablet: Floating action button to open transcript when closed */}
      {(isMobile || isTablet) && !isOpen && (
        <motion.button
          className="fixed bottom-6 right-6 z-20 glass-pill p-3 shadow-xl"
          initial={{ opacity: 0, scale: 0.9 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ type: prefersReduced ? 'tween' : 'spring', stiffness: 300, damping: 30, delay: 0.5 }}
          onClick={handleToggle}
          aria-label="Open transcript"
          aria-expanded={false}
        >
          <MessageSquare className="w-6 h-6 text-[var(--color-text-primary)]" aria-hidden="true" />
        </motion.button>
      )}
    </div>
  );
}
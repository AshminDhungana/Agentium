import { motion, AnimatePresence, type Variants } from 'framer-motion';
import { Copy, MessageSquare, X } from 'lucide-react';
import { useState, useRef, useEffect, useCallback } from 'react';
import type { TranscriptDisplayProps, TranscriptEntry } from './types';
import { EmptyState } from '@/components/ui/EmptyState';

const transcriptVariants: Variants = {
  hidden: { opacity: 0, y: 20, scale: 0.98 },
  visible: {
    opacity: 1,
    y: 0,
    scale: 1,
    transition: { type: 'spring' as const, stiffness: 300, damping: 30 },
  },
  exit: { opacity: 0, y: -10, scale: 0.98, transition: { duration: 0.2 } },
};

const bubbleVariants: Variants = {
  hidden: { opacity: 0, scale: 0.9, y: 10 },
  visible: {
    opacity: 1,
    scale: 1,
    y: 0,
    transition: { type: 'spring' as const, stiffness: 400, damping: 30, delay: 0.1 },
  },
};

const streamingVariants: Variants = {
  hidden: { width: 0, opacity: 0 },
  visible: (i: number) => ({
    width: 'auto',
    opacity: 1,
    transition: { delay: i * 0.02, duration: 0.05, ease: 'linear' as const },
  }),
};

export function TranscriptDisplay({
  transcripts = [],
  className = '',
  maxHeight = 400,
}: TranscriptDisplayProps) {
  const [copiedTooltip, setCopiedTooltip] = useState<{ index: number; timeout: NodeJS.Timeout } | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const prefersReduced = typeof window !== 'undefined' && window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  const scrollToBottom = useCallback(() => {
    if (containerRef.current) {
      containerRef.current.scrollTop = containerRef.current.scrollHeight;
    }
  }, []);

  useEffect(() => {
    scrollToBottom();
  }, [transcripts.length, scrollToBottom]);

  const handleCopy = (text: string, index: number) => {
    navigator.clipboard.writeText(text);
    setCopiedIndex(index);
    if (copiedTooltip) clearTimeout(copiedTooltip.timeout);
    const timeout = setTimeout(() => {
      setCopiedIndex(null);
      setCopiedTooltip(null);
    }, 2000);
    setCopiedTooltip({ index, timeout });
  };

  const [copiedIndex, setCopiedIndex] = useState<number | null>(null);

  if (transcripts.length === 0) {
    return (
      <div className={`flex flex-col items-center justify-center h-full text-center p-8 ${className}`} role="status" aria-live="polite">
        <EmptyState
          illustration="inbox"
          icon={MessageSquare}
          title="No conversation yet"
          description="Start speaking to see transcripts here"
          size="md"
        />
      </div>
    );
  }

  return (
    <div
      ref={containerRef}
      className={`flex flex-col gap-3 overflow-y-auto pr-2 ${className} bg-[var(--c-panel)]/50 backdrop-blur-md border border-[var(--c-hairline)] rounded-2xl p-4`}
      style={{ maxHeight: maxHeight }}
      role="log"
      aria-live="polite"
      aria-label="Conversation transcript"
      tabIndex={0}
    >
      <AnimatePresence>
        {transcripts.map((entry, index) => (
          <motion.div
            key={`${entry.id}-${index}`}
            variants={transcriptVariants}
            initial="hidden"
            animate="visible"
            exit="exit"
            className="w-full"
          >
            <motion.div
              variants={bubbleVariants}
              className={`flex flex-col gap-1 max-w-[85%] ${
                entry.speaker === 'user' ? 'ml-auto items-end' : 'mr-auto items-start'
              }`}
            >
              <div className="flex items-center gap-2 text-xs">
                <span
                  className={`font-medium px-2 py-0.5 rounded-full ${
                    entry.speaker === 'user'
                      ? 'bg-[var(--c-brand)]/15 text-[var(--c-brand)] dark:text-[var(--c-brand-light)] border border-[var(--c-brand)]/20'
                      : 'bg-[var(--c-brand-2)]/15 text-[var(--c-brand-2)] dark:text-[var(--c-brand-2-light)] border border-[var(--c-brand-2)]/20'
                  }`}
                >
                  {entry.speaker === 'user' ? 'You' : 'Agentium'}
                </span>
                <time className="text-[var(--color-text-muted)]" dateTime={entry.timestamp.toISOString()}>
                  {entry.timestamp.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                </time>
                {entry.isStreaming && (
                  <span className="flex items-center gap-1 text-[var(--c-warning)] dark:text-[var(--c-warning-light)] text-xs">
                    <span className="w-1.5 h-1.5 rounded-full bg-[var(--c-warning)] dark:bg-[var(--c-warning-light)] animate-pulse" />
                    Streaming...
                  </span>
                )}
              </div>
              <div className="relative group">
                <div
                  className={`px-4 py-2.5 rounded-2xl ${
                    entry.speaker === 'user'
                      ? 'bg-[var(--c-brand)]/10 dark:bg-[var(--c-brand)]/20 text-[var(--color-text-primary)] border border-[var(--c-brand)]/20 rounded-br-md'
                      : 'bg-[var(--c-subtle)] dark:bg-[var(--c-subtle-dark)] text-[var(--color-text-primary)] border border-[var(--c-hairline)] rounded-bl-md'
                  } whitespace-pre-wrap break-words`}
                >
                  {entry.isStreaming ? (
                    <AnimatePresence>
                      {entry.text.split('').map((char, charIndex) => (
                        <motion.span
                          key={`${entry.id}-${charIndex}`}
                          variants={streamingVariants}
                          initial="hidden"
                          animate="visible"
                          custom={charIndex}
                        >
                          {char}
                        </motion.span>
                      ))}
                    </AnimatePresence>
                  ) : (
                    entry.text
                  )}
                </div>
                <div className="absolute top-1 right-1 opacity-0 group-hover:opacity-100 transition-opacity flex items-center gap-1">
                  <button
                    onClick={() => handleCopy(entry.text, index)}
                    className="relative p-1.5 rounded-lg bg-[var(--c-panel)]/80 dark:bg-[var(--c-panel)]/50 hover:bg-[var(--c-subtle)] dark:hover:bg-[var(--c-subtle-dark)] text-[var(--color-text-muted)] hover:text-[var(--color-text-primary)] transition-colors shadow-sm"
                    aria-label="Copy message"
                  >
                    {copiedIndex === index ? (
                      <motion.span
                        initial={{ opacity: 0, scale: 0.5, y: -10 }}
                        animate={{ opacity: 1, scale: 1, y: 0 }}
                        exit={{ opacity: 0, scale: 0.5, y: -10 }}
                        className="absolute -top-6 left-1/2 -translate-x-1/2 whitespace-nowrap px-2 py-1 text-xs bg-[var(--c-success)] text-white rounded"
                      >
                        Copied!
                      </motion.span>
                    ) : (
                      <Copy className="w-3.5 h-3.5" />
                    )}
                  </button>
                </div>
              </div>
            </motion.div>
          </motion.div>
        ))}
      </AnimatePresence>
      <div
        ref={(el) => {
          if (el && typeof el.scrollIntoView === 'function') {
            el.scrollIntoView();
          }
        }}
      />
    </div>
  );
}

export function TranscriptEntryItem({
  entry,
  onCopy,
  copiedId,
}: {
  entry: TranscriptEntry;
  onCopy: (text: string) => void;
  copiedId: string | null;
}) {
  return (
    <motion.div
      variants={bubbleVariants}
      initial="hidden"
      animate="visible"
      className={`flex flex-col gap-1 max-w-[85%] ${
        entry.speaker === 'user' ? 'ml-auto items-end' : 'mr-auto items-start'
      }`}
    >
      <div className="flex items-center gap-2 text-xs">
        <span
          className={`font-medium px-2 py-0.5 rounded-full ${
            entry.speaker === 'user'
              ? 'bg-[var(--c-brand)]/15 text-[var(--c-brand)] dark:text-[var(--c-brand-light)]'
              : 'bg-[var(--c-brand-2)]/15 text-[var(--c-brand-2)] dark:text-[var(--c-brand-2-light)]'
          }`}
        >
          {entry.speaker === 'user' ? 'You' : 'Agentium'}
        </span>
        <time className="text-[var(--color-text-muted)]" dateTime={entry.timestamp.toISOString()}>
          {entry.timestamp.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
        </time>
      </div>
      <div className="relative group">
        <div
          className={`px-4 py-2.5 rounded-2xl ${
            entry.speaker === 'user'
              ? 'bg-[var(--c-brand)]/10 dark:bg-[var(--c-brand)]/20 text-[var(--color-text-primary)] border border-[var(--c-brand)]/20 rounded-br-md'
              : 'bg-[var(--c-subtle)] dark:bg-[var(--c-subtle-dark)] text-[var(--color-text-primary)] border border-[var(--c-hairline)] rounded-bl-md'
          } whitespace-pre-wrap break-words`}
        >
          {entry.text}
        </div>
        <div className="absolute top-1 right-1 opacity-0 group-hover:opacity-100 transition-opacity">
          <button
            onClick={() => onCopy(entry.text)}
            className="p-1.5 rounded-lg bg-[var(--c-panel)]/80 dark:bg-[var(--c-panel)]/50 hover:bg-[var(--c-subtle)] dark:hover:bg-[var(--c-subtle-dark)] text-[var(--color-text-muted)] hover:text-[var(--color-text-primary)] transition-colors shadow-sm"
            aria-label="Copy message"
          >
            {copiedId === entry.id ? <X className="w-3.5 h-3.5 text-[var(--c-success)] dark:text-[var(--c-success-light)]" /> : <Copy className="w-3.5 h-3.5" />}
          </button>
        </div>
      </div>
    </motion.div>
  );
}
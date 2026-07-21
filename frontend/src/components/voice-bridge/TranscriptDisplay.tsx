import { motion, AnimatePresence, type Variants } from 'framer-motion';
import { Copy, Trash2, X } from 'lucide-react';
import { useState, useRef, useEffect, useCallback } from 'react';
import type { TranscriptDisplayProps, TranscriptEntry } from './types';

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
  const [copiedIndex, setCopiedIndex] = useState<number | null>(null);
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
    setTimeout(() => setCopiedIndex(null), 2000);
  };

  const handleClear = () => {
    // This will be handled by parent via onClear prop if needed
    window.dispatchEvent(new CustomEvent('voice-bridge-clear-transcripts'));
  };

  if (transcripts.length === 0) {
    return (
      <div
        className={`flex flex-col items-center justify-center h-full text-center p-8 ${className}`}
        role="status"
        aria-live="polite"
      >
        <div className="w-16 h-16 rounded-2xl bg-white/5 border border-white/10 flex items-center justify-center mb-4">
          <svg className="w-8 h-8 text-gray-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
          </svg>
        </div>
        <p className="text-gray-400 text-sm font-medium">No conversation yet</p>
        <p className="text-gray-600 text-xs mt-1">Start speaking to see transcripts here</p>
      </div>
    );
  }

  return (
    <div
      ref={containerRef}
      className={`flex flex-col gap-3 overflow-y-auto pr-2 ${className}`}
      style={{ maxHeight: maxHeight }}
      role="log"
      aria-live="polite"
      aria-label="Conversation transcript"
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
                      ? 'bg-blue-500/20 text-blue-300'
                      : 'bg-purple-500/20 text-purple-300'
                  }`}
                >
                  {entry.speaker === 'user' ? 'You' : 'Agentium'}
                </span>
                <time className="text-gray-500" dateTime={entry.timestamp.toISOString()}>
                  {entry.timestamp.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                </time>
                {entry.isStreaming && (
                  <span className="flex items-center gap-1 text-amber-400 text-xs">
                    <span className="w-1.5 h-1.5 rounded-full bg-amber-400 animate-pulse" />
                    Streaming...
                  </span>
                )}
              </div>
              <div className="relative group">
                <div
                  className={`px-4 py-2.5 rounded-2xl ${
                    entry.speaker === 'user'
                      ? 'bg-blue-500/15 text-blue-100 border border-blue-500/20 rounded-br-md'
                      : 'bg-white/5 text-white border border-white/10 rounded-bl-md'
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
                    className="p-1.5 rounded-lg bg-white/5 hover:bg-white/10 text-gray-400 hover:text-white transition-colors"
                    aria-label="Copy message"
                    title="Copy"
                  >
                    {copiedIndex === index ? (
                      <X className="w-3.5 h-3.5 text-green-400" />
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
      <div ref={(el) => { if (el) el.scrollIntoView(); }} />
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
              ? 'bg-blue-500/20 text-blue-300'
              : 'bg-purple-500/20 text-purple-300'
          }`}
        >
          {entry.speaker === 'user' ? 'You' : 'Agentium'}
        </span>
        <time className="text-gray-500" dateTime={entry.timestamp.toISOString()}>
          {entry.timestamp.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
        </time>
      </div>
      <div className="relative group">
        <div
          className={`px-4 py-2.5 rounded-2xl ${
            entry.speaker === 'user'
              ? 'bg-blue-500/15 text-blue-100 border border-blue-500/20 rounded-br-md'
              : 'bg-white/5 text-white border border-white/10 rounded-bl-md'
          } whitespace-pre-wrap break-words`}
        >
          {entry.text}
        </div>
        <div className="absolute top-1 right-1 opacity-0 group-hover:opacity-100 transition-opacity">
          <button
            onClick={() => onCopy(entry.text)}
            className="p-1.5 rounded-lg bg-white/5 hover:bg-white/10 text-gray-400 hover:text-white transition-colors"
            aria-label="Copy message"
          >
            {copiedId === entry.id ? <X className="w-3.5 h-3.5 text-green-400" /> : <Copy className="w-3.5 h-3.5" />}
          </button>
        </div>
      </div>
    </motion.div>
  );
}
import { motion, useReducedMotion } from 'motion/react';
import { useRef, useEffect } from 'react';
import { MessageCircle } from 'lucide-react';
import { MarkdownMessage } from '@/components/chat/MarkdownMessage';
import type { Message } from '@/store/chatStore';

interface MessageListProps {
  messages: Message[];
  reduceMotion: boolean;
}

export function MessageList({ messages, reduceMotion }: MessageListProps) {
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const messagesContainerRef = useRef<HTMLDivElement>(null);
  const reduceMotionPref = useReducedMotion();

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: reduceMotion || reduceMotionPref ? 'auto' : 'smooth' });
  };

  useEffect(() => {
    const container = messagesContainerRef.current;
    if (!container) return;
    const nearBottom = container.scrollHeight - container.scrollTop - container.clientHeight < 80;
    if (nearBottom) scrollToBottom();
  }, [messages]);

  if (messages.length === 0) {
    return (
      <div className="flex flex-1 flex-col items-center justify-center gap-2 px-6 py-10 text-center">
        <div className="flex h-11 w-11 items-center justify-center rounded-full bg-[var(--color-muted)] text-[var(--color-text-muted)]">
          <MessageCircle className="h-5 w-5" aria-hidden="true" />
        </div>
        <p className="text-sm font-medium text-[var(--color-text-primary)]">Start a conversation</p>
        <p className="max-w-[220px] text-xs text-[var(--color-text-muted)]">
          Ask Agentium anything — questions, tasks, or just say hello.
        </p>
      </div>
    );
  }

  return (
    <div
      ref={messagesContainerRef}
      className="floating-chat-messages"
      role="log"
      aria-live="polite"
      aria-label="Chat messages"
    >
      <motion.div
        initial={false}
        animate={{ opacity: 1 }}
        transition={{ staggerChildren: reduceMotion || reduceMotionPref ? 0 : 0.05 }}
      >
        {messages.map((msg) => {
          const isUser = msg.role === 'sovereign';
          return (
            <motion.div
              key={msg.id}
              className={`mb-2 flex last:mb-0 ${isUser ? 'justify-end' : 'justify-start'}`}
              variants={{
                hidden: { opacity: 0, y: 20 },
                visible: { opacity: 1, y: 0 },
              }}
              initial="hidden"
              animate="visible"
            >
              <div
                className={`max-w-[85%] rounded-2xl px-3.5 py-2.5 shadow-sm ${
                  isUser
                    ? 'rounded-br-md bg-[var(--color-primary)] text-white'
                    : 'rounded-bl-md border border-[var(--color-border)] bg-[var(--color-muted)] text-[var(--color-text-primary)]'
                }`}
              >
                <MarkdownMessage content={msg.content} isUser={isUser} status={msg.status} />
              </div>
            </motion.div>
          );
        })}
      </motion.div>
      <div ref={messagesEndRef} />
    </div>
  );
}
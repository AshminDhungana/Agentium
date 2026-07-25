import { motion, useReducedMotion } from 'motion/react';
import { useRef, useEffect } from 'react';
import { MarkdownMessage } from '@/components/chat/MarkdownMessage';
import { TypingIndicator } from '@/components/chat/TypingIndicator';
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
      <div className="floating-chat-empty">
        <p>No messages yet. Start a conversation!</p>
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
{messages.map((msg, index) => (
            <motion.div
              key={msg.id}
              className={`floating-chat-message ${msg.role}`}
              variants={{
                hidden: { opacity: 0, y: 20 },
                visible: { opacity: 1, y: 0 },
              }}
              initial="hidden"
              animate="visible"
            >
              <MarkdownMessage
                content={msg.content}
                isUser={msg.role === 'sovereign'}
                status={msg.status}
              />
            </motion.div>
          ))}
      </motion.div>
      <div ref={messagesEndRef} />
    </div>
  );
}
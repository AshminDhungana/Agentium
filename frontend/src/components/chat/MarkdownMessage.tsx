import { useEffect, useMemo, useRef, useState } from 'react';
import { marked } from 'marked';
import { sanitizeMarkdown } from '../../utils/markdown/sanitizeMarkdown';
import styles from './MarkdownMessage.module.css';

marked.setOptions({ breaks: true, gfm: true });

interface MarkdownMessageProps {
  content: string;
  className?: string;
  isUser?: boolean;
  status?: string;
  role?: string;
}

/**
 * Renders backend/LLM markdown safely in chat bubbles.
 * - Non-user messages are parsed with `marked` and sanitized with `DOMPurify`.
 * - User messages are rendered as plain text (never markdown-parsed).
 * - Fenced code blocks get an overlay copy button (vector icon, no layout shift).
 * - If parsing fails, falls back to plain text (never blank).
 */
export function MarkdownMessage({
  content,
  className = '',
  isUser = false,
  status,
}: MarkdownMessageProps) {
  const ref = useRef<HTMLDivElement>(null);

  // Compute sanitized HTML (empty string = plain-text fallback).
  const html = useMemo(() => {
    if (isUser) return '';
    try {
      const parsed = marked.parse(content, { async: false }) as string;
      return sanitizeMarkdown(parsed);
    } catch {
      return '';
    }
  }, [content, isUser]);

  const isPlain = isUser || html === '';

  // Attach a copy button to every <pre> block. No-op when rendering plain text.
  useEffect(() => {
    if (isPlain) return;
    const root = ref.current;
    if (!root) return;
    const pres = Array.from(root.querySelectorAll('pre'));
    const cleanups: Array<() => void> = [];

    pres.forEach((pre) => {
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.setAttribute('aria-label', 'Copy code');
      btn.className =
        'absolute right-2 top-2 p-1 rounded-md text-gray-500 dark:text-gray-400 ' +
        'opacity-0 group-hover/code:opacity-100 focus-visible:opacity-100 transition-opacity ' +
        'hover:bg-gray-100 dark:hover:bg-[#1e2535]';
      const code = pre.querySelector('code')?.textContent ?? pre.textContent ?? '';
      btn.addEventListener('click', () => {
        navigator.clipboard?.writeText(code).catch(() => {
          /* clipboard blocked — silent no-op */
        });
      });
      pre.style.position = 'relative';
      pre.classList.add('group/code');
      pre.appendChild(btn);
      cleanups.push(() => btn.remove());
    });

    return () => cleanups.forEach((fn) => fn());
  }, [html, isPlain]);

  if (isPlain) {
    return (
      <p className={`text-[15px] leading-relaxed whitespace-pre-wrap ${className}`}>
        {content}
        {status === 'streaming' && (
          <span data-testid="stream-caret" className={styles['stream-caret']} aria-hidden>
            ▍
          </span>
        )}
      </p>
    );
  }

  return (
    <div className={`markdown-body text-[15px] leading-relaxed ${className}`}>
      <div ref={ref} dangerouslySetInnerHTML={{ __html: html }} />
      {status === 'streaming' && (
        <span data-testid="stream-caret" className={styles['stream-caret']} aria-hidden>
          ▍
        </span>
      )}
    </div>
  );
}

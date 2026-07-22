import { useEffect, useMemo, useRef, useState, useCallback } from 'react';
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
  isCollapsed?: boolean; // controlled collapse state
  /** Test-only: override measured line count */
  testLineCount?: number;
}

/**
 * Renders backend/LLM markdown safely in chat bubbles.
 * - Non-user messages are parsed with `marked` and sanitized with `DOMPurify`.
 * - User messages are rendered as plain text (never markdown-parsed).
 * - Fenced code blocks get an overlay copy button (vector icon, no layout shift).
 * - If parsing fails, falls back to plain text (never blank).
 * - Long messages (>10 lines) collapse with "Show more/less" toggle.
 */
export function MarkdownMessage({
  content,
  className = '',
  isUser = false,
  status,
  isCollapsed: controlledCollapsed,
  testLineCount,
}: MarkdownMessageProps) {
  const contentRef = useRef<HTMLDivElement>(null);
  const ref = useRef<HTMLDivElement>(null); // for backward compat with caret logic

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

  // Soft fade-out: keep the caret mounted briefly after streaming ends so it
  // fades rather than disappearing abruptly. (The harsh `steps(2)` blink was
  // replaced with a gentle pulse in the CSS module.)
  const isStreaming = status === 'streaming';
  const [showCaret, setShowCaret] = useState(isStreaming);
  const [caretFading, setCaretFading] = useState(false);
  useEffect(() => {
    if (isStreaming) {
      setShowCaret(true);
      setCaretFading(false);
    } else if (showCaret && !caretFading) {
      setCaretFading(true);
      const t = setTimeout(() => setShowCaret(false), 260);
      return () => clearTimeout(t);
    }
  }, [isStreaming, showCaret, caretFading]);

  // Collapse/expand state - default to collapsed for long content
  // Use testLineCount if provided (tests), otherwise will be set after measurement
  const initialCollapsed = testLineCount !== undefined ? testLineCount > 10 : false;
  const [isCollapsed, setIsCollapsed] = useState(initialCollapsed);
  const [lineCount, setLineCount] = useState(0);
  const prefersReducedMotionRef = useRef(false);

  // Detect prefers-reduced-motion
  useEffect(() => {
    const mediaQuery = window.matchMedia('(prefers-reduced-motion: reduce)');
    prefersReducedMotionRef.current = mediaQuery.matches;
    const handler = (e: MediaQueryListEvent) => { prefersReducedMotionRef.current = e.matches; };
    mediaQuery.addEventListener('change', handler);
    return () => mediaQuery.removeEventListener('change', handler);
  }, []);

  // Measure content height and line count (runs in effect for real DOM measurement)
  const measureContent = useCallback(() => {
    const el = contentRef.current;
    if (!el) return;
    const lineHeight = parseFloat(getComputedStyle(el).lineHeight) || 24;
    const lines = Math.round(el.scrollHeight / lineHeight);
    setLineCount(lines);
  }, []);

  useEffect(() => {
    measureContent();
    const ro = new ResizeObserver(measureContent);
    if (contentRef.current) ro.observe(contentRef.current);
    return () => ro.disconnect();
  }, [content, measureContent]);

  // Derive shouldCollapse from testLineCount (sync) or lineCount (async from measurement)
  const effectiveLineCount = testLineCount !== undefined ? testLineCount : lineCount;
  const shouldCollapse = effectiveLineCount > 10 && !isUser;

  // Sync with controlled prop if provided
  useEffect(() => {
    if (controlledCollapsed !== undefined) {
      setIsCollapsed(controlledCollapsed);
    }
  }, [controlledCollapsed]);

  const toggleCollapse = () => {
    if (shouldCollapse) setIsCollapsed(prev => !prev);
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      toggleCollapse();
    }
  };

  const maxHeight = (isCollapsed && shouldCollapse && !isStreaming) ? '120px' : 'none';
  const transition = prefersReducedMotionRef.current ? 'none' : 'max-height 200ms ease';

  const renderCaret = () =>
    showCaret ? (
      <span
        data-testid="stream-caret"
        className={`${styles['stream-caret']}${caretFading ? ` ${styles['stream-caret--fading']}` : ''}`}
        aria-hidden
      >
        _
      </span>
    ) : null;

  // Find the element the streaming caret should be appended to so it sits
  // right after the final word instead of wrapping onto its own line.
  // Walks to the deepest last descendant; if that leaf is an inline element
  // (e.g. <strong>), the caret is appended to its parent so it stays inline.
  const lastCaretHost = (root: HTMLElement): HTMLElement => {
    let el: Element | null = root.lastElementChild;
    while (el && el.lastElementChild) el = el.lastElementChild;
    if (!el) return root;
    const display = getComputedStyle(el as HTMLElement).display;
    if (display.startsWith('inline')) return el.parentElement ?? root;
    return el as HTMLElement;
  };

  // Attach a copy button to every <pre> block, and (while streaming) append the
  // caret inline to the last block. No-op when rendering plain text.
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

    // Append the streaming caret inline so it follows the last word instead of
    // wrapping onto its own line (a block-level sibling always forces a break).
    if (showCaret) {
      const host = lastCaretHost(root);
      const caret = document.createElement('span');
      caret.setAttribute('data-testid', 'stream-caret');
      caret.setAttribute('aria-hidden', 'true');
      caret.className =
        styles['stream-caret'] + (caretFading ? ` ${styles['stream-caret--fading']}` : '');
      caret.textContent = '_';
      host.appendChild(caret);
      cleanups.push(() => caret.remove());
    }

    return () => cleanups.forEach((fn) => fn());
  }, [html, isPlain, showCaret, caretFading]);

  if (isPlain) {
    return (
      <p className={`text-[15px] leading-relaxed whitespace-pre-wrap ${className}`}>
        {content}
        {renderCaret()}
      </p>
    );
  }

  return (
    <div
      ref={contentRef}
      role={shouldCollapse ? 'region' : undefined}
      aria-label={shouldCollapse ? 'Message content' : undefined}
      aria-expanded={shouldCollapse ? !isCollapsed : undefined}
      data-collapsed={shouldCollapse ? String(isCollapsed) : undefined}
      data-status={status}
      data-testid="collapsible-message"
      onClick={shouldCollapse ? toggleCollapse : undefined}
      onKeyDown={shouldCollapse ? handleKeyDown : undefined}
      tabIndex={shouldCollapse ? 0 : undefined}
      className={`markdown-body text-[15px] leading-relaxed ${className}`}
      style={{
        maxHeight: maxHeight,
        overflow: shouldCollapse ? 'hidden' : 'visible',
        transition: transition,
        position: 'relative',
      }}
    >
      <div ref={ref} dangerouslySetInnerHTML={{ __html: html }} />
      
      {shouldCollapse && (
        <div className={styles['collapse-fade']} aria-hidden="true" />
      )}
      
      {shouldCollapse && (
        <button
          type="button"
          className={styles['collapse-toggle']}
          onClick={(e) => { e.stopPropagation(); toggleCollapse(); }}
          aria-expanded={!isCollapsed}
          aria-controls={contentRef.current?.id}
        >
          {isCollapsed ? 'Show more' : 'Show less'}
        </button>
      )}
    </div>
  );
}

import DOMPurify from 'dompurify';

const ALLOWED_TAGS = [
  'p', 'strong', 'em', 'u', 'ul', 'ol', 'li',
  'code', 'pre', 'a', 'blockquote', 'h1', 'h2', 'h3', 'h4',
  'br', 'hr', 'span',
];

const ALLOWED_ATTR = ['href', 'title', 'target', 'rel', 'class'];

/**
 * Sanitize raw HTML (produced by marked) for safe injection into chat bubbles.
 * Strips scripts, event handlers, and unsafe URL schemes. Memoized per input.
 */
const cache = new Map<string, string>();

export function sanitizeMarkdown(html: string): string {
  const cached = cache.get(html);
  if (cached !== undefined) return cached;

  const clean = DOMPurify.sanitize(html, {
    ALLOWED_TAGS,
    ALLOWED_ATTR,
    ALLOWED_URI_REGEXP: /^(?:https?|mailto):/i,
  });

  cache.set(html, clean);
  return clean;
}

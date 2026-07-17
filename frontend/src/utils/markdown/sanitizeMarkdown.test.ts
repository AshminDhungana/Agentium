import { describe, it, expect } from 'vitest';
import { sanitizeMarkdown } from './sanitizeMarkdown';

describe('sanitizeMarkdown', () => {
  it('strips <script> tags', () => {
    const out = sanitizeMarkdown('<p>hi</p><script>alert(1)</script>');
    expect(out).not.toContain('<script>');
    expect(out).toContain('<p>hi</p>');
  });

  it('strips on* event handlers', () => {
    const out = sanitizeMarkdown('<img src="x" onerror="alert(1)">');
    expect(out).not.toContain('onerror');
  });

  it('neutralizes javascript: links', () => {
    const out = sanitizeMarkdown('<a href="javascript:alert(1)">click</a>');
    expect(out).not.toContain('javascript:');
  });

  it('preserves safe formatting and links', () => {
    const html = '<h2>Title</h2><p><strong>bold</strong> and <em>italic</em></p><ul><li>a</li></ul><a href="https://x.com">link</a><code>code</code>';
    const out = sanitizeMarkdown(html);
    expect(out).toContain('<h2>Title</h2>');
    expect(out).toContain('<strong>bold</strong>');
    expect(out).toContain('<em>italic</em>');
    expect(out).toContain('<ul><li>a</li></ul>');
    expect(out).toContain('href="https://x.com"');
    expect(out).toContain('<code>code</code>');
  });

  it('forces safe link protocols only', () => {
    const out = sanitizeMarkdown('<a href="mailto:a@b.com">m</a>');
    expect(out).toContain('href="mailto:a@b.com"');
  });
});

import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { MarkdownMessage } from './MarkdownMessage';

describe('MarkdownMessage', () => {
  it('renders headings, bold, and lists from markdown', () => {
    const md = '## Status\n**Done** and a list:\n- one\n- two';
    const { container } = render(<MarkdownMessage content={md} />);
    expect(container.querySelector('h2')?.textContent).toBe('Status');
    expect(container.querySelector('strong')?.textContent).toBe('Done');
    expect(container.querySelectorAll('li')).toHaveLength(2);
  });

  it('neutralizes script content injected via markdown', () => {
    const md = 'Hello\n\n<script>alert(1)</script>';
    const { container } = render(<MarkdownMessage content={md} />);
    expect(container.querySelector('script')).toBeNull();
    expect(screen.getByText('Hello')).toBeInTheDocument();
  });

  it('renders user messages as plain text without markdown parsing', () => {
    const md = '**not bold**';
    const { container } = render(<MarkdownMessage content={md} isUser />);
    expect(container.querySelector('strong')).toBeNull();
    expect(container.textContent).toContain('**not bold**');
  });

  it('renders a copy button for fenced code blocks', () => {
    const md = '```\nconsole.log(1)\n```';
    render(<MarkdownMessage content={md} />);
    expect(screen.getByRole('button', { name: /copy code/i })).toBeInTheDocument();
  });
});

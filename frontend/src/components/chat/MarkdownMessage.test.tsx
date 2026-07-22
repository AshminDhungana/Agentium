import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
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

  it('shows a caret while streaming', () => {
    const { container } = render(
      <MarkdownMessage content="Hello" status="streaming" role="head_of_council" />
    );
    expect(container.querySelector('[data-testid="stream-caret"]')).not.toBeNull();
  });

  it('hides the caret when complete', () => {
    const { container } = render(
      <MarkdownMessage content="Hello" status="sent" role="head_of_council" />
    );
    expect(container.querySelector('[data-testid="stream-caret"]')).toBeNull();
  });

  describe('collapse/expand', () => {
    const longContent = Array(15).fill('This is a test line of content that should wrap.').join('\n\n');

    it('renders collapsed when content exceeds 10 lines', () => {
      // Use testLineCount to simulate > 10 lines
      render(<MarkdownMessage content={longContent} isUser={false} testLineCount={15} />);
      const message = screen.getByTestId('collapsible-message');
      expect(message).toHaveAttribute('data-collapsed', 'true');
      expect(screen.getByText(/show more/i)).toBeInTheDocument();
    });

    it('expands when message is clicked', () => {
      render(<MarkdownMessage content={longContent} isUser={false} testLineCount={15} />);
      const message = screen.getByTestId('collapsible-message');
      expect(message).toHaveAttribute('data-collapsed', 'true');
      fireEvent.click(message);
      expect(message).toHaveAttribute('data-collapsed', 'false');
      expect(screen.getByText(/show less/i)).toBeInTheDocument();
    });

    it('expands when "Show more" button is clicked', () => {
      render(<MarkdownMessage content={longContent} isUser={false} testLineCount={15} />);
      expect(screen.getByTestId('collapsible-message')).toHaveAttribute('data-collapsed', 'true');
      fireEvent.click(screen.getByText(/show more/i));
      expect(screen.getByTestId('collapsible-message')).toHaveAttribute('data-collapsed', 'false');
    });

    it('short content does not show collapse UI', () => {
      render(<MarkdownMessage content="Short message" isUser={false} testLineCount={3} />);
      expect(screen.queryByText(/show more/i)).not.toBeInTheDocument();
      expect(screen.getByTestId('collapsible-message')).not.toHaveAttribute('data-collapsed');
    });

    it('user messages do not collapse', () => {
      render(<MarkdownMessage content={longContent} isUser={true} testLineCount={15} />);
      expect(screen.queryByText(/show more/i)).not.toBeInTheDocument();
      // User messages render as <p> without data-testid, check for content (use regex for newlines)
      expect(screen.getByText(/This is a test line of content/)).toBeInTheDocument();
    });

    it('respects controlled isCollapsed prop', () => {
      const { rerender } = render(<MarkdownMessage content={longContent} isUser={false} isCollapsed={true} testLineCount={15} />);
      expect(screen.getByTestId('collapsible-message')).toHaveAttribute('data-collapsed', 'true');
      rerender(<MarkdownMessage content={longContent} isUser={false} isCollapsed={false} testLineCount={15} />);
      expect(screen.getByTestId('collapsible-message')).toHaveAttribute('data-collapsed', 'false');
    });
  });
});

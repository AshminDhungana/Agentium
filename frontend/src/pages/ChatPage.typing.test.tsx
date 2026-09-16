import { describe, it, expect, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { useChatStore } from '@/store/chatStore';
import { TypingIndicator } from '@/components/chat/TypingIndicator';

describe('ChatPage streaming polish', () => {
    beforeEach(() => {
        useChatStore.setState({ messages: [], activeStreamId: null, currentStreamingMessage: '' });
    });

    it('shows typing indicator for an empty streaming placeholder while awaiting', () => {
        useChatStore.getState().beginStream('s1', 'head_of_council');
        const m = useChatStore.getState().messages[0];
        expect(m.status).toBe('streaming');
        expect(m.content).toBe('');
    });

    it('renders three bouncing dots with the expected test id', () => {
        const { container } = render(<TypingIndicator />);
        const indicator = screen.getByTestId('typing-dots');
        expect(indicator).toBeTruthy();
        expect(indicator.getAttribute('aria-hidden')).toBe('true');
        // Three dot spans (CSS modules mangle classes, so just count descendants)
        expect(container.querySelectorAll('span').length).toBe(3);
    });

    it('shows tool count when toolCount > 0', () => {
        const { container } = render(<TypingIndicator toolCount={2} />);
        expect(container.textContent).toContain('Running tools: 2');
    });

    it('hides tool count when toolCount is 0', () => {
        const { container } = render(<TypingIndicator toolCount={0} />);
        expect(container.textContent).not.toContain('Running tools');
    });

    it('hides tool count when toolCount is undefined', () => {
        const { container } = render(<TypingIndicator />);
        expect(container.textContent).not.toContain('Running tools');
    });

    it('shows thinking label when thinking prop is true', () => {
        const { container } = render(<TypingIndicator thinking />);
        expect(container.textContent).toContain('Thinking');
    });

    it('shows tool names when provided', () => {
        const { container } = render(<TypingIndicator toolNames={['web_search', 'file_read']} />);
        expect(container.textContent).toContain('Running: web_search, file_read');
    });

    it('truncates tool names when more than 3', () => {
        const { container } = render(<TypingIndicator toolNames={['a', 'b', 'c', 'd']} />);
        expect(container.textContent).toContain('+1 more');
    });
});

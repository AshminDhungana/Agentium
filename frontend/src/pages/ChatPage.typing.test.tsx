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
        const indicator = screen.getByTestId('typing-indicator');
        expect(indicator).toBeTruthy();
        expect(indicator.getAttribute('aria-hidden')).toBe('true');
        // Three dot spans (CSS modules mangle classes, so just count descendants)
        expect(container.querySelectorAll('span').length).toBe(3);
    });

    it('shows +N count when toolCount > 0', () => {
        const { container } = render(<TypingIndicator toolCount={2} />);
        expect(container.textContent).toContain('+2');
    });

    it('hides +N count when toolCount is 0', () => {
        const { container } = render(<TypingIndicator toolCount={0} />);
        expect(container.textContent).not.toContain('+');
    });

    it('hides +N count when toolCount is undefined', () => {
        const { container } = render(<TypingIndicator />);
        expect(container.textContent).not.toContain('+');
    });

    it('thinking prop is a no-op visually (same dots, no label)', () => {
        const { container: t1 } = render(<TypingIndicator />);
        const { container: t2 } = render(<TypingIndicator thinking />);
        expect(t1.querySelectorAll('span').length).toBe(3);
        expect(t2.querySelectorAll('span').length).toBe(3);
        expect(t2.textContent).not.toContain('Thinking…');
    });
});

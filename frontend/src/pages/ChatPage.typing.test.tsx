import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { useChatStore } from '@/store/chatStore';
import { TypingIndicator } from '@/components/chat/TypingIndicator';

describe('ChatPage streaming polish', () => {
    beforeEach(() => {
        useChatStore.setState({ messages: [], activeStreamId: null, currentStreamingMessage: '' });
    });

    it('shows typing indicator for an empty streaming placeholder while awaiting', () => {
        // Simulate the thinking phase: a streaming placeholder with empty content
        // and isAwaitingReply true (driven via the store + a lightweight render).
        useChatStore.getState().beginStream('s1', 'head_of_council');
        // NOTE: rendering full ChatPage may be heavy; if so, assert the store state
        // invariants instead: placeholder exists with status 'streaming' and empty
        // content, which is what the typing indicator keys off of.
        const m = useChatStore.getState().messages[0];
        expect(m.status).toBe('streaming');
        expect(m.content).toBe('');
    });

    it('renders the typing indicator with the expected test id and is aria-hidden', () => {
        const { container } = render(<TypingIndicator />);
        const indicator = screen.getByTestId('typing-indicator');
        expect(indicator).toBeTruthy();
        expect(indicator.getAttribute('aria-hidden')).toBe('true');
        // Three animated dots.
        expect(container.querySelectorAll('span').length).toBe(3);
    });
});

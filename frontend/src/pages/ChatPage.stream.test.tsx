/**
 * ChatPage.stream.test.tsx
 *
 * Task 8: verifies the chatStore streaming helpers that ChatPage now drives
 * from the WS subscriber (beginStream / appendDelta / endStream), and the
 * Stop button wiring contract.
 *
 * The WS subscriber itself is hard to unit-test in isolation, so the mandatory
 * assertions below exercise `useChatStore` directly (the exact helpers the
 * subscriber calls). The Stop button is validated against a tiny extracted
 * harness component that mirrors ChatPage's wiring (mounting the full ChatPage
 * is too heavy here), as permitted by the task fallback.
 */

import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { useChatStore } from '@/store/chatStore';
import { useWebSocketStore } from '@/store/websocketStore';

// ── Store-driven assertions (MANDATORY, real) ────────────────────────────────

describe('chatStore streaming helpers (driven by ChatPage WS subscriber)', () => {
    beforeEach(() => {
        // Reset to a clean slate before each case.
        useChatStore.setState({
            messages: [],
            activeStreamId: null,
            currentStreamingMessage: '',
            cardStatus: {},
            activeCardId: null,
        });
    });

    it('beginStream creates a streaming placeholder with empty content', () => {
        useChatStore.getState().beginStream('s1', 'head_of_council');

        const m = useChatStore.getState().messages.find((x) => x.id === 's1');
        expect(m).toBeDefined();
        expect(m!.content).toBe('');
        expect(m!.status).toBe('streaming');
        expect(useChatStore.getState().activeStreamId).toBe('s1');
    });

    it('appendDelta accumulates content', () => {
        useChatStore.getState().beginStream('s1', 'head_of_council');
        useChatStore.getState().appendDelta('s1', 'Hello');

        const m = useChatStore.getState().messages.find((x) => x.id === 's1');
        expect(m!.content).toBe('Hello');
    });

    it('endStream finalizes status, merges metadata, and clears activeStreamId', () => {
        useChatStore.getState().beginStream('s1', 'head_of_council');
        useChatStore.getState().appendDelta('s1', 'Hello');
        useChatStore.getState().endStream('s1', 'Hello', { model: 'm' });

        const m = useChatStore.getState().messages.find((x) => x.id === 's1');
        expect(m!.status).toBe('sent');
        expect(m!.metadata?.model).toBe('m');
        expect(useChatStore.getState().activeStreamId).toBeNull();
    });
});

// ── Stop button wiring (extracted harness fallback) ──────────────────────────
//
// NOTE: The real ChatPage Stop button sends the `cancel` frame directly over
// the open socket (useWebSocketStore.getState()._ws.send(...)) because the WS
// store's `sendMessage` only emits `type:'message'` frames and the store must
// not be modified. This harness asserts the wiring contract: when an
// activeStreamId is set the button renders and invokes sendWsMessage with
// { type:'cancel', stream_id }.

function StopButtonHarness({ sendWsMessage }: { sendWsMessage: (payload: unknown) => void }) {
    const activeStreamId = useChatStore((s) => s.activeStreamId);
    if (!activeStreamId) return null;
    return (
        <button
            type="button"
            aria-label="Stop generating"
            onClick={() => sendWsMessage({ type: 'cancel', stream_id: activeStreamId })}
        >
            Stop
        </button>
    );
}

describe('Stop button wiring', () => {
    beforeEach(() => {
        useChatStore.setState({ activeStreamId: null });
    });

    it('does not render when no active stream', () => {
        render(<StopButtonHarness sendWsMessage={() => {}} />);
        expect(screen.queryByRole('button', { name: 'Stop generating' })).toBeNull();
    });

    it('calls sendWsMessage with { type:"cancel", stream_id } when active', () => {
        useChatStore.setState({ activeStreamId: 's9' });
        const sendWsMessage = vi.fn();
        render(<StopButtonHarness sendWsMessage={sendWsMessage} />);

        const btn = screen.getByRole('button', { name: 'Stop generating' });
        fireEvent.click(btn);

        expect(sendWsMessage).toHaveBeenCalledTimes(1);
        expect(sendWsMessage).toHaveBeenCalledWith({ type: 'cancel', stream_id: 's9' });
    });
});

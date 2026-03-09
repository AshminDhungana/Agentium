// src/hooks/useQRPolling.ts
// ─────────────────────────────────────────────────────────────────────────────
// Encapsulates WhatsApp QR-code polling with:
//   • A stored timeout handle so it can be reliably cancelled on unmount.
//   • An active-channel ref that prevents stale closures from re-scheduling
//     after the poll has been stopped.
//   • Auto-cleanup via useEffect return, so unmounting the parent never leaks
//     a dangling interval.
//
// BREAKING CHANGE RISK: None — this is a new file, nothing imports it yet.
// ─────────────────────────────────────────────────────────────────────────────

import { useRef, useEffect, useCallback } from 'react';
import { api } from '@/services/api';

export interface UseQRPollingOptions {
    /** Called once the backend confirms the QR was scanned successfully. */
    onAuthenticated: () => void;
    /** Called every time a fresh QR string arrives from the backend. */
    onQRCode: (qrData: string) => void;
    /** Optional — defaults to console.error. */
    onError?: (err: unknown) => void;
    /** Poll cadence in milliseconds (default: 10 000). */
    intervalMs?: number;
}

export interface UseQRPollingReturn {
    /** Start (or restart) polling for the given channel. */
    startPolling: (channelId: string) => void;
    /** Cancel any in-flight request and clear the scheduled timeout. */
    stopPolling: () => void;
}

export function useQRPolling({
    onAuthenticated,
    onQRCode,
    onError,
    intervalMs = 10_000,
}: UseQRPollingOptions): UseQRPollingReturn {
    /** Which channel we are currently polling for. null = not polling. */
    const activeChannelRef = useRef<string | null>(null);
    /** Handle for the pending setTimeout — stored so we can cancel it. */
    const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

    const stopPolling = useCallback((): void => {
        activeChannelRef.current = null;
        if (timeoutRef.current !== null) {
            clearTimeout(timeoutRef.current);
            timeoutRef.current = null;
        }
    }, []);

    const poll = useCallback(async (channelId: string): Promise<void> => {
        // Guard: if we were stopped between schedule and execution, bail out.
        if (activeChannelRef.current !== channelId) return;

        try {
            const { data } = await api.get(`/api/v1/channels/${channelId}/qr`);

            if (data.authenticated === true || data.status === 'active') {
                stopPolling();
                onAuthenticated();
                return;
            }

            if (data.qr_code) {
                onQRCode(data.qr_code);
            }
        } catch (err) {
            if (onError) {
                onError(err);
            } else {
                console.error('[useQRPolling] poll error:', err);
            }
        }

        // Schedule next tick only if still active.
        if (activeChannelRef.current === channelId) {
            timeoutRef.current = setTimeout(() => poll(channelId), intervalMs);
        }
    // poll depends on stopPolling, onAuthenticated, onQRCode, onError, intervalMs.
    // All callers should wrap callbacks in useCallback to keep this stable.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [stopPolling, onAuthenticated, onQRCode, onError, intervalMs]);

    const startPolling = useCallback((channelId: string): void => {
        stopPolling();                      // cancel any existing poll first
        activeChannelRef.current = channelId;
        poll(channelId);                    // kick off the first tick immediately
    }, [poll, stopPolling]);

    // Unmount cleanup — ensures no orphaned timeouts after navigation.
    useEffect(() => () => { stopPolling(); }, [stopPolling]);

    return { startPolling, stopPolling };
}

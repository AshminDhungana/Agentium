// src/hooks/useSystemTab.ts
// Owns all data-fetching, WebSocket lifecycle, and container action logic
// for the System tab. Refactored to use useRealtimeData for polled data,
// keeping the sovereign WebSocket for push-only command-logs.

import { useState, useEffect, useCallback, useRef } from 'react';
import { useBackendStore } from '@/store/backendStore';
import { hostAccessApi } from '@/services/hostAccessApi';
import { useRealtimeData } from './useRealtimeData';

// ── Types (exported so SystemTab.tsx can import them) ─────────────────────────

export interface SystemStatus {
    cpu: { usage: number; cores: number; load: number[] };
    memory: { total: number; used: number; free: number; percentage: number };
    disk: { total: number; used: number; free: number; percentage: number };
    uptime: { seconds: number; formatted: string };
}

export interface Container {
    id: string;
    name: string;
    status: string;
    image: string;
    created: string;
}

export interface CommandLog {
    id: string;
    command: string;
    status: 'pending' | 'approved' | 'rejected' | 'executed';
    timestamp: Date;
    executor?: string;
}

// ── Hook ──────────────────────────────────────────────────────────────────────

export function useSystemTab() {
    const { status: backendStatus } = useBackendStore();

    const [commandLogs,  setCommandLogs] = useState<CommandLog[]>([]);
    const [isLoading,   setIsLoading]      = useState(false);
    const [error,        setError]          = useState<string | null>(null);

    // Stable refs for the sovereign WebSocket (push-only, no polling)
    const wsRef            = useRef<{ send: (d: unknown) => void; close: () => void } | null>(null);
    const retryTimeoutRef  = useRef<ReturnType<typeof setTimeout> | null>(null);
    const retriesRef       = useRef(0);
    const mountedRef       = useRef(true);

    // ── Realtime data (polling + WS refresh) ───────────────────────────────
    // status and containers are replaced by useRealtimeData to avoid
    // manually wiring setInterval + refresh + WebSocket debounce.

    const { data: systemStatus, refresh: refreshStatus } = useRealtimeData<SystemStatus>(
        () => hostAccessApi.getSystemStatus(),
        ['system_status', 'container_update'],
        { pollIntervalMs: 10_000 }
    );

    const { data: containers, refresh: refreshContainers } = useRealtimeData<Container[]>(
        () => hostAccessApi.getContainers(),
        ['container_update', 'system_status'],
        { pollIntervalMs: 10_000 }
    );

    // ── WebSocket for real-time command logs (push-only) ─────────────────
    const connectWebSocket = useCallback(() => {
        wsRef.current = hostAccessApi.connectWebSocket(
            (data: any) => {
                retriesRef.current = 0;
                if (!mountedRef.current) return;

                if (data.type === 'system_status') {
                    // handled by useRealtimeData above
                    refreshStatus();
                } else if (data.type === 'container_update') {
                    refreshContainers();
                } else if (data.type === 'command_log') {
                    setCommandLogs((prev) => [data.payload, ...prev]);
                }
            },
            () => {
                // onClose — exponential backoff reconnect (max 30s)
                if (!mountedRef.current) return;
                const delay = Math.min(1000 * 2 ** retriesRef.current, 30_000);
                retriesRef.current += 1;
                retryTimeoutRef.current = setTimeout(connectWebSocket, delay);
            },
        );
    }, [refreshStatus, refreshContainers]);

    // ── Container actions ──────────────────────────────────────────────────

    const handleContainerAction = useCallback(async (
        containerId: string,
        action: 'start' | 'stop' | 'restart' | 'remove',
    ) => {
        setIsLoading(true);
        try {
            await hostAccessApi.manageContainer(containerId, action);
            const ctrs = await hostAccessApi.getContainers();
            if (mountedRef.current) {
                // handled by useRealtimeData refresh; call it immediately
                void refreshContainers();
            }
        } catch {
            if (mountedRef.current)
                setError(`Failed to ${action} container. Please try again.`);
        } finally {
            if (mountedRef.current) setIsLoading(false);
        }
    }, [refreshContainers]);

    // ── Lifecycle ───────────────────────────────────────────────────────────

    useEffect(() => {
        mountedRef.current = true;

        if (backendStatus.status !== 'connected') return;

        // Command-log WebSocket (push-only)
        connectWebSocket();

        return () => {
            mountedRef.current = false;
            if (retryTimeoutRef.current) clearTimeout(retryTimeoutRef.current);
            wsRef.current?.close();
        };
    }, [backendStatus.status, connectWebSocket]);

    return {
        systemStatus: systemStatus ?? null,
        containers: containers ?? [],
        commandLogs,
        isLoading,
        error,
        refresh: () => { void refreshStatus(); void refreshContainers(); },
        handleContainerAction,
        clearError: () => setError(null),
    };
}

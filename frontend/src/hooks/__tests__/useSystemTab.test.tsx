// frontend/src/hooks/__tests__/useSystemTab.test.tsx
// Fix 2 regression (TODO 12.4.3): the System tab's Command History panel must
// seed from the REST endpoint on connect (it was permanently empty before),
// map audit dicts to the display type, prepend live WS pushes, and degrade
// gracefully when the seed request fails.
import { renderHook, waitFor, act } from '@testing-library/react';
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { useSystemTab, mapAuditToCommandLog } from '@/hooks/useSystemTab';
import { hostAccessApi } from '@/services/hostAccessApi';
import { useBackendStore } from '@/store/backendStore';

const AUDIT = {
    id: 'audit-1',
    level: 'warning',
    category: 'governance',
    actor: { type: 'sovereign', id: 'admin' },
    action: 'container_restart',
    description: 'Sovereign manually restarted container xyz',
    result: { success: false, message: null, error: null },
    timestamp: '2026-09-24T10:00:00',
};

vi.mock('@/services/hostAccessApi', () => ({
    hostAccessApi: {
        getSystemStatus: vi.fn().mockResolvedValue(null),
        getContainers: vi.fn().mockResolvedValue([]),
        manageContainer: vi.fn().mockResolvedValue({}),
        getCommandHistory: vi.fn(),
        connectWebSocket: vi.fn().mockReturnValue({ send: vi.fn(), close: vi.fn() }),
    },
}));

vi.mock('@/hooks/useRealtimeData', () => {
    // Stable refresh identity — useSystemTab's connectWebSocket callback
    // depends on [refreshStatus, refreshContainers], and the seed sets state
    // on resolve; a fresh function per call would re-run the lifecycle effect
    // (and re-seed) on every render, looping forever.
    const refresh = () => {};
    return { useRealtimeData: () => ({ data: null, refresh }) };
});

describe('mapAuditToCommandLog', () => {
    it('maps an audit dict to the CommandLog display type', () => {
        const log = mapAuditToCommandLog(AUDIT);
        expect(log.id).toBe('audit-1');
        expect(log.command).toBe('container_restart');
        expect(log.status).toBe('pending');
        expect(log.executor).toBe('admin');
        expect(log.timestamp.getFullYear()).toBe(2026);
    });

    it('maps successful result to executed and errored result to rejected', () => {
        expect(
            mapAuditToCommandLog({ ...AUDIT, result: { success: true, error: null } }).status,
        ).toBe('executed');
        expect(
            mapAuditToCommandLog({ ...AUDIT, result: { success: false, error: 'boom' } }).status,
        ).toBe('rejected');
    });
});

describe('useSystemTab command history', () => {
    beforeEach(() => {
        vi.clearAllMocks();
        useBackendStore.setState({ status: { status: 'connected' } as never });
    });

    it('seeds command history from the REST endpoint on connect', async () => {
        vi.mocked(hostAccessApi.getCommandHistory).mockResolvedValue([AUDIT]);
        const { result } = renderHook(() => useSystemTab());

        await waitFor(() => expect(result.current.commandLogs).toHaveLength(1));
        expect(result.current.commandLogs[0].command).toBe('container_restart');
        expect(hostAccessApi.getCommandHistory).toHaveBeenCalledWith(50);
    });

    it('prepends a live command_log WebSocket push', async () => {
        vi.mocked(hostAccessApi.getCommandHistory).mockResolvedValue([]);
        const { result } = renderHook(() => useSystemTab());

        await waitFor(() => expect(hostAccessApi.connectWebSocket).toHaveBeenCalled());
        const onMessage = vi.mocked(hostAccessApi.connectWebSocket).mock.calls[0][0];
        act(() => onMessage({ type: 'command_log', payload: AUDIT }));

        expect(result.current.commandLogs).toHaveLength(1);
        expect(result.current.commandLogs[0].command).toBe('container_restart');
    });

    it('degrades gracefully when the seed request fails', async () => {
        vi.mocked(hostAccessApi.getCommandHistory).mockRejectedValue(new Error('network down'));
        const { result } = renderHook(() => useSystemTab());

        await waitFor(() => expect(hostAccessApi.getCommandHistory).toHaveBeenCalled());
        await act(async () => { await Promise.resolve(); });
        expect(result.current.commandLogs).toHaveLength(0);
        expect(result.current.error).toBeNull();
    });
});

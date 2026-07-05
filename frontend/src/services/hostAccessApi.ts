/**
 * Sovereign host-access API.
 *
 * Uses the shared `api` axios instance (defined in ./api) so that:
 *  - The Authorization header is set automatically via the shared instance/interceptors.
 *  - Token refresh / 401 handling is consistent with the rest of the app.
 *  - There is no duplication of auth logic here.
 */
import { api } from './api';
import { logger } from '@/utils/logger';

export const hostAccessApi = {
    // ── System Status ──────────────────────────────────────────────────────────

    getSystemStatus: async () => {
        const response = await api.get('/api/v1/sovereign/system/status');
        return response.data;
    },

    // ── Containers ─────────────────────────────────────────────────────────────

    getContainers: async () => {
        const response = await api.get('/api/v1/sovereign/containers');
        return response.data;
    },

    manageContainer: async (
        containerId: string,
        action: 'start' | 'stop' | 'restart' | 'remove',
    ) => {
        const response = await api.post(
            `/api/v1/sovereign/containers/${containerId}/${action}`,
            {},
        );
        return response.data;
    },

    // ── Commands ───────────────────────────────────────────────────────────────

    getCommandHistory: async (limit = 50) => {
        const response = await api.get('/api/v1/sovereign/commands', {
            params: { limit },
        });
        return response.data;
    },

    executeSovereignCommand: async (
        command: string,
        params: Record<string, unknown> = {},
    ) => {
        const response = await api.post('/api/v1/sovereign/command', {
            command,
            params,
            target: 'head_of_council',
            requireApproval: false,
        });
        return response.data;
    },

    // ── Audit Logs ─────────────────────────────────────────────────────────────

    getAuditLogs: async (filters?: {
        agentiumId?: string;
        level?: string;
        startTime?: string;
        endTime?: string;
        limit?: number;
    }) => {
        const response = await api.get('/api/v1/sovereign/audit', {
            params: filters,
        });
        return response.data;
    },

    // ── Agent Management ───────────────────────────────────────────────────────

    blockAgent: async (agentiumId: string, reason: string) => {
        const response = await api.post(
            `/api/v1/sovereign/agents/${agentiumId}/block`,
            { reason },
        );
        return response.data;
    },

    unblockAgent: async (agentiumId: string) => {
        const response = await api.post(
            `/api/v1/sovereign/agents/${agentiumId}/unblock`,
            {},
        );
        return response.data;
    },

    // ── File System ────────────────────────────────────────────────────────────

    readFile: async (path: string) => {
        const response = await api.get('/api/v1/sovereign/files', {
            params: { path },
        });
        return response.data;
    },

    writeFile: async (path: string, content: string) => {
        const response = await api.post('/api/v1/sovereign/files', {
            path,
            content,
        });
        return response.data;
    },

    listDirectory: async (path = '/') => {
        const response = await api.get('/api/v1/sovereign/directory', {
            params: { path },
        });
        return response.data;
    },

    // ── WebSocket for real-time updates ───────────────────────────────────────

    /**
     * Open a WebSocket connection for live sovereign events.
     *
     * @param onMessage  Called for every well-formed JSON message received.
     * @param onClose    Optional — called when the socket closes for any reason
     *                   (clean close, network error, server restart). Callers
     *                   can use this to schedule a reconnect with backoff.
     *                   C2: added to enable reconnect logic in useSystemTab.
     *
     * Derives the WS URL from the current page's protocol/host so it works in
     * both HTTP (ws://) and HTTPS (wss://) environments.
     */
    connectWebSocket: (
        onMessage: (data: unknown) => void,
        onClose?: () => void,
    ) => {
        const token = localStorage.getItem('access_token');
        const wsProtocol = window.location.protocol === 'https:' ? 'wss' : 'ws';
        const wsBase = `${wsProtocol}://${window.location.host}`;
        const ws = new WebSocket(`${wsBase}/api/v1/sovereign/ws?token=${token}`);

        ws.onopen = () => {
            logger.debug('Sovereign WebSocket connected');
        };

        ws.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                onMessage(data);
            } catch (err) {
                logger.error('Failed to parse WebSocket message:', err);
            }
        };

        ws.onerror = (error) => {
            logger.error('Sovereign WebSocket error:', error);
        };

        ws.onclose = () => {
            logger.debug('Sovereign WebSocket disconnected');
            onClose?.();
        };

        return {
            send: (data: unknown) => ws.send(JSON.stringify(data)),
            close: () => ws.close(),
        };
    },
};
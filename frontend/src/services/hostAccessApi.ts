import axios from 'axios';

const API_URL = import.meta.env.VITE_API_URL || '';

// Get auth token from localStorage
const getAuthHeaders = () => {
    const token = localStorage.getItem('access_token');
    return {
        Authorization: `Bearer ${token}`
    };
};

export const hostAccessApi = {
    // System Status
    getSystemStatus: async () => {
        const response = await axios.get(`${API_URL}/api/v1/sovereign/system/status`, {
            headers: getAuthHeaders()
        });
        return response.data;
    },

    // Containers
    getContainers: async () => {
        const response = await axios.get(`${API_URL}/api/v1/sovereign/containers`, {
            headers: getAuthHeaders()
        });
        return response.data;
    },

    manageContainer: async (containerId: string, action: 'start' | 'stop' | 'restart' | 'remove') => {
        const response = await axios.post(
            `${API_URL}/api/v1/sovereign/containers/${containerId}/${action}`,
            {},
            { headers: getAuthHeaders() }
        );
        return response.data;
    },

    // Commands
    getCommandHistory: async (limit = 50) => {
        const response = await axios.get(`${API_URL}/api/v1/sovereign/commands`, {
            params: { limit },
            headers: getAuthHeaders()
        });
        return response.data;
    },

    executeSovereignCommand: async (command: string, params: Record<string, any> = {}) => {
        const response = await axios.post(
            `${API_URL}/api/v1/sovereign/command`,
            {
                command,
                params,
                target: 'head_of_council',
                requireApproval: false
            },
            { headers: getAuthHeaders() }
        );
        return response.data;
    },

    // Audit Logs
    getAuditLogs: async (filters?: {
        agentiumId?: string;
        level?: string;
        startTime?: string;
        endTime?: string;
        limit?: number;
    }) => {
        const response = await axios.get(`${API_URL}/api/v1/sovereign/audit`, {
            params: filters,
            headers: getAuthHeaders()
        });
        return response.data;
    },

    // Agent Management
    blockAgent: async (agentiumId: string, reason: string) => {
        const response = await axios.post(
            `${API_URL}/api/v1/sovereign/agents/${agentiumId}/block`,
            { reason },
            { headers: getAuthHeaders() }
        );
        return response.data;
    },

    unblockAgent: async (agentiumId: string) => {
        const response = await axios.post(
            `${API_URL}/api/v1/sovereign/agents/${agentiumId}/unblock`,
            {},
            { headers: getAuthHeaders() }
        );
        return response.data;
    },

    // File System
    readFile: async (path: string) => {
        const response = await axios.get(`${API_URL}/api/v1/sovereign/files`, {
            params: { path },
            headers: getAuthHeaders()
        });
        return response.data;
    },

    writeFile: async (path: string, content: string) => {
        const response = await axios.post(
            `${API_URL}/api/v1/sovereign/files`,
            { path, content },
            { headers: getAuthHeaders() }
        );
        return response.data;
    },

    listDirectory: async (path: string = '/') => {
        const response = await axios.get(`${API_URL}/api/v1/sovereign/directory`, {
            params: { path },
            headers: getAuthHeaders()
        });
        return response.data;
    },

    // WebSocket for real-time updates
    connectWebSocket: (onMessage: (data: any) => void) => {
        const token = localStorage.getItem('access_token');
        const ws = new WebSocket(`${API_URL.replace('http', 'ws')}/ws/sovereign?token=${token}`);

        ws.onopen = () => {
            console.log('Sovereign WebSocket connected');
        };

        ws.onmessage = (event) => {
            const data = JSON.parse(event.data);
            onMessage(data);
        };

        ws.onerror = (error) => {
            console.error('WebSocket error:', error);
        };

        ws.onclose = () => {
            console.log('Sovereign WebSocket disconnected');
        };

        return {
            send: (data: any) => ws.send(JSON.stringify(data)),
            close: () => ws.close()
        };
    }
};
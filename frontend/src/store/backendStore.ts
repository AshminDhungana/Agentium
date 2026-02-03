import { create } from 'zustand';
import axios from 'axios';
import { BackendStatus } from '@/types';

interface BackendState {
    status: BackendStatus;
    checkConnection: () => Promise<void>;
    startPolling: () => void;
    stopPolling: () => void;
    pollingInterval?: NodeJS.Timeout;
}

const API_URL = import.meta.env.VITE_API_URL || '';

export const useBackendStore = create<BackendState>()((set, get) => ({
    status: {
        status: 'connecting',
        lastChecked: new Date()
    },

    checkConnection: async () => {
        const startTime = Date.now();

        try {
            const response = await axios.get(`${API_URL}/health`, {
                timeout: 5000
            });

            const latency = Date.now() - startTime;

            set({
                status: {
                    status: 'connected',
                    version: response.data.version,
                    lastChecked: new Date(),
                    latency
                }
            });
        } catch (error) {
            set({
                status: {
                    status: 'disconnected',
                    lastChecked: new Date()
                }
            });
        }
    },

    startPolling: () => {
        // Check immediately
        get().checkConnection();

        // Then every 10 seconds
        const interval = setInterval(() => {
            get().checkConnection();
        }, 10000);

        set({ pollingInterval: interval });
    },

    stopPolling: () => {
        const { pollingInterval } = get();
        if (pollingInterval) {
            clearInterval(pollingInterval);
            set({ pollingInterval: undefined });
        }
    }
}));
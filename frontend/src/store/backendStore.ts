import { create } from 'zustand';
import { BackendStatus } from '@/types';
import { backendHealthApi } from '@/services/backendHealth';
import { channelMetricsApi } from '@/services/channelMetrics';
import { logger } from '@/utils/logger';
import type {
  AllChannelsMetricsResponse,
  ChannelMetricsResponse,
  ChannelHealthStatus
} from '@/types';

interface BackendState {
  // Connection status
  status: BackendStatus;
  checkConnection: () => Promise<void>;
  startPolling: () => void;
  stopPolling: () => void;
  pollingInterval?: NodeJS.Timeout;
  
  // Channel Metrics (Phase 4 + Phase 7)
  channelMetrics: AllChannelsMetricsResponse | null;
  currentChannelMetrics: Record<string, ChannelMetricsResponse>;
  isLoadingChannelMetrics: boolean;
  isLoadingSingleChannel: Record<string, boolean>;
  fetchChannelMetrics: () => Promise<void>;
  fetchSingleChannelMetrics: (channelId: string) => Promise<ChannelMetricsResponse | null>;
  resetChannelCircuit: (channelId: string) => Promise<boolean>;
  getChannelHealthStatus: (channelId: string) => ChannelHealthStatus | null;
}

export const useBackendStore = create<BackendState>()((set, get) => ({
  // ═══════════════════════════════════════════════════════════
  // CONNECTION STATUS
  // ═══════════════════════════════════════════════════════════

  status: {
    status: 'connecting',
    lastChecked: new Date()
  },

  checkConnection: async () => {
    const startTime = Date.now();

    try {
      const data = await backendHealthApi.check();
      const latency = Date.now() - startTime;

      set({
        status: {
          status: 'connected',
          version: data.version,
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
  },

  // ═══════════════════════════════════════════════════════════
  // CHANNEL METRICS (Phase 4 + Phase 7)
  // ═══════════════════════════════════════════════════════════

  channelMetrics: null,
  currentChannelMetrics: {},
  isLoadingChannelMetrics: false,
  isLoadingSingleChannel: {},

  /**
   * Fetch metrics for all channels (dashboard widget)
   */
  fetchChannelMetrics: async () => {
    // Prevent duplicate requests
    if (get().isLoadingChannelMetrics) return;
    
    set({ isLoadingChannelMetrics: true });
    
    try {
      const data = await channelMetricsApi.getAllChannelsMetrics();
      set({ 
        channelMetrics: data, 
        isLoadingChannelMetrics: false 
      });
    } catch (error) {
      logger.warn('Failed to fetch channel metrics:', error);
      set({ isLoadingChannelMetrics: false });
    }
  },

  /**
   * Fetch metrics for a specific channel
   */
  fetchSingleChannelMetrics: async (channelId: string) => {
    // Set loading state for this specific channel
    set(state => ({
      isLoadingSingleChannel: {
        ...state.isLoadingSingleChannel,
        [channelId]: true
      }
    }));

    try {
      const data = await channelMetricsApi.getChannelMetrics(channelId);
      
      set(state => ({
        currentChannelMetrics: {
          ...state.currentChannelMetrics,
          [channelId]: data
        },
        isLoadingSingleChannel: {
          ...state.isLoadingSingleChannel,
          [channelId]: false
        }
      }));

      return data;
    } catch (error) {
      logger.warn(`Failed to fetch metrics for channel ${channelId}:`, error);
      
      set(state => ({
        isLoadingSingleChannel: {
          ...state.isLoadingSingleChannel,
          [channelId]: false
        }
      }));
      
      return null;
    }
  },

  /**
   * Reset circuit breaker for a channel
   */
  resetChannelCircuit: async (channelId: string) => {
    try {
      await channelMetricsApi.resetChannel(channelId);
      
      // Refresh metrics after reset
      await get().fetchSingleChannelMetrics(channelId);
      await get().fetchChannelMetrics();
      
      return true;
    } catch (error) {
      logger.warn(`Failed to reset channel ${channelId}:`, error);
      return false;
    }
  },

  /**
   * Get health status for a specific channel (from cache)
   */
  getChannelHealthStatus: (channelId: string) => {
    const metrics = get().currentChannelMetrics[channelId];
    return metrics?.health_status || null;
  }
}));
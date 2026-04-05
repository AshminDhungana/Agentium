import { api } from './api';
import type {
  ChannelMetricsResponse,
  AllChannelsMetricsResponse,
  MessageLog,
  ChannelSettings,
  ChannelLogFilters,
} from '@/types';

export const channelMetricsApi = {
  // Get metrics for specific channel
  getChannelMetrics: (channelId: string) =>
    api.get<ChannelMetricsResponse>(`/api/v1/channels/${channelId}/metrics`)
      .then(r => r.data),

  // Get all channels metrics (for dashboard)
  getAllChannelsMetrics: () =>
    api.get<AllChannelsMetricsResponse>('/api/v1/channels/metrics')
      .then(r => r.data),

  // Get message logs for channel (legacy — uses /messages)
  getChannelLogs: (channelId: string, filters: ChannelLogFilters = {}) => {
    const params = new URLSearchParams();
    if (filters.status)    params.set('status',    filters.status);
    if (filters.sender_id) params.set('sender_id', filters.sender_id);
    if (filters.date_from) params.set('date_from', filters.date_from);
    if (filters.date_to)   params.set('date_to',   filters.date_to);
    params.set('limit',  String(filters.limit  ?? 50));
    params.set('offset', String(filters.offset ?? 0));
    return api.get<{ messages: MessageLog[]; total: number; limit: number; offset: number }>(
      `/api/v1/channels/${channelId}/logs?${params.toString()}`
    ).then(r => r.data);
  },

  // Reset circuit breaker
  resetChannel: (channelId: string) =>
    api.post(`/api/v1/channels/${channelId}/reset`).then(r => r.data),

 
  /**
   * Update per-channel operational settings.
   * Maps to PATCH /api/v1/channels/{id}/settings
   */
  updateChannelSettings: (channelId: string, settings: ChannelSettings) =>
    api.patch<ReturnType<typeof Object>>(`/api/v1/channels/${channelId}/settings`, settings)
      .then(r => r.data),
};
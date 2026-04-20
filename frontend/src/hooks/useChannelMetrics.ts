// src/hooks/useChannelMetrics.ts
// ─────────────────────────────────────────────────────────────────────────────
// Custom hook that encapsulates polling + reset mutation for a single channel's
// metrics.  Used by MonitoringPage (and any future component that needs
// per-channel health data) so the same query options are never duplicated.
//
// Key improvements over the old inline queries:
//   • refetchIntervalInBackground: false  — pauses when the tab is hidden
//   • keepPreviousData                    — prevents layout shift on each poll
//   • staleTime == refetchInterval        — no spurious double-fetches on mount
//   • reset mutation exposes isPending for button loading state
// ─────────────────────────────────────────────────────────────────────────────

import { useQuery, useMutation, useQueryClient, keepPreviousData } from '@tanstack/react-query';
import { showToast } from '@/hooks/useToast';
import { channelMetricsApi } from '@/services/channelMetrics';
import type { ChannelMetricsResponse } from '@/types';

const POLL_INTERVAL = 10_000; // 10 s

export interface UseChannelMetricsReturn {
    data:            ChannelMetricsResponse | undefined;
    isLoading:       boolean;
    isError:         boolean;
    isFetching:      boolean;
    dataUpdatedAt:   number;
    refetch:         () => void;
    reset:           () => void;
    isResetting:     boolean;
}

export function useChannelMetrics(channelId: string): UseChannelMetricsReturn {
    const queryClient = useQueryClient();

    const {
        data,
        isLoading,
        isError,
        isFetching,
        dataUpdatedAt,
        refetch,
    } = useQuery<ChannelMetricsResponse>({
        queryKey: ['channel-metrics', channelId],
        queryFn:  () => channelMetricsApi.getChannelMetrics(channelId),
        // Align staleTime with refetchInterval so a mount between the two
        // boundaries does not fire an extra request.
        staleTime:                  POLL_INTERVAL,
        refetchInterval:            POLL_INTERVAL,
        // Stop polling when the browser tab is backgrounded.
        refetchIntervalInBackground: false,
        // Keep showing previous data while the silent background poll is
        // in-flight — prevents the loading spinner from flashing every 10 s.
        placeholderData:            keepPreviousData,
    });

    const resetMutation = useMutation({
        mutationFn: () => channelMetricsApi.resetChannel(channelId),
        onSuccess: () => {
            showToast.success('Channel reset successfully');
            queryClient.invalidateQueries({ queryKey: ['channel-metrics', channelId] });
            // Also invalidate the batched query used by ChannelsPage
            queryClient.invalidateQueries({ queryKey: ['all-channel-metrics'] });
        },
        onError: () => showToast.error('Failed to reset channel'),
    });

    return {
        data,
        isLoading,
        isError,
        isFetching,
        dataUpdatedAt,
        refetch: () => { refetch(); },
        reset:        () => resetMutation.mutate(),
        isResetting:  resetMutation.isPending,
    };
}
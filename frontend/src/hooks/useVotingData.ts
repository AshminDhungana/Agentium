/**
 * useVotingData
 *
 * Encapsulates all data-fetching logic for the Voting page.
 * Refactored to use useRealtimeData for common polling + WebSocket refresh logic.
 */

import { useState, useCallback } from 'react';
import { showToast } from '@/hooks/useToast';
import { useRealtimeData } from './useRealtimeData';
import {
    votingService,
    AmendmentVoting,
    TaskDeliberation,
} from '../services/voting';

// ── Return shape ──────────────────────────────────────────────────────────────

export interface UseVotingDataReturn {
    amendments: AmendmentVoting[];
    deliberations: TaskDeliberation[];
    isLoading: boolean;
    isRefreshing: boolean;
    selectedItem: AmendmentVoting | TaskDeliberation | null;
    setSelectedItem: React.Dispatch<React.SetStateAction<AmendmentVoting | TaskDeliberation | null>>;
    loadData: (silent?: boolean) => Promise<void>;
}

// ── Internal aggregated type ─────────────────────────────────────────────────

interface VotingData {
    amendments: AmendmentVoting[];
    deliberations: TaskDeliberation[];
}

// ── Hook ──────────────────────────────────────────────────────────────────────

export function useVotingData(): UseVotingDataReturn {
    const [selectedItem, setSelectedItem] = useState<
        AmendmentVoting | TaskDeliberation | null
    >(null);

    // Fetcher stays stable thanks to useCallback
    const fetcher = useCallback(async (): Promise<VotingData> => {
        const [amendData, deliData] = await Promise.all([
            votingService.getAmendmentVotings(),
            votingService.getTaskDeliberations(),
        ]);
        return { amendments: amendData, deliberations: deliData };
    }, []);

    // Delegate real-time scaffolding to useRealtimeData
    const {
        data,
        isLoading,
        isRefreshing,
        refresh,
    } = useRealtimeData<VotingData>(
        fetcher,
        ['vote_update', 'vote_cast', 'vote_finalized'],
        { pollIntervalMs: 30_000, debounceMs: 500 }
    );

    // Keep selectedItem in sync with fresh server data on each refresh
    const syncSelected = useCallback(() => {
        if (!data) return;
        setSelectedItem((prev) => {
            if (!prev) return null;
            const freshAmend = data.amendments.find((a) => a.id === prev.id);
            const freshDeli = data.deliberations.find((d) => d.id === prev.id);
            return freshAmend ?? freshDeli ?? prev;
        });
    }, [data]);

    // Wrap refresh for consumers that expect the old loadData signature
    const loadData = useCallback(async (silent = false): Promise<void> => {
        try {
            await refresh();
            syncSelected();
        } catch (e) {
            if (!silent) {
                showToast.error('Failed to load voting data');
            }
        }
    }, [refresh, syncSelected]);

    return {
        amendments: data?.amendments ?? [],
        deliberations: data?.deliberations ?? [],
        isLoading,
        isRefreshing,
        selectedItem,
        setSelectedItem,
        loadData,
    };
}

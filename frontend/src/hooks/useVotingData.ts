/**
 * useVotingData
 *
 * Encapsulates all data-fetching logic for the Voting page.
 * Improvements over the previous inline implementation:
 *  - Concurrent fetch prevention via pendingRef
 *  - Unmount safety via isMountedRef (no setState after unmount)
 *  - WebSocket-triggered refreshes are debounced (500ms) to prevent
 *    multiple rapid fetches when vote events arrive in bursts
 *  - Auto-refresh every 30s
 *  - selectedItem is kept in sync with fresh server data on each refresh
 */

import { useState, useEffect, useCallback, useRef } from 'react';
import { showToast } from '@/hooks/useToast';
import {
    votingService,
    AmendmentVoting,
    TaskDeliberation,
} from '../services/voting';
import { useWebSocketStore } from '../store/websocketStore';

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

// ── Hook ──────────────────────────────────────────────────────────────────────

export function useVotingData(): UseVotingDataReturn {
    const [amendments, setAmendments] = useState<AmendmentVoting[]>([]);
    const [deliberations, setDeliberations] = useState<TaskDeliberation[]>([]);
    const [isLoading, setIsLoading] = useState(true);
    const [isRefreshing, setIsRefreshing] = useState(false);
    const [selectedItem, setSelectedItem] = useState<AmendmentVoting | TaskDeliberation | null>(null);

    // Prevent concurrent in-flight requests
    const pendingRef = useRef(false);
    // Prevent setState after unmount
    const isMountedRef = useRef(true);
    // Debounce WebSocket-triggered refreshes
    const wsDebounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

    useEffect(() => {
        isMountedRef.current = true;
        return () => {
            isMountedRef.current = false;
            if (wsDebounceRef.current) clearTimeout(wsDebounceRef.current);
        };
    }, []);

    const loadData = useCallback(async (silent = false) => {
        // Prevent duplicate concurrent fetches
        if (pendingRef.current) return;
        pendingRef.current = true;

        if (!isMountedRef.current) {
            pendingRef.current = false;
            return;
        }

        if (!silent) setIsLoading(true);
        else setIsRefreshing(true);

        try {
            const [amendData, deliData] = await Promise.all([
                votingService.getAmendmentVotings(),
                votingService.getTaskDeliberations(),
            ]);

            if (!isMountedRef.current) return;

            setAmendments(amendData);
            setDeliberations(deliData);

            // Keep selectedItem in sync with fresh server data
            setSelectedItem(prev => {
                if (!prev) return null;
                const freshAmend = amendData.find(a => a.id === prev.id);
                const freshDeli = deliData.find(d => d.id === prev.id);
                return freshAmend ?? freshDeli ?? prev;
            });
        } catch (error) {
            if (!isMountedRef.current) return;
            console.error('Failed to load voting data:', error);
            if (!silent) showToast.error('Failed to load voting data');
        } finally {
            if (isMountedRef.current) {
                setIsLoading(false);
                setIsRefreshing(false);
            }
            pendingRef.current = false;
        }
    }, []);

    // Initial load + 30-second auto-refresh
    useEffect(() => {
        loadData();
        const id = setInterval(() => loadData(true), 30_000);
        return () => clearInterval(id);
    }, [loadData]);

    // WebSocket-triggered refresh — debounced to prevent burst re-fetches
    const lastMessage = useWebSocketStore(s => s.lastMessage);
    useEffect(() => {
        if (!lastMessage) return;
        const data = lastMessage as any;
        const isVoteEvent =
            data.type === 'vote_update' ||
            data.event === 'vote_cast' ||
            data.event === 'vote_finalized';

        if (!isVoteEvent) return;

        // Debounce: ignore rapid consecutive events, fire once after 500ms quiet period
        if (wsDebounceRef.current) clearTimeout(wsDebounceRef.current);
        wsDebounceRef.current = setTimeout(() => {
            loadData(true);
        }, 500);
    }, [lastMessage, loadData]);

    return {
        amendments,
        deliberations,
        isLoading,
        isRefreshing,
        selectedItem,
        setSelectedItem,
        loadData,
    };
}
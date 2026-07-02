// ─── useRealtimeData ─────────────────────────────────────────────────────────
// One hook that polls an endpoint on a timer AND listens to the global
// Zustand WebSocket store for instant invalidation.
// Replaces scattered patterns in useVotingData, useSystemTab, etc.
// ──────────────────────────────────────────────────────────────────────────────

import { useState, useEffect, useCallback, useRef } from 'react';
import { api } from '@/services/api';
import { useWebSocketStore } from '@/store/websocketStore';

export interface UseRealtimeDataReturn<T> {
  /** Current data (null before first successful load) */
  data: T | null;
  /** True only during the very first fetch */
  isLoading: boolean;
  /** True during background (silent) refreshes */
  isRefreshing: boolean;
  /** Last error message, or null */
  error: string | null;
  /** Manually trigger a fetch */
  refresh: () => Promise<void>;
}

export interface UseRealtimeDataOptions {
  /** How often to re-poll (ms). Omit or 0 to disable polling. */
  pollIntervalMs?: number;
  /** Debounce window for WebSocket-triggered refreshes (default 500). */
  debounceMs?: number;
  /** If true, background re-fetches don't set error state */
  silentRefresh?: boolean;
}

/**
 * Unified hook for real-time data.
 *
 * @param fetcher       Either a GET endpoint string (relative to api.baseURL)
 *                      or a custom fetch function returning Promise<T>.
 * @param wsEventFilter WebSocket event type(s) to trigger auto-refresh.
 *                      Checks both `msg.type` and `msg.event`.
 * @param options       Optional configuration.
 *
 * @example
 * // Poll GET /api/v1/agents every 30s, refresh on 'agent_spawned'
 * const { data, isLoading, isRefreshing, error, refresh } =
 *   useRealtimeData<Agent[]>('/api/v1/agents', 'agent_spawned', { pollIntervalMs: 30000 });
 *
 * @example
 * // Custom fetcher, 30s poll, refresh on multiple WS events
 * const { data } = useRealtimeData<VotingData>(
 *   async () => ({ amendments: await getAmendments(), ... }),
 *   ['vote_update', 'vote_cast'],
 *   { pollIntervalMs: 30000, debounceMs: 500 }
 * );
 */
export function useRealtimeData<T>(
  fetcher: string | (() => Promise<T>),
  wsEventFilter?: string | string[],
  options: UseRealtimeDataOptions = {}
): UseRealtimeDataReturn<T> {
  const { pollIntervalMs, debounceMs = 500 } = options;

  const [data, setData] = useState<T | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const isMountedRef = useRef(true);
  const pendingRef = useRef(false);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const fetcherRef = useRef(fetcher);
  fetcherRef.current = fetcher; // keep latest stable ref for load() callback

  // ── Fetch helper ──────────────────────────────────────────────────────────
  const fetchData = useCallback(async (): Promise<T> => {
    const current = fetcherRef.current;
    if (typeof current === 'string') {
      const { data: responseData } = await api.get<T>(current);
      return responseData;
    }
    return current();
  }, []);

  // ── Main load ────────────────────────────────────────────────────────────
  const load = useCallback(async (silent = false) => {
    if (pendingRef.current) return;
    pendingRef.current = true;

    if (!isMountedRef.current) {
      pendingRef.current = false;
      return;
    }

    if (!silent) setIsLoading(true);
    else setIsRefreshing(true);

    let result: T | null = null;
    try {
      result = await fetchData();
      if (!isMountedRef.current) return;
      setData(result);
      setError(null);
    } catch (err) {
      if (!isMountedRef.current) return;
      const msg = err instanceof Error ? err.message : 'Failed to load data';
      setError(msg);
      if (!silent) console.error('[useRealtimeData] Load error:', err);
    } finally {
      if (isMountedRef.current) {
        setIsLoading(false);
        setIsRefreshing(false);
      }
      pendingRef.current = false;
    }
  }, [fetchData]);

  // ── Initial load + interval polling ─────────────────────────────────────
  useEffect(() => {
    isMountedRef.current = true;
    load(false);

    if (pollIntervalMs && pollIntervalMs > 0) {
      pollRef.current = setInterval(() => load(true), pollIntervalMs);
    }

    return () => {
      isMountedRef.current = false;
      if (pollRef.current) {
        clearInterval(pollRef.current);
        pollRef.current = null;
      }
    };
  }, [load, pollIntervalMs]);

  // ── WebSocket-triggered refresh (debounced) ───────────────────────────────
  const lastMessage = useWebSocketStore((s) => s.lastMessage);
  const filterRef = useRef(wsEventFilter);
  filterRef.current = wsEventFilter;

  useEffect(() => {
    if (!lastMessage) return;
    const filter = filterRef.current;
    if (!filter) return;

    const filters = Array.isArray(filter) ? filter : [filter];
    const msg = lastMessage as any;
    const matches = filters.some(
      (f) => msg.type === f || msg.event === f || (msg as any)[f] !== undefined
    );

    if (!matches) return;

    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      load(true);
    }, debounceMs);
  }, [lastMessage, load, debounceMs]);

  // ── Cleanup debounce on unmount ─────────────────────────────────────────
  useEffect(() => {
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, []);

  return {
    data,
    isLoading,
    isRefreshing,
    error,
    refresh: () => load(true),
  };
}

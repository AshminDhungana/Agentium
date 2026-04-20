/**
 * frontend/src/hooks/useMessageLog.ts
 *
 * Custom hook that owns all state and side-effects for the Message Log page.
 *
 * Improvements applied vs the original inline page logic:
 *  - AbortController cancels stale in-flight requests on filter change
 *  - Debounce timer is cleaned up on unmount (no stale-closure warning)
 *  - Channel fetch error is surfaced as a toast instead of silently swallowed
 *  - handleReplay awaits fetchMessages so the list refreshes before re-enabling the button
 *  - failedTotal is read from the backend stats field (full dataset count) with a
 *    page-slice fallback for older backend versions that don't yet expose it
 *  - Bulk replay toast wording reflects that messages are queued, not instantly done
 */

import { useState, useEffect, useCallback, useRef } from 'react';
import { api } from '@/services/api';
import {
  channelMessagesApi,
  ChannelMessage,
  MessageLogFilters,
} from '@/services/channelMessages';
import { showToast } from '@/hooks/useToast';

// ─── Constants ────────────────────────────────────────────────────────────────

export const DEFAULT_FILTERS: MessageLogFilters = {
  limit: 50,
  offset: 0,
};

// ─── Return type ─────────────────────────────────────────────────────────────

export interface UseMessageLogReturn {
  messages: ChannelMessage[];
  total: number;
  /** Total failed messages matching the current filters (full dataset, not page slice). */
  failedTotal: number;
  loading: boolean;
  filters: MessageLogFilters;
  search: string;
  channels: Array<{ id: string; name: string; type: string }>;
  replayingId: string | null;
  bulkReplaying: boolean;
  currentPage: number;
  totalPages: number;
  hasActiveFilters: boolean;
  fetchMessages: (f: MessageLogFilters, signal?: AbortSignal) => Promise<void>;
  handleFilterChange: (patch: Partial<MessageLogFilters>) => void;
  handleSearchChange: (value: string) => void;
  handleReset: () => void;
  handleReplay: (messageId: string) => Promise<void>;
  handleBulkReplay: () => Promise<void>;
  /** Exposed so the pagination controls can directly set offset. */
  setFilters: React.Dispatch<React.SetStateAction<MessageLogFilters>>;
}

// ─── Hook ─────────────────────────────────────────────────────────────────────

export function useMessageLog(): UseMessageLogReturn {
  const [messages, setMessages]         = useState<ChannelMessage[]>([]);
  const [total, setTotal]               = useState(0);
  const [failedTotal, setFailedTotal]   = useState(0);
  const [loading, setLoading]           = useState(true);
  const [filters, setFilters]           = useState<MessageLogFilters>(DEFAULT_FILTERS);
  const [search, setSearch]             = useState('');
  const [channels, setChannels]         = useState<Array<{ id: string; name: string; type: string }>>([]);
  const [replayingId, setReplayingId]   = useState<string | null>(null);
  const [bulkReplaying, setBulkReplaying] = useState(false);

  const searchDebounce = useRef<ReturnType<typeof setTimeout>>();

  // ── Load channels for the filter dropdown ──────────────────────────────────
  useEffect(() => {
    api
      .get('/channels/')
      .then(r => {
        setChannels(
          (r.data.channels ?? []).map((c: any) => ({
            id:   c.id,
            name: c.name,
            type: c.type,
          }))
        );
      })
      .catch(() => {
        // Surface the error so users know why the dropdown is empty.
        showToast.error('Could not load channels for filter');
      });
  }, []);

  // ── Cleanup debounce timer on unmount ──────────────────────────────────────
  useEffect(() => {
    return () => clearTimeout(searchDebounce.current);
  }, []);

  // ── Core fetch ─────────────────────────────────────────────────────────────
  const fetchMessages = useCallback(
    async (f: MessageLogFilters, signal?: AbortSignal) => {
      setLoading(true);
      try {
        const data = await channelMessagesApi.getLog(f, signal);
        setMessages(data.messages);
        setTotal(data.total);

        // Prefer the backend-supplied failed_total (full-dataset count).
        // Fall back to counting the current page slice for older backend builds.
        setFailedTotal(
          data.stats.failed_total ??
          data.messages.filter(m => m.status === 'failed' || m.error_count > 0).length
        );
      } catch (err: unknown) {
        // Ignore intentional cancellations — they are not real errors.
        if (err instanceof Error && err.name === 'AbortError') return;
        // Axios uses a code instead of name for cancellations.
        if (err && typeof err === 'object' && 'code' in err && (err as any).code === 'ERR_CANCELED') return;
        showToast.error('Failed to load message log');
      } finally {
        setLoading(false);
      }
    },
    []
  );

  // ── Re-fetch whenever filters change; cancel any pending request ──────────
  useEffect(() => {
    const controller = new AbortController();
    fetchMessages(filters, controller.signal);
    return () => controller.abort();
  }, [filters, fetchMessages]);

  // ── Handlers ───────────────────────────────────────────────────────────────

  const handleFilterChange = (patch: Partial<MessageLogFilters>) => {
    setFilters(prev => ({ ...prev, ...patch, offset: 0 }));
  };

  const handleSearchChange = (value: string) => {
    setSearch(value);
    clearTimeout(searchDebounce.current);
    searchDebounce.current = setTimeout(() => {
      setFilters(prev => ({ ...prev, search: value || undefined, offset: 0 }));
    }, 400);
  };

  const handleReset = () => {
    setSearch('');
    setFilters(DEFAULT_FILTERS);
  };

  const handleReplay = async (messageId: string) => {
    setReplayingId(messageId);
    try {
      await channelMessagesApi.replayMessage(messageId);
      showToast.success('Message re-queued for processing');
      // Await the refresh so the updated status is visible before the
      // button re-enables (was fire-and-forget in the original).
      await fetchMessages(filters);
    } catch {
      showToast.error('Replay failed');
    } finally {
      setReplayingId(null);
    }
  };

  const handleBulkReplay = async () => {
    setBulkReplaying(true);
    try {
      const res = await channelMessagesApi.replayFailed(filters.channel_id);
      // Wording clarified: messages are queued, not instantly processed.
      showToast.success(`${res.queued} failed message(s) queued for replay`);
      setTimeout(() => fetchMessages(filters), 2500);
    } catch {
      showToast.error('Bulk replay failed');
    } finally {
      setBulkReplaying(false);
    }
  };

  // ── Derived values ─────────────────────────────────────────────────────────

  const currentPage = Math.floor((filters.offset ?? 0) / (filters.limit ?? 50)) + 1;
  const totalPages  = Math.ceil(total / (filters.limit ?? 50));

  const hasActiveFilters =
    Object.keys(filters).some(
      k => k !== 'limit' && k !== 'offset' && filters[k as keyof MessageLogFilters] !== undefined
    ) || !!search;

  return {
    messages,
    total,
    failedTotal,
    loading,
    filters,
    search,
    channels,
    replayingId,
    bulkReplaying,
    currentPage,
    totalPages,
    hasActiveFilters,
    fetchMessages,
    handleFilterChange,
    handleSearchChange,
    handleReset,
    handleReplay,
    handleBulkReplay,
    setFilters,
  };
}
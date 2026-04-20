/**
 * frontend/src/pages/MessageLogPage.tsx
 *
 * Cross-channel message log with:
 *   - Filter by channel, channel type, agent, date range, success/failure
 *   - Full-text search
 *   - Per-message replay for failures
 *   - Bulk replay failed
 *   - Pagination
 */

import { memo, useMemo } from 'react';
import {
  Search, Filter, RefreshCw, RotateCcw, ChevronLeft, ChevronRight,
  CheckCircle2, XCircle, Clock, AlertTriangle, Inbox,
  MessageSquare, Calendar, User, Hash, LayoutGrid,
  ChevronDown, X, Play, AlertCircle, Zap, Loader2
} from "lucide-react";
import { useMessageLog, DEFAULT_FILTERS } from '@/hooks/useMessageLog';
import { getRelativeTime } from '@/utils/time';
import { ChannelMessage, MessageLogFilters } from '@/services/channelMessages';

// ─── Channel icons (emoji fallback) ──────────────────────────────────────────

const CHANNEL_ICONS: Record<string, string> = {
  whatsapp:    '💬',
  slack:       '🔷',
  telegram:    '✈️',
  email:       '✉️',
  discord:     '🎮',
  signal:      '🔒',
  google_chat: '💠',
  teams:       '🟦',
  zalo:        '🟩',
  matrix:      '🔳',
  imessage:    '🍎',
  custom:      '🔗',
};

const STATUS_CONFIG = {
  received:   { label: 'Received',   color: 'text-blue-600 dark:text-blue-400',      bg: 'bg-blue-100 dark:bg-blue-500/10',      icon: Clock       },
  processing: { label: 'Processing', color: 'text-yellow-600 dark:text-yellow-400',  bg: 'bg-yellow-100 dark:bg-yellow-500/10',  icon: Loader2     },
  responded:  { label: 'Responded',  color: 'text-emerald-600 dark:text-emerald-400',bg: 'bg-emerald-100 dark:bg-emerald-500/10',icon: CheckCircle2 },
  failed:     { label: 'Failed',     color: 'text-red-600 dark:text-red-400',        bg: 'bg-red-100 dark:bg-red-500/10',        icon: XCircle     },
};

const CHANNEL_TYPE_OPTIONS = [
  'whatsapp','slack','telegram','email','discord',
  'signal','google_chat','teams','zalo','matrix','imessage','custom',
];

// ─── Atoms ────────────────────────────────────────────────────────────────────

function StatusBadge({ status }: { status: string }) {
  const cfg = STATUS_CONFIG[status as keyof typeof STATUS_CONFIG] ?? STATUS_CONFIG.received;
  const Icon = cfg.icon;
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium ${cfg.color} ${cfg.bg}`}>
      <Icon className={`w-3 h-3 ${status === 'processing' ? 'animate-spin' : ''}`} />
      {cfg.label}
    </span>
  );
}

function ChannelBadge({ type, name }: { type: string; name: string }) {
  return (
    <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-md bg-slate-100 dark:bg-slate-700/50 text-slate-700 dark:text-slate-300 text-xs font-medium border border-slate-200 dark:border-slate-600/40">
      {/* aria-hidden prevents screen readers from announcing the emoji glyph name */}
      <span aria-hidden="true" className="text-sm leading-none">
        {CHANNEL_ICONS[type] ?? '📡'}
      </span>
      {name}
    </span>
  );
}

function FilterChip({ label, onRemove }: { label: string; onRemove: () => void }) {
  return (
    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-blue-100 dark:bg-blue-500/15 border border-blue-200 dark:border-blue-500/25 text-blue-700 dark:text-blue-300 text-xs">
      {label}
      <button onClick={onRemove} className="hover:text-slate-900 dark:hover:text-white transition-colors">
        <X className="w-3 h-3" />
      </button>
    </span>
  );
}

// ─── Filter bar ───────────────────────────────────────────────────────────────

interface FilterBarProps {
  filters: MessageLogFilters;
  channels: Array<{ id: string; name: string; type: string }>;
  onChange: (f: Partial<MessageLogFilters>) => void;
  onReset: () => void;
}

function FilterBar({ filters, channels, onChange, onReset }: FilterBarProps) {
  const [open, setOpen] = useState(false);
  const activeCount = [
    filters.channel_id, filters.channel_type, filters.agent_id,
    filters.status, filters.success !== undefined ? '1' : undefined,
    filters.date_from, filters.date_to,
  ].filter(Boolean).length;

  const panelId = 'message-log-filter-panel';

  return (
    <div className="relative">
      {/* Toggle button — accessible: announces expand state and controls target */}
      <button
        aria-expanded={open}
        aria-controls={panelId}
        aria-label="Toggle advanced filters"
        onClick={() => setOpen(o => !o)}
        className={`flex items-center gap-2 px-3 py-2 rounded-lg border text-sm font-medium transition-colors
          ${activeCount > 0
            ? 'bg-blue-100 dark:bg-blue-600/20 border-blue-300 dark:border-blue-500/40 text-blue-700 dark:text-blue-300'
            : 'bg-white dark:bg-slate-800 border-slate-200 dark:border-slate-600/50 text-slate-600 dark:text-slate-400 hover:text-slate-800 dark:hover:text-slate-200 hover:border-slate-300 dark:hover:border-slate-500'
          }`}
      >
        <Filter className="w-4 h-4" />
        Filters
        {activeCount > 0 && (
          <span className="bg-blue-600 dark:bg-blue-500 text-white text-xs w-5 h-5 rounded-full flex items-center justify-center">
            {activeCount}
          </span>
        )}
        <ChevronDown className={`w-3 h-3 transition-transform ${open ? 'rotate-180' : ''}`} />
      </button>

      {open && (
        // role="region" + aria-label lets assistive technology navigate to this panel
        <div
          id={panelId}
          role="region"
          aria-label="Advanced filters"
          className="absolute top-full right-0 mt-2 w-96 bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-600/50 rounded-xl shadow-xl shadow-slate-200/50 dark:shadow-black/50 z-30 p-4 space-y-3"
        >
          {/* Channel */}
          <div>
            <label className="text-xs text-slate-500 dark:text-slate-400 font-medium mb-1 block">Channel</label>
            <select
              value={filters.channel_id ?? ''}
              onChange={e => onChange({ channel_id: e.target.value || undefined })}
              className="w-full bg-slate-50 dark:bg-slate-700 border border-slate-200 dark:border-slate-600/50 rounded-lg px-3 py-1.5 text-sm text-slate-800 dark:text-slate-200 focus:outline-none focus:ring-1 focus:ring-blue-500"
            >
              <option value="">All channels</option>
              {channels.map(c => (
                <option key={c.id} value={c.id}>
                  {CHANNEL_ICONS[c.type] ?? '📡'} {c.name}
                </option>
              ))}
            </select>
          </div>

          {/* Channel type */}
          <div>
            <label className="text-xs text-slate-500 dark:text-slate-400 font-medium mb-1 block">Channel Type</label>
            <select
              value={filters.channel_type ?? ''}
              onChange={e => onChange({ channel_type: e.target.value || undefined })}
              className="w-full bg-slate-50 dark:bg-slate-700 border border-slate-200 dark:border-slate-600/50 rounded-lg px-3 py-1.5 text-sm text-slate-800 dark:text-slate-200 focus:outline-none focus:ring-1 focus:ring-blue-500"
            >
              <option value="">All types</option>
              {CHANNEL_TYPE_OPTIONS.map(t => (
                <option key={t} value={t}>{CHANNEL_ICONS[t] ?? '📡'} {t}</option>
              ))}
            </select>
          </div>

          {/* Status */}
          <div>
            <label className="text-xs text-slate-500 dark:text-slate-400 font-medium mb-1 block">Status</label>
            <div className="flex flex-wrap gap-1.5">
              {(['', 'received', 'processing', 'responded', 'failed'] as const).map(s => (
                <button
                  key={s}
                  onClick={() => onChange({ status: s || undefined, success: undefined })}
                  className={`px-2.5 py-1 rounded-lg text-xs font-medium transition-colors border
                    ${(filters.status ?? '') === s
                      ? 'bg-blue-100 dark:bg-blue-600/30 border-blue-300 dark:border-blue-500/50 text-blue-700 dark:text-blue-300'
                      : 'bg-slate-100 dark:bg-slate-700 border-slate-200 dark:border-slate-600/40 text-slate-600 dark:text-slate-400 hover:text-slate-800 dark:hover:text-slate-200'
                    }`}
                >
                  {s || 'All'}
                </button>
              ))}
            </div>
          </div>

          {/* Outcome quick filters */}
          <div>
            <label className="text-xs text-slate-500 dark:text-slate-400 font-medium mb-1 block">Outcome</label>
            <div className="flex gap-1.5">
              {[
                { label: 'Any',         value: undefined },
                { label: '✅ Success',  value: true      },
                { label: '❌ Failures', value: false     },
              ].map(opt => (
                <button
                  key={String(opt.value)}
                  onClick={() => onChange({ success: opt.value, status: undefined })}
                  className={`flex-1 py-1 rounded-lg text-xs font-medium transition-colors border
                    ${filters.success === opt.value
                      ? 'bg-blue-100 dark:bg-blue-600/30 border-blue-300 dark:border-blue-500/50 text-blue-700 dark:text-blue-300'
                      : 'bg-slate-100 dark:bg-slate-700 border-slate-200 dark:border-slate-600/40 text-slate-600 dark:text-slate-400 hover:text-slate-800 dark:hover:text-slate-200'
                    }`}
                >
                  {opt.label}
                </button>
              ))}
            </div>
          </div>

          {/* Date range */}
          <div className="grid grid-cols-2 gap-2">
            <div>
              <label className="text-xs text-slate-500 dark:text-slate-400 font-medium mb-1 block">From</label>
              <input
                type="datetime-local"
                value={filters.date_from?.slice(0, 16) ?? ''}
                onChange={e => onChange({ date_from: e.target.value ? e.target.value + ':00' : undefined })}
                className="w-full bg-slate-50 dark:bg-slate-700 border border-slate-200 dark:border-slate-600/50 rounded-lg px-2 py-1.5 text-xs text-slate-800 dark:text-slate-200 focus:outline-none focus:ring-1 focus:ring-blue-500"
              />
            </div>
            <div>
              <label className="text-xs text-slate-500 dark:text-slate-400 font-medium mb-1 block">To</label>
              <input
                type="datetime-local"
                value={filters.date_to?.slice(0, 16) ?? ''}
                onChange={e => onChange({ date_to: e.target.value ? e.target.value + ':00' : undefined })}
                className="w-full bg-slate-50 dark:bg-slate-700 border border-slate-200 dark:border-slate-600/50 rounded-lg px-2 py-1.5 text-xs text-slate-800 dark:text-slate-200 focus:outline-none focus:ring-1 focus:ring-blue-500"
              />
            </div>
          </div>

          {/* Agent ID */}
          <div>
            <label className="text-xs text-slate-500 dark:text-slate-400 font-medium mb-1 block">Agent ID</label>
            <input
              type="text"
              placeholder="e.g. 10001"
              value={filters.agent_id ?? ''}
              onChange={e => onChange({ agent_id: e.target.value || undefined })}
              className="w-full bg-slate-50 dark:bg-slate-700 border border-slate-200 dark:border-slate-600/50 rounded-lg px-3 py-1.5 text-sm text-slate-800 dark:text-slate-200 placeholder-slate-400 dark:placeholder-slate-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
            />
          </div>

          <div className="flex justify-end pt-1">
            <button
              onClick={() => { onReset(); setOpen(false); }}
              className="text-xs text-slate-500 dark:text-slate-400 hover:text-slate-700 dark:hover:text-slate-200 flex items-center gap-1 transition-colors"
            >
              <X className="w-3 h-3" /> Clear all filters
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

// ─── Message row ──────────────────────────────────────────────────────────────

interface MessageRowProps {
  msg: ChannelMessage;
  onReplay: (id: string) => Promise<void>;
  replayingId: string | null;
}

/**
 * React.memo: skips re-render when the parent re-renders for unrelated reasons
 * (e.g. loading spinner toggle, other messages updating).
 * Only re-renders when msg, replayingId, or onReplay reference changes.
 */
const MessageRow = memo(function MessageRow({ msg, onReplay, replayingId }: MessageRowProps) {
  const [expanded, setExpanded] = useState(false);
  const isReplaying = replayingId === msg.id;
  const canReplay   = msg.status === 'failed' || msg.error_count > 0;

  const ts = new Date(msg.created_at);

  // useMemo: avoids recomputing the relative time string on every render.
  // getRelativeTime is a pure function so the result is stable for the same input.
  const relativeTime = useMemo(() => getRelativeTime(msg.created_at), [msg.created_at]);

  return (
    <div
      className={`border rounded-xl overflow-hidden transition-colors ${
        msg.status === 'failed'
          ? 'border-red-300 dark:border-red-500/20 bg-red-50 dark:bg-red-500/5 hover:bg-red-100 dark:hover:bg-red-500/8'
          : 'border-slate-200 dark:border-slate-700/50 bg-white dark:bg-slate-800/40 hover:bg-slate-50 dark:hover:bg-slate-800/70'
      }`}
    >
      {/* Main row */}
      <div
        className="flex items-center gap-3 px-4 py-3 cursor-pointer"
        onClick={() => setExpanded(e => !e)}
      >
        {/* Channel icon — aria-hidden so screen readers announce channel name, not emoji */}
        <span aria-hidden="true" className="text-xl flex-shrink-0 w-7 text-center">
          {CHANNEL_ICONS[msg.channel_type] ?? '📡'}
        </span>

        {/* Content */}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-sm text-slate-800 dark:text-slate-200 font-medium truncate max-w-xs">
              {msg.sender_name || msg.sender_id}
            </span>
            <ChannelBadge type={msg.channel_type} name={msg.channel_name} />
            {msg.task_id && (
              <span className="text-xs text-slate-500 dark:text-slate-500 font-mono">
                #{msg.task_id.slice(0, 8)}
              </span>
            )}
          </div>
          <p className="text-sm text-slate-500 dark:text-slate-400 truncate mt-0.5">
            {msg.content || <em className="text-slate-400 dark:text-slate-600">no content</em>}
          </p>
          {msg.last_error && (
            <p className="text-xs text-red-600 dark:text-red-400 truncate mt-0.5 flex items-center gap-1">
              <AlertCircle className="w-3 h-3 flex-shrink-0" /> {msg.last_error}
            </p>
          )}
        </div>

        {/* Right side */}
        <div className="flex items-center gap-3 flex-shrink-0">
          <StatusBadge status={msg.status} />
          <span className="text-xs text-slate-500 dark:text-slate-500 w-16 text-right">
            {relativeTime}
          </span>

          {canReplay && (
            <button
              onClick={e => { e.stopPropagation(); onReplay(msg.id); }}
              disabled={isReplaying}
              className="flex items-center gap-1 px-2.5 py-1 rounded-lg bg-amber-100 dark:bg-amber-500/15 border border-amber-300 dark:border-amber-500/30 text-amber-700 dark:text-amber-400 text-xs font-medium hover:bg-amber-200 dark:hover:bg-amber-500/25 transition-colors disabled:opacity-50"
            >
              {isReplaying
                ? <LoadingSpinner size="xs" />
                : <Play className="w-3 h-3" />
              }
              Replay
            </button>
          )}

          <ChevronDown className={`w-4 h-4 text-slate-400 dark:text-slate-500 transition-transform ${expanded ? 'rotate-180' : ''}`} />
        </div>
      </div>

      {/* Expanded details */}
      {expanded && (
        <div className="border-t border-slate-200 dark:border-slate-700/50 px-4 py-3 bg-slate-50 dark:bg-slate-900/30 space-y-3">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            {[
              { icon: Hash,        label: 'Message ID', value: msg.id           },
              { icon: MessageSquare, label: 'Type',     value: msg.message_type },
              { icon: User,        label: 'Sender ID',  value: msg.sender_id    },
              { icon: Calendar,    label: 'Received',   value: ts.toLocaleString() },
              ...(msg.assigned_agent_id ? [{ icon: Zap,        label: 'Agent', value: msg.assigned_agent_id }] : []),
              ...(msg.task_id           ? [{ icon: LayoutGrid, label: 'Task',  value: msg.task_id           }] : []),
            ].map(({ icon: Icon, label, value }) => (
              <div key={label}>
                <span className="text-xs text-slate-500 dark:text-slate-500 flex items-center gap-1 mb-0.5">
                  <Icon className="w-3 h-3" /> {label}
                </span>
                <span className="text-xs text-slate-700 dark:text-slate-300 font-mono break-all">{value}</span>
              </div>
            ))}
          </div>

          {msg.content && (
            <div>
              <span className="text-xs text-slate-500 dark:text-slate-500 block mb-1">Full Content</span>
              <pre className="text-xs text-slate-700 dark:text-slate-300 bg-slate-100 dark:bg-slate-900/60 rounded-lg p-3 whitespace-pre-wrap break-words max-h-48 overflow-y-auto">
                {msg.content}
              </pre>
            </div>
          )}

          {msg.error_count > 0 && (
            <div className="flex items-center gap-2">
              <AlertTriangle className="w-3.5 h-3.5 text-red-600 dark:text-red-400 flex-shrink-0" />
              <span className="text-xs text-red-600 dark:text-red-400">
                {msg.error_count} error{msg.error_count > 1 ? 's' : ''} recorded
                {msg.last_error && ` — ${msg.last_error}`}
              </span>
            </div>
          )}
        </div>
      )}
    </div>
  );
});

// ─── Main page ────────────────────────────────────────────────────────────────

// useState is still needed locally by FilterBar; import it here so the file
// compiles without importing from React at the top (memo + useMemo already pull it in).
import { useState } from 'react';
import { LoadingSpinner } from '@/components/ui/LoadingSpinner';
import { EmptyState } from '@/components/ui/EmptyState';

export function MessageLogPage() {
  const {
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
  } = useMessageLog();

  return (
    <div className="flex flex-col h-full min-h-0 bg-white dark:bg-[#0f1117] text-slate-900 dark:text-slate-100 transition-colors duration-200">

      {/* Header */}
      <div className="flex-shrink-0 px-6 py-4 border-b border-slate-200 dark:border-slate-700/50 bg-white/80 dark:bg-[#0f1117]/80 backdrop-blur-sm transition-colors duration-200">
        <div className="flex items-center justify-between flex-wrap gap-3">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-lg bg-blue-100 dark:bg-blue-600/20 border border-blue-200 dark:border-blue-500/30 flex items-center justify-center">
              <Inbox className="w-4 h-4 text-blue-600 dark:text-blue-400" />
            </div>
            <div>
              <h1 className="text-lg font-semibold text-slate-900 dark:text-slate-100">Message Log</h1>
              <p className="text-xs text-slate-500 dark:text-slate-400">
                {total.toLocaleString()} message{total !== 1 ? 's' : ''} across all channels
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            {/* failedTotal: counts across the full dataset, not just the visible page */}
            {failedTotal > 0 && (
              <button
                onClick={handleBulkReplay}
                disabled={bulkReplaying}
                className="flex items-center gap-1.5 px-3 py-2 rounded-lg bg-amber-100 dark:bg-amber-500/15 border border-amber-300 dark:border-amber-500/30 text-amber-700 dark:text-amber-400 text-sm font-medium hover:bg-amber-200 dark:hover:bg-amber-500/25 transition-colors disabled:opacity-50"
              >
                {bulkReplaying
                  ? <LoadingSpinner size="sm" />
                  : <RotateCcw className="w-4 h-4" />
                }
                Replay {failedTotal} Failed
              </button>
            )}
            <button
              onClick={() => fetchMessages(filters)}
              className="p-2 rounded-lg bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-600/50 text-slate-500 dark:text-slate-400 hover:text-slate-700 dark:hover:text-slate-200 transition-colors"
              aria-label="Refresh message log"
            >
              <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
            </button>
          </div>
        </div>

        {/* Filter row */}
        <div className="flex items-center gap-2 mt-3 flex-wrap">
          {/* Search */}
          <div className="relative flex-1 min-w-52">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400 dark:text-slate-500" />
            <input
              type="text"
              placeholder="Search messages, senders…"
              value={search}
              onChange={e => handleSearchChange(e.target.value)}
              className="w-full pl-9 pr-3 py-2 bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-600/50 rounded-lg text-sm text-slate-800 dark:text-slate-200 placeholder-slate-400 dark:placeholder-slate-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
            />
          </div>

          <FilterBar
            filters={filters}
            channels={channels}
            onChange={handleFilterChange}
            onReset={handleReset}
          />

          {hasActiveFilters && (
            <button
              onClick={handleReset}
              className="flex items-center gap-1 px-2 py-2 rounded-lg text-xs text-slate-500 dark:text-slate-400 hover:text-slate-700 dark:hover:text-slate-200 transition-colors"
            >
              <X className="w-3.5 h-3.5" /> Clear
            </button>
          )}
        </div>

        {/* Active filter chips */}
        {hasActiveFilters && (
          <div className="flex flex-wrap gap-1.5 mt-2">
            {filters.channel_id && (
              <FilterChip
                label={`Channel: ${channels.find(c => c.id === filters.channel_id)?.name ?? filters.channel_id}`}
                onRemove={() => handleFilterChange({ channel_id: undefined })}
              />
            )}
            {filters.channel_type && (
              <FilterChip
                label={`Type: ${filters.channel_type}`}
                onRemove={() => handleFilterChange({ channel_type: undefined })}
              />
            )}
            {filters.status && (
              <FilterChip
                label={`Status: ${filters.status}`}
                onRemove={() => handleFilterChange({ status: undefined })}
              />
            )}
            {filters.success !== undefined && (
              <FilterChip
                label={filters.success ? 'Successes only' : 'Failures only'}
                onRemove={() => handleFilterChange({ success: undefined })}
              />
            )}
            {filters.date_from && (
              <FilterChip
                label={`From: ${new Date(filters.date_from).toLocaleDateString()}`}
                onRemove={() => handleFilterChange({ date_from: undefined })}
              />
            )}
            {filters.date_to && (
              <FilterChip
                label={`To: ${new Date(filters.date_to).toLocaleDateString()}`}
                onRemove={() => handleFilterChange({ date_to: undefined })}
              />
            )}
            {filters.agent_id && (
              <FilterChip
                label={`Agent: ${filters.agent_id}`}
                onRemove={() => handleFilterChange({ agent_id: undefined })}
              />
            )}
            {search && (
              <FilterChip
                label={`Search: "${search}"`}
                onRemove={() => handleSearchChange('')}
              />
            )}
          </div>
        )}
      </div>

      {/* Message list */}
      <div className="flex-1 overflow-y-auto px-6 py-4 space-y-2 bg-slate-50 dark:bg-[#0f1117] transition-colors duration-200">
        {loading && messages.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-20 text-slate-400 dark:text-slate-500">
            <LoadingSpinner size="lg" />
            <p className="text-sm">Loading messages…</p>
          </div>
        ) : messages.length === 0 ? (
          <EmptyState
            icon={Inbox}
            title="No messages found"
            description={hasActiveFilters ? 'Try adjusting or clearing your filters' : undefined}
          />
        ) : (
          messages.map(msg => (
            <MessageRow
              key={msg.id}
              msg={msg}
              onReplay={handleReplay}
              replayingId={replayingId}
            />
          ))
        )}
      </div>

      {/* Pagination */}
      {total > (filters.limit ?? 50) && (
        <div className="flex-shrink-0 flex items-center justify-between px-6 py-3 border-t border-slate-200 dark:border-slate-700/50 bg-white/80 dark:bg-[#0f1117]/80 transition-colors duration-200">
          <span className="text-xs text-slate-500 dark:text-slate-500">
            Showing {(filters.offset ?? 0) + 1}–{Math.min((filters.offset ?? 0) + (filters.limit ?? 50), total)} of {total.toLocaleString()}
          </span>
          <div className="flex items-center gap-2">
            <button
              disabled={(filters.offset ?? 0) === 0}
              onClick={() => setFilters(p => ({ ...p, offset: Math.max(0, (p.offset ?? 0) - (p.limit ?? 50)) }))}
              className="p-1.5 rounded-lg bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-600/50 text-slate-500 dark:text-slate-400 hover:text-slate-700 dark:hover:text-slate-200 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
              aria-label="Previous page"
            >
              <ChevronLeft className="w-4 h-4" />
            </button>
            <span className="text-xs text-slate-500 dark:text-slate-400 px-2">
              {currentPage} / {totalPages}
            </span>
            <button
              disabled={currentPage >= totalPages}
              onClick={() => setFilters(p => ({ ...p, offset: (p.offset ?? 0) + (p.limit ?? 50) }))}
              className="p-1.5 rounded-lg bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-600/50 text-slate-500 dark:text-slate-400 hover:text-slate-700 dark:hover:text-slate-200 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
              aria-label="Next page"
            >
              <ChevronRight className="w-4 h-4" />
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
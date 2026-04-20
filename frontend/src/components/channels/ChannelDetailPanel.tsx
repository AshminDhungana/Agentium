// src/components/channels/ChannelDetailPanel.tsx
// ─────────────────────────────────────────────────────────────────────────────
// Phase 15.3 — Channel Health Monitoring, Logs & Settings
//
// A right-side slide-in panel that opens when a channel is selected in
// ChannelsPage. Three tabs:
//   Health   — status badge, last message time, 24h error count, circuit
//               breaker state, rate limit utilisation bar
//   Logs     — scrollable paginated ExternalMessage history with status and
//               sender filters
//   Settings — rate limit slider, auto-task toggle, default agent dropdown,
//               content filter keyword list
// ─────────────────────────────────────────────────────────────────────────────

import { useState, useCallback } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from '@/services/api';
import { channelMetricsApi } from '@/services/channelMetrics';
import { format, formatDistanceToNow } from 'date-fns';
import {
    X,
    Activity,
    MessageSquare,
    Settings,
    CheckCircle,
    XCircle,
    Clock,
    AlertTriangle,
    ChevronLeft,
    ChevronRight,
    Search,
    Plus,
    Trash2,
} from 'lucide-react';
import type {
    Channel,
    ChannelHealthDetail,
    ChannelSettings,
    ChannelLogFilters,
    MessageLog,
    Agent,
} from '@/types';
import { CircuitBreakerBadge } from './CircuitBreakerBadge';
import { getHealthBadgeProps } from '@/utils/channelHealth';
import { showToast } from '@/hooks/useToast';
import { LoadingSpinner } from '@/components/ui/LoadingSpinner';

// ─── Types ────────────────────────────────────────────────────────────────────

type PanelTab = 'health' | 'logs' | 'settings';

const LOG_PAGE_SIZE = 25;

// ─── Sub-components ───────────────────────────────────────────────────────────

function StatusIcon({ status }: { status: string }) {
    switch (status) {
        case 'responded':  return <CheckCircle  className="w-3.5 h-3.5 text-green-500 shrink-0"  />;
        case 'failed':     return <XCircle      className="w-3.5 h-3.5 text-red-500 shrink-0"    />;
        case 'processing': return <Clock        className="w-3.5 h-3.5 text-yellow-500 animate-spin shrink-0" />;
        default:           return <AlertTriangle className="w-3.5 h-3.5 text-gray-400 shrink-0"  />;
    }
}

function TabButton({
    label,
    icon: Icon,
    active,
    onClick,
}: {
    label: string;
    icon: React.ElementType;
    active: boolean;
    onClick: () => void;
}) {
    return (
        <button
            onClick={onClick}
            className={`flex items-center gap-1.5 px-3 py-2 text-sm font-medium rounded-lg transition-colors ${
                active
                    ? 'bg-blue-50 dark:bg-blue-500/10 text-blue-700 dark:text-blue-400'
                    : 'text-gray-500 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-[#1e2535]'
            }`}
        >
            <Icon className="w-4 h-4" />
            {label}
        </button>
    );
}

// ─── Health Tab ────────────────────────────────────────────────────────────────

function HealthTab({ channel }: { channel: Channel }) {
    const { data: health, isLoading } = useQuery<ChannelHealthDetail>({
        queryKey: ['channel-health-detail', channel.id],
        queryFn: () => api.get(`/api/v1/channels/${channel.id}/health`).then(r => r.data),
        staleTime: 30_000,
        refetchInterval: 60_000,
    });

    const { data: metricsData, isLoading: metricsLoading } = useQuery({
        queryKey: ['channel-metrics', channel.id],
        queryFn: () => channelMetricsApi.getChannelMetrics(channel.id),
        staleTime: 30_000,
        refetchInterval: 30_000,
    });

    if (isLoading || metricsLoading) {
        return (
            <div className="flex items-center justify-center py-12">
                <LoadingSpinner size="md" />
            </div>
        );
    }

    const stats = health?.statistics;
    const rateLimits = health?.rate_limits;
    const metrics = metricsData?.metrics;
    const healthStatus = metricsData?.health_status ?? 'healthy';
    const colors = getHealthBadgeProps(healthStatus);

    return (
        <div className="space-y-5">
            {/* Status + circuit breaker */}
            <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                    <div className={`w-2.5 h-2.5 rounded-full ${colors.indicator}`} />
                    <span className={`text-xs px-2 py-0.5 rounded-full border font-medium uppercase ${colors.bg} ${colors.border} ${colors.text}`}>
                        {healthStatus}
                    </span>
                </div>
                {metrics && <CircuitBreakerBadge state={metrics.circuit_breaker_state} />}
            </div>

            {/* Key stats grid */}
            <div className="grid grid-cols-2 gap-3">
                <div className="p-3 bg-gray-50 dark:bg-[#0f1117] rounded-xl border border-gray-200 dark:border-[#1e2535]">
                    <div className="text-xs text-gray-500 dark:text-gray-400 mb-1">Success rate</div>
                    <div className={`text-xl font-bold ${colors.text}`}>
                        {metrics ? `${metrics.success_rate.toFixed(1)}%` : '—'}
                    </div>
                </div>
                <div className="p-3 bg-gray-50 dark:bg-[#0f1117] rounded-xl border border-gray-200 dark:border-[#1e2535]">
                    <div className="text-xs text-gray-500 dark:text-gray-400 mb-1">Errors (24 h)</div>
                    <div className={`text-xl font-bold ${
                        (stats?.error_count_24h ?? 0) > 0
                            ? 'text-red-600 dark:text-red-400'
                            : 'text-gray-800 dark:text-gray-200'
                    }`}>
                        {stats?.error_count_24h ?? 0}
                    </div>
                </div>
                <div className="p-3 bg-gray-50 dark:bg-[#0f1117] rounded-xl border border-gray-200 dark:border-[#1e2535]">
                    <div className="text-xs text-gray-500 dark:text-gray-400 mb-1">Consecutive failures</div>
                    <div className={`text-xl font-bold ${
                        (metrics?.consecutive_failures ?? 0) > 2
                            ? 'text-red-600 dark:text-red-400'
                            : 'text-gray-800 dark:text-gray-200'
                    }`}>
                        {metrics?.consecutive_failures ?? 0}
                    </div>
                </div>
                <div className="p-3 bg-gray-50 dark:bg-[#0f1117] rounded-xl border border-gray-200 dark:border-[#1e2535]">
                    <div className="text-xs text-gray-500 dark:text-gray-400 mb-1">Rate limit hits</div>
                    <div className={`text-xl font-bold ${
                        (metrics?.rate_limit_hits ?? 0) > 0
                            ? 'text-yellow-600 dark:text-yellow-400'
                            : 'text-gray-800 dark:text-gray-200'
                    }`}>
                        {metrics?.rate_limit_hits ?? 0}
                    </div>
                </div>
            </div>

            {/* Last message */}
            {stats?.last_message_at && (
                <div className="flex items-center justify-between text-sm">
                    <span className="text-gray-500 dark:text-gray-400">Last message</span>
                    <span className="text-gray-900 dark:text-gray-100 font-medium">
                        {formatDistanceToNow(new Date(stats.last_message_at), { addSuffix: true })}
                    </span>
                </div>
            )}

            {/* Rate limit utilisation bar */}
            {rateLimits && (
                <div>
                    <div className="flex items-center justify-between mb-1.5">
                        <span className="text-xs text-gray-500 dark:text-gray-400">Rate limit utilisation</span>
                        <span className="text-xs font-medium text-gray-700 dark:text-gray-300">
                            {rateLimits.utilization_pct}%
                        </span>
                    </div>
                    <div className="h-2 bg-gray-200 dark:bg-[#1e2535] rounded-full overflow-hidden">
                        <div
                            className={`h-full rounded-full transition-all ${
                                rateLimits.utilization_pct > 80
                                    ? 'bg-red-500'
                                    : rateLimits.utilization_pct > 50
                                        ? 'bg-yellow-500'
                                        : 'bg-green-500'
                            }`}
                            style={{ width: `${Math.min(rateLimits.utilization_pct, 100)}%` }}
                        />
                    </div>
                    <div className="flex justify-between mt-1 text-[11px] text-gray-400 dark:text-gray-500">
                        <span>{rateLimits.platform_limits.requests_per_minute}/min</span>
                        <span>{rateLimits.platform_limits.requests_per_hour}/hr</span>
                    </div>
                </div>
            )}

            {/* Total traffic */}
            <div className="flex gap-4 text-sm border-t border-gray-100 dark:border-[#1e2535] pt-4">
                <div>
                    <span className="text-gray-400 dark:text-gray-500 text-xs uppercase tracking-wide">Received </span>
                    <span className="font-semibold text-gray-900 dark:text-gray-100">
                        {stats?.total_messages_received ?? channel.stats?.received ?? 0}
                    </span>
                </div>
                <div>
                    <span className="text-gray-400 dark:text-gray-500 text-xs uppercase tracking-wide">Sent </span>
                    <span className="font-semibold text-gray-900 dark:text-gray-100">
                        {stats?.total_messages_sent ?? channel.stats?.sent ?? 0}
                    </span>
                </div>
            </div>
        </div>
    );
}

// ─── Logs Tab ─────────────────────────────────────────────────────────────────

function LogsTab({ channel }: { channel: Channel }) {
    const [filters, setFilters] = useState<ChannelLogFilters>({ limit: LOG_PAGE_SIZE, offset: 0 });
    const [senderInput, setSenderInput] = useState('');
    const [page, setPage] = useState(0);

    const effectiveFilters: ChannelLogFilters = {
        ...filters,
        limit: LOG_PAGE_SIZE,
        offset: page * LOG_PAGE_SIZE,
    };

    const { data, isLoading, isFetching } = useQuery({
        queryKey: ['channel-logs', channel.id, effectiveFilters],
        queryFn: () => channelMetricsApi.getChannelLogs(channel.id, effectiveFilters),
        staleTime: 15_000,
        placeholderData: (prev) => prev,
    });

    const messages: MessageLog[] = data?.messages ?? [];
    const total = data?.total ?? 0;
    const totalPages = Math.ceil(total / LOG_PAGE_SIZE);

    const applySearch = useCallback(() => {
        setFilters(f => ({ ...f, sender_id: senderInput || undefined }));
        setPage(0);
    }, [senderInput]);

    return (
        <div className="space-y-3">
            {/* Filters bar */}
            <div className="flex gap-2">
                {/* Status filter */}
                <select
                    value={filters.status ?? ''}
                    onChange={e => {
                        setFilters(f => ({ ...f, status: (e.target.value as ChannelLogFilters['status']) || undefined }));
                        setPage(0);
                    }}
                    className="flex-1 px-2 py-1.5 text-xs border border-gray-300 dark:border-[#1e2535] rounded-lg bg-white dark:bg-[#0f1117] text-gray-900 dark:text-white focus:ring-1 focus:ring-blue-500 outline-none"
                >
                    <option value="">All statuses</option>
                    <option value="received">Received</option>
                    <option value="processing">Processing</option>
                    <option value="responded">Responded</option>
                    <option value="failed">Failed</option>
                </select>

                {/* Sender search */}
                <div className="flex flex-1 gap-1">
                    <input
                        value={senderInput}
                        onChange={e => setSenderInput(e.target.value)}
                        onKeyDown={e => e.key === 'Enter' && applySearch()}
                        placeholder="Search sender…"
                        className="flex-1 px-2 py-1.5 text-xs border border-gray-300 dark:border-[#1e2535] rounded-lg bg-white dark:bg-[#0f1117] text-gray-900 dark:text-white placeholder-gray-400 focus:ring-1 focus:ring-blue-500 outline-none"
                    />
                    <button
                        onClick={applySearch}
                        className="px-2 py-1.5 bg-gray-100 dark:bg-[#1e2535] border border-gray-300 dark:border-[#2a3347] rounded-lg hover:bg-gray-200 dark:hover:bg-[#2a3347] transition-colors"
                    >
                        <Search className="w-3.5 h-3.5 text-gray-500 dark:text-gray-400" />
                    </button>
                </div>
            </div>

            {/* Log table */}
            <div className="border border-gray-200 dark:border-[#1e2535] rounded-xl overflow-hidden">
                {/* Header */}
                <div className="bg-gray-50 dark:bg-[#0f1117] px-3 py-2 border-b border-gray-200 dark:border-[#1e2535] flex items-center justify-between">
                    <span className="text-xs font-semibold text-gray-600 dark:text-gray-400">
                        {total} message{total !== 1 ? 's' : ''}
                    </span>
                    {isFetching && <LoadingSpinner size="xs" />}
                </div>

                {isLoading ? (
                    <div className="flex items-center justify-center py-8">
                        <LoadingSpinner size="md" />
                    </div>
                ) : messages.length === 0 ? (
                    <div className="py-8 text-center text-sm text-gray-400 dark:text-gray-500">
                        No messages match the current filters
                    </div>
                ) : (
                    <div className="divide-y divide-gray-100 dark:divide-[#1e2535] max-h-72 overflow-y-auto">
                        {messages.map(msg => (
                            <div key={msg.id} className="px-3 py-2.5 hover:bg-gray-50 dark:hover:bg-[#0f1117] transition-colors">
                                <div className="flex items-start gap-2">
                                    <StatusIcon status={msg.status} />
                                    <div className="flex-1 min-w-0">
                                        <div className="flex items-center justify-between gap-2">
                                            <span className="text-xs font-medium text-gray-900 dark:text-gray-100 truncate">
                                                {msg.sender_name || msg.sender_id}
                                            </span>
                                            <span className="text-[11px] text-gray-400 dark:text-gray-500 shrink-0">
                                                {format(new Date(msg.created_at), 'MMM d, HH:mm')}
                                            </span>
                                        </div>
                                        <p className="text-xs text-gray-500 dark:text-gray-400 truncate mt-0.5">
                                            {msg.content}
                                        </p>
                                        {msg.last_error && (
                                            <p className="text-[11px] text-red-500 dark:text-red-400 truncate mt-0.5">
                                                {msg.last_error}
                                            </p>
                                        )}
                                    </div>
                                </div>
                            </div>
                        ))}
                    </div>
                )}
            </div>

            {/* Pagination */}
            {totalPages > 1 && (
                <div className="flex items-center justify-between text-xs">
                    <button
                        onClick={() => setPage(p => Math.max(0, p - 1))}
                        disabled={page === 0}
                        className="flex items-center gap-1 px-2 py-1 rounded-lg bg-gray-100 dark:bg-[#1e2535] text-gray-600 dark:text-gray-400 disabled:opacity-40 hover:bg-gray-200 dark:hover:bg-[#2a3347] transition-colors"
                    >
                        <ChevronLeft className="w-3.5 h-3.5" /> Prev
                    </button>
                    <span className="text-gray-500 dark:text-gray-400">
                        {page + 1} / {totalPages}
                    </span>
                    <button
                        onClick={() => setPage(p => Math.min(totalPages - 1, p + 1))}
                        disabled={page >= totalPages - 1}
                        className="flex items-center gap-1 px-2 py-1 rounded-lg bg-gray-100 dark:bg-[#1e2535] text-gray-600 dark:text-gray-400 disabled:opacity-40 hover:bg-gray-200 dark:hover:bg-[#2a3347] transition-colors"
                    >
                        Next <ChevronRight className="w-3.5 h-3.5" />
                    </button>
                </div>
            )}
        </div>
    );
}

// ─── Settings Tab ─────────────────────────────────────────────────────────────

function SettingsTab({ channel }: { channel: Channel }) {
    const queryClient = useQueryClient();

    const [local, setLocal] = useState<ChannelSettings>({
        rate_limit_per_minute: channel.config?.rate_limit_per_minute ?? 60,
        rate_limit_per_hour:   channel.config?.rate_limit_per_hour   ?? 1000,
        auto_create_tasks:     channel.routing?.auto_create_tasks     ?? true,
        require_approval:      channel.routing?.require_approval      ?? false,
        default_agent_id:      channel.routing?.default_agent         ?? '',
        content_filters:       channel.config?.content_filters        ?? [],
    });
    const [keywordInput, setKeywordInput] = useState('');

    // Fetch active agents for the default-agent dropdown
    const { data: agentsData } = useQuery({
        queryKey: ['agents-active'],
        queryFn: () =>
            api.get<{ agents: Agent[] }>('/api/v1/agents/').then(r => r.data),
        staleTime: 60_000,
        select: (d) =>
            (d?.agents ?? []).filter(a => a.status === 'active' && !a.is_terminated),
    });

    const saveMutation = useMutation({
        mutationFn: () => channelMetricsApi.updateChannelSettings(channel.id, local),
        onSuccess: () => {
            showToast.success('Settings saved');
            queryClient.invalidateQueries({ queryKey: ['channels'] });
        },
        onError: () => showToast.error('Failed to save settings'),
    });

    const addKeyword = () => {
        const kw = keywordInput.trim().toLowerCase();
        if (!kw || local.content_filters?.includes(kw)) return;
        setLocal(s => ({ ...s, content_filters: [...(s.content_filters ?? []), kw] }));
        setKeywordInput('');
    };

    const removeKeyword = (kw: string) =>
        setLocal(s => ({ ...s, content_filters: (s.content_filters ?? []).filter(k => k !== kw) }));

    return (
        <div className="space-y-6">
            {/* Rate limits */}
            <section>
                <h4 className="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wider mb-3">
                    Rate limits
                </h4>
                <div className="space-y-4">
                    <div>
                        <div className="flex justify-between text-sm mb-1.5">
                            <label className="text-gray-700 dark:text-gray-300">Per minute</label>
                            <span className="font-medium text-gray-900 dark:text-white">{local.rate_limit_per_minute}</span>
                        </div>
                        <input
                            type="range"
                            min={1}
                            max={600}
                            step={1}
                            value={local.rate_limit_per_minute}
                            onChange={e => setLocal(s => ({ ...s, rate_limit_per_minute: Number(e.target.value) }))}
                            className="w-full accent-blue-600"
                        />
                        <div className="flex justify-between text-[11px] text-gray-400 mt-0.5">
                            <span>1</span><span>600</span>
                        </div>
                    </div>

                    <div>
                        <div className="flex justify-between text-sm mb-1.5">
                            <label className="text-gray-700 dark:text-gray-300">Per hour</label>
                            <span className="font-medium text-gray-900 dark:text-white">{local.rate_limit_per_hour}</span>
                        </div>
                        <input
                            type="range"
                            min={1}
                            max={10000}
                            step={50}
                            value={local.rate_limit_per_hour}
                            onChange={e => setLocal(s => ({ ...s, rate_limit_per_hour: Number(e.target.value) }))}
                            className="w-full accent-blue-600"
                        />
                        <div className="flex justify-between text-[11px] text-gray-400 mt-0.5">
                            <span>1</span><span>10,000</span>
                        </div>
                    </div>
                </div>
            </section>

            {/* Routing toggles */}
            <section>
                <h4 className="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wider mb-3">
                    Routing
                </h4>
                <div className="space-y-3">
                    {/* Auto-create tasks */}
                    <label className="flex items-center justify-between cursor-pointer">
                        <div>
                            <p className="text-sm text-gray-800 dark:text-gray-200">Auto-create tasks</p>
                            <p className="text-xs text-gray-500 dark:text-gray-400">
                                Automatically queue a task for each inbound message
                            </p>
                        </div>
                        <button
                            type="button"
                            role="switch"
                            aria-checked={local.auto_create_tasks}
                            onClick={() => setLocal(s => ({ ...s, auto_create_tasks: !s.auto_create_tasks }))}
                            className={`relative w-10 h-6 rounded-full transition-colors ${
                                local.auto_create_tasks ? 'bg-blue-600' : 'bg-gray-300 dark:bg-gray-600'
                            }`}
                        >
                            <span className={`absolute top-0.5 left-0.5 w-5 h-5 bg-white rounded-full shadow transition-transform ${
                                local.auto_create_tasks ? 'translate-x-4' : ''
                            }`} />
                        </button>
                    </label>

                    {/* Require approval */}
                    <label className="flex items-center justify-between cursor-pointer">
                        <div>
                            <p className="text-sm text-gray-800 dark:text-gray-200">Require approval</p>
                            <p className="text-xs text-gray-500 dark:text-gray-400">
                                Agent responses need sovereign sign-off before sending
                            </p>
                        </div>
                        <button
                            type="button"
                            role="switch"
                            aria-checked={local.require_approval}
                            onClick={() => setLocal(s => ({ ...s, require_approval: !s.require_approval }))}
                            className={`relative w-10 h-6 rounded-full transition-colors ${
                                local.require_approval ? 'bg-blue-600' : 'bg-gray-300 dark:bg-gray-600'
                            }`}
                        >
                            <span className={`absolute top-0.5 left-0.5 w-5 h-5 bg-white rounded-full shadow transition-transform ${
                                local.require_approval ? 'translate-x-4' : ''
                            }`} />
                        </button>
                    </label>
                </div>
            </section>

            {/* Default agent */}
            <section>
                <h4 className="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wider mb-3">
                    Default agent
                </h4>
                <select
                    value={local.default_agent_id ?? ''}
                    onChange={e => setLocal(s => ({ ...s, default_agent_id: e.target.value || undefined }))}
                    className="w-full px-3 py-2 text-sm border border-gray-300 dark:border-[#1e2535] rounded-lg bg-white dark:bg-[#0f1117] text-gray-900 dark:text-white focus:ring-2 focus:ring-blue-500 outline-none"
                >
                    <option value="">— Auto-assign —</option>
                    {(agentsData ?? []).map(a => (
                        <option key={a.id} value={a.id}>
                            {a.name} ({a.agent_type.replace(/_/g, ' ')})
                        </option>
                    ))}
                </select>
            </section>

            {/* Content filters */}
            <section>
                <h4 className="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wider mb-1">
                    Content filters
                </h4>
                <p className="text-xs text-gray-400 dark:text-gray-500 mb-3">
                    Messages containing these keywords will be dropped
                </p>

                {/* Keyword chips */}
                <div className="flex flex-wrap gap-1.5 mb-2 min-h-[28px]">
                    {(local.content_filters ?? []).map(kw => (
                        <span
                            key={kw}
                            className="inline-flex items-center gap-1 px-2 py-0.5 bg-red-100 dark:bg-red-500/15 text-red-700 dark:text-red-300 rounded-full text-xs"
                        >
                            {kw}
                            <button
                                onClick={() => removeKeyword(kw)}
                                className="hover:text-red-900 dark:hover:text-red-100 ml-0.5"
                                aria-label={`Remove keyword "${kw}"`}
                            >
                                <Trash2 className="w-3 h-3" />
                            </button>
                        </span>
                    ))}
                    {(local.content_filters ?? []).length === 0 && (
                        <span className="text-xs text-gray-400 dark:text-gray-500">No filters set</span>
                    )}
                </div>

                {/* Add keyword */}
                <div className="flex gap-2">
                    <input
                        value={keywordInput}
                        onChange={e => setKeywordInput(e.target.value)}
                        onKeyDown={e => e.key === 'Enter' && addKeyword()}
                        placeholder="Add keyword (Enter to add)"
                        className="flex-1 px-3 py-1.5 text-xs border border-gray-300 dark:border-[#1e2535] rounded-lg bg-white dark:bg-[#0f1117] text-gray-900 dark:text-white placeholder-gray-400 focus:ring-1 focus:ring-blue-500 outline-none"
                    />
                    <button
                        onClick={addKeyword}
                        className="px-2.5 py-1.5 bg-gray-100 dark:bg-[#1e2535] border border-gray-300 dark:border-[#2a3347] rounded-lg hover:bg-gray-200 dark:hover:bg-[#2a3347] transition-colors"
                        aria-label="Add keyword"
                    >
                        <Plus className="w-3.5 h-3.5 text-gray-600 dark:text-gray-400" />
                    </button>
                </div>
            </section>

            {/* Save button */}
            <button
                onClick={() => saveMutation.mutate()}
                disabled={saveMutation.isPending}
                className="w-full flex items-center justify-center gap-2 py-2.5 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white text-sm font-medium rounded-lg transition-colors"
            >
                {saveMutation.isPending
                    ? <><LoadingSpinner size="sm" /> Saving…</>
                    : 'Save settings'
                }
            </button>
        </div>
    );
}

// ─── Main export ──────────────────────────────────────────────────────────────

export interface ChannelDetailPanelProps {
    channel: Channel;
    onClose: () => void;
}

export function ChannelDetailPanel({ channel, onClose }: ChannelDetailPanelProps) {
    const [activeTab, setActiveTab] = useState<PanelTab>('health');

    return (
        <>
            {/* Backdrop */}
            <div
                className="fixed inset-0 bg-black/40 dark:bg-black/60 z-40"
                onClick={onClose}
                aria-hidden="true"
            />

            {/* Panel */}
            <div
                role="dialog"
                aria-modal="true"
                aria-label={`${channel.name} details`}
                onKeyDown={e => e.key === 'Escape' && onClose()}
                className="fixed right-0 top-0 h-full w-full max-w-md bg-white dark:bg-[#161b27] border-l border-gray-200 dark:border-[#1e2535] shadow-2xl z-50 flex flex-col"
            >
                {/* Header */}
                <div className="flex items-center justify-between px-5 py-4 border-b border-gray-200 dark:border-[#1e2535]">
                    <div>
                        <h2 className="text-base font-semibold text-gray-900 dark:text-white">
                            {channel.name}
                        </h2>
                        <p className="text-xs text-gray-500 dark:text-gray-400 capitalize mt-0.5">
                            {channel.type} · {channel.status}
                        </p>
                    </div>
                    <button
                        onClick={onClose}
                        aria-label="Close panel"
                        className="p-2 hover:bg-gray-100 dark:hover:bg-[#1e2535] rounded-lg transition-colors"
                    >
                        <X className="w-4 h-4 text-gray-500 dark:text-gray-400" />
                    </button>
                </div>

                {/* Tabs */}
                <div className="flex items-center gap-1 px-4 pt-3 pb-2 border-b border-gray-100 dark:border-[#1e2535]">
                    <TabButton
                        label="Health"
                        icon={Activity}
                        active={activeTab === 'health'}
                        onClick={() => setActiveTab('health')}
                    />
                    <TabButton
                        label="Logs"
                        icon={MessageSquare}
                        active={activeTab === 'logs'}
                        onClick={() => setActiveTab('logs')}
                    />
                    <TabButton
                        label="Settings"
                        icon={Settings}
                        active={activeTab === 'settings'}
                        onClick={() => setActiveTab('settings')}
                    />
                </div>

                {/* Tab body */}
                <div className="flex-1 overflow-y-auto px-5 py-4">
                    {activeTab === 'health'   && <HealthTab   channel={channel} />}
                    {activeTab === 'logs'     && <LogsTab     channel={channel} />}
                    {activeTab === 'settings' && <SettingsTab channel={channel} />}
                </div>
            </div>
        </>
    );
}
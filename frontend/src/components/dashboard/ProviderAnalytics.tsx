/**
 * @description Dashboard widget showing per-provider analytics with charts
 * for request success rate, latency, cost, and token distribution.
 * @example
 * ```tsx
 * import { ProviderAnalytics } from '@/components/dashboard/ProviderAnalytics';
 *
 * <ProviderAnalytics />
 * ```
 */
import { useEffect, useRef, useState, useCallback, useMemo } from 'react';
import { api } from '@/services/api';
import { useWebSocketStore } from '@/store/websocketStore';
import {
    LineChart, Line, BarChart, Bar, XAxis, YAxis, CartesianGrid,
    Tooltip, ResponsiveContainer, Cell, PieChart, Pie,
} from 'recharts';
import {
    BarChart3, DollarSign, Zap, CheckCircle2,
    RefreshCw, ChevronDown, AlertCircle, Clock,
    ArrowUpRight, ArrowDownRight, Minus,
} from 'lucide-react';
import { LoadingSpinner } from '@/components/ui/LoadingSpinner';
import { WidgetCard } from './WidgetCard';
import { EmptyState } from '@/components/ui/EmptyState';
import { WidgetErrorFallback } from '@/components/ui/WidgetErrorFallback';

// ─── Types ────────────────────────────────────────────────────────────────────

interface ProviderStat {
    provider: string;
    total_requests: number;
    successful_requests: number;
    failed_requests: number;
    success_rate_pct: number;
    avg_latency_ms: number;
    total_cost_usd: number;
    total_tokens: number;
    avg_cost_per_request: number;
}

interface TimelineEntry {
    date: string;
    [provider: string]: number | string;
}

interface ModelRow {
    provider: string;
    model: string;
    total_requests: number;
    successful_requests: number;
    success_rate_pct: number;
    avg_latency_ms: number;
    total_cost_usd: number;
    total_tokens: number;
    cost_per_1k_tokens: number;
}

// ─── Palette ──────────────────────────────────────────────────────────────────
// Cohesive provider palette used across every chart for visual consistency.

const PROVIDER_COLORS: Record<string, string> = {
    OPENAI:     '#10b981',
    ANTHROPIC:  '#6366f1',
    GEMINI:     '#f59e0b',
    GROQ:       '#14b8a6',
    MISTRAL:    '#8b5cf6',
    COHERE:     '#ec4899',
    DEEPSEEK:   '#3b82f6',
    MOONSHOT:   '#f97316',
    LOCAL:      '#64748b',
    CUSTOM:     '#a78bfa',
};
const getColor = (p: string) => PROVIDER_COLORS[p?.toUpperCase()] ?? '#64748b';

// Per-series line styles so providers are distinguishable without relying on
// colour alone (helps colour-blind users). Cycles through solid/dashed/dotted.
const LINE_DASHES = ['', '6 4', '2 4', '8 4', '4 4', '3 3', '10 4', '5 2'];

// ─── Formatters ───────────────────────────────────────────────────────────────

const fmtInt = (n: number) => n.toLocaleString();

const fmtCurrency = (n: number) =>
    n >= 100
        ? `$${n.toLocaleString(undefined, { maximumFractionDigits: 2 })}`
        : `$${n.toFixed(n >= 1 ? 2 : 4)}`;

const fmtCompactCurrency = (n: number) => {
    if (n >= 100) return `$${(n).toFixed(0)}`;
    if (n >= 1)   return `$${n.toFixed(1)}`;
    if (n >= 0.01) return `$${n.toFixed(3)}`;
    return `$${n.toFixed(5)}`;
};

const fmtPct = (n: number) => `${n.toFixed(1)}%`;

// ─── Sub-components ───────────────────────────────────────────────────────────

const ChartTooltip = ({ active, payload, label, prefix = '', suffix = '' }: any) => {
    if (!active || !payload?.length) return null;
    return (
        <div className="rounded-lg border border-gray-200 dark:border-[#2a3347] bg-white dark:bg-[#1f2433] px-3 py-2 shadow-xl">
            <p className="text-[11px] font-medium text-gray-500 dark:text-gray-400 mb-1.5">{label}</p>
            {payload.map((p: any) => (
                <div key={p.dataKey} className="flex items-center gap-2 mb-0.5 last:mb-0">
                    <span className="w-2 h-2 rounded-full flex-shrink-0" style={{ background: p.color ?? p.fill }} />
                    <span className="text-xs font-semibold text-gray-900 dark:text-gray-100">
                        {p.name}: {prefix}{typeof p.value === 'number' ? p.value.toFixed(p.value < 1 ? 5 : p.value < 100 ? 2 : 0) : p.value}{suffix}
                    </span>
                </div>
            ))}
        </div>
    );
};

const ChartCard = ({ title, caption, children, className = '' }: {
    title: string;
    caption?: string;
    children: React.ReactNode;
    className?: string;
}) => (
    <div className={`rounded-xl border border-gray-100 dark:border-[#1e2535] bg-gray-50/60 dark:bg-[#0f1117] p-4 ${className}`}>
        <div className="mb-3">
            <h3 className="text-[13px] font-semibold text-gray-900 dark:text-white leading-none">{title}</h3>
            {caption && <p className="text-[11px] text-gray-600 dark:text-gray-500 mt-1">{caption}</p>}
        </div>
        {children}
    </div>
);

function KpiCard({ icon: Icon, label, value, sub, color, trend }: {
    icon: any;
    label: string;
    value: string;
    sub?: string;
    color: string;
    trend?: 'up' | 'down' | 'flat';
}) {
    const TrendIcon = trend === 'up' ? ArrowUpRight : trend === 'down' ? ArrowDownRight : Minus;
    const trendColor = trend === 'up' ? 'text-emerald-500' : trend === 'down' ? 'text-rose-500' : 'text-gray-400';
    return (
        <div className="relative overflow-hidden rounded-xl border border-gray-100 dark:border-[#1e2535] bg-white dark:bg-[#0f1117] p-3.5 group hover:border-gray-200 dark:hover:border-[#2a3347] transition-colors">
            <span className="absolute left-0 top-0 h-full w-1" style={{ background: color }} aria-hidden />
            <div className="flex items-center justify-between mb-2">
                <div className="w-7 h-7 rounded-lg flex items-center justify-center" style={{ background: `${color}1a` }}>
                    <Icon className="w-3.5 h-3.5" style={{ color }} />
                </div>
                {trend && <TrendIcon className={`w-3.5 h-3.5 ${trendColor}`} aria-hidden />}
            </div>
            <p className="text-[11px] font-medium text-gray-600 dark:text-gray-500 leading-none mb-1">{label}</p>
            <p className="text-xl font-bold text-gray-900 dark:text-white tracking-tight leading-none">{value}</p>
            {sub && <p className="text-[10px] text-gray-600 dark:text-gray-500 mt-1.5">{sub}</p>}
        </div>
    );
}

// Clickable legend for the cost-over-time line chart (progressive disclosure).
function LineLegend({ providers, hidden, onToggle }: {
    providers: string[];
    hidden: Set<string>;
    onToggle: (p: string) => void;
}) {
    return (
        <div className="flex flex-wrap gap-x-3 gap-y-1.5 mt-2">
            {providers.map(p => {
                const off = hidden.has(p);
                return (
                    <button
                        key={p}
                        type="button"
                        onClick={() => onToggle(p)}
                        aria-pressed={!off}
                        className={`flex items-center gap-1.5 text-[11px] font-medium transition-opacity ${off ? 'opacity-40' : 'opacity-100'}`}
                        title={off ? `Show ${p}` : `Hide ${p}`}
                    >
                        <span className="w-2.5 h-2.5 rounded-sm" style={{ background: getColor(p) }} aria-hidden />
                        <span className="text-gray-700 dark:text-gray-300">{p}</span>
                    </button>
                );
            })}
        </div>
    );
}

// ─── Main Component ───────────────────────────────────────────────────────────

export function ProviderAnalytics() {
    const [summary, setSummary]                     = useState<ProviderStat[]>([]);
    const [timeline, setTimeline]                   = useState<TimelineEntry[]>([]);
    const [timelineProviders, setTimelineProviders] = useState<string[]>([]);
    const [models, setModels]                       = useState<ModelRow[]>([]);
    const [loading, setLoading]                     = useState(true);
    const [error, setError]                         = useState<string | null>(null);
    const [expanded, setExpanded]                   = useState(true);
    const [days, setDays]                           = useState(30);
    const [hiddenSeries, setHiddenSeries]           = useState<Set<string>>(new Set());

    const refresh = useCallback(async () => {
        setLoading(true);
        setError(null);
        try {
            const [summaryRes, timelineRes, modelsRes] = await Promise.all([
                api.get(`/api/v1/provider-analytics/summary?days=${days}`),
                api.get(`/api/v1/provider-analytics/cost-over-time?days=${Math.min(days, 14)}`),
                api.get(`/api/v1/provider-analytics/model-breakdown?days=${days}`),
            ]);

            setSummary(summaryRes.data.providers ?? []);

            const tl: TimelineEntry[] = (timelineRes.data.timeline ?? []).map((e: TimelineEntry) => ({
                ...e,
                date: String(e.date).slice(5), // MM-DD
            }));
            setTimeline(tl);
            setTimelineProviders(timelineRes.data.providers ?? []);
            setModels(modelsRes.data.models ?? []);
        } catch (e: any) {
            setError(e?.response?.data?.detail ?? 'Failed to load analytics');
        } finally {
            setLoading(false);
        }
    }, [days]);

    useEffect(() => { refresh(); }, [refresh]);

    // Auto-refresh when a provider becomes available (e.g. after an API key is
    // added on the Models page) so the widget updates without a manual refresh.
    const apiKeyAddedAt = useWebSocketStore((s) => s.apiKeyAddedAt);
    const didMountRef = useRef(false);
    useEffect(() => {
        if (!didMountRef.current) {
            didMountRef.current = true;
            return;
        }
        refresh();
    }, [apiKeyAddedAt, refresh]);

    const toggleSeries = useCallback((p: string) => {
        setHiddenSeries(prev => {
            const next = new Set(prev);
            next.has(p) ? next.delete(p) : next.add(p);
            return next;
        });
    }, []);

    // ── Derived ──────────────────────────────────────────────────────────────

    const totalCost   = summary.reduce((s, p) => s + p.total_cost_usd, 0);
    const totalReqs   = summary.reduce((s, p) => s + p.total_requests, 0);
    const totalFailed = summary.reduce((s, p) => s + p.failed_requests, 0);
    const avgLatency  = summary.length ? summary.reduce((s, p) => s + p.avg_latency_ms, 0) / summary.length : 0;
    const avgSuccess  = summary.length ? summary.reduce((s, p) => s + p.success_rate_pct, 0) / summary.length : 0;
    const topProvider = useMemo(
        () => [...summary].sort((a, b) => b.total_cost_usd - a.total_cost_usd)[0]?.provider,
        [summary],
    );

    const pieData = summary.filter(p => p.total_cost_usd > 0).map(p => ({
        name: p.provider,
        value: parseFloat(p.total_cost_usd.toFixed(6)),
        fill: getColor(p.provider),
    }));

    const visibleTimelineProviders = timelineProviders.filter(p => !hiddenSeries.has(p));

    const successTone = (pct: number) =>
        pct >= 90 ? 'text-emerald-600 dark:text-emerald-400'
        : pct >= 70 ? 'text-amber-600 dark:text-amber-400'
        : 'text-rose-600 dark:text-rose-400';

    return (
        <WidgetCard
            title="Provider Analytics"
            icon={BarChart3}
            aria-label="Provider analytics"
            action={
                <div className="flex items-center gap-2">
                    <select
                        value={days}
                        onChange={(e) => setDays(Number(e.target.value))}
                        className="rounded-lg border border-hairline bg-panel px-2 py-1 text-sm text-gray-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-brand dark:text-gray-200"
                        aria-label="Select time range"
                    >
                        <option value={7}>7 days</option>
                        <option value={14}>14 days</option>
                        <option value={30}>30 days</option>
                        <option value={90}>90 days</option>
                    </select>
                    <button onClick={refresh} disabled={loading} aria-label="Refresh analytics" className="rounded-lg p-1.5 text-gray-500 transition-colors duration-200 hover:bg-subtle hover:text-brand disabled:opacity-50 dark:text-gray-400">
                        {loading ? <LoadingSpinner size="sm" /> : <RefreshCw className="h-4 w-4" aria-hidden="true" />}
                    </button>
                    <button onClick={() => setExpanded((v) => !v)} aria-label={expanded ? 'Collapse analytics' : 'Expand analytics'} aria-expanded={expanded} className="rounded-lg p-1.5 text-gray-500 transition-colors duration-200 hover:bg-subtle hover:text-brand dark:text-gray-400">
                        <ChevronDown className={`h-4 w-4 transition-transform duration-200 ${expanded ? '' : '-rotate-90'}`} aria-hidden="true" />
                    </button>
                </div>
            }
        >
            {!expanded ? null : (
                <div className="space-y-6 p-5">

                    {/* Error */}
                    {error && (
                        <WidgetErrorFallback widgetName="Provider analytics" onRetry={refresh} />
                    )}

                    {/* Loading */}
                    {loading && !error && (
                        <div className="py-8 flex items-center justify-center gap-2">
                            <LoadingSpinner size="md" />
                            <span className="text-sm text-gray-600 dark:text-gray-400">Loading analytics…</span>
                        </div>
                    )}

                    {/* Empty */}
                    {!loading && !error && summary.length === 0 && (
                        <EmptyState
                            icon={BarChart3}
                            title="No usage data"
                            description="Usage will appear once providers are active."
                            size="sm"
                        />
                    )}

                    {/* Content */}
                    {!loading && !error && summary.length > 0 && (
                        <div className="space-y-5">

                            {/* KPIs */}
                            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3">
                                <KpiCard icon={DollarSign}   label="Total Spend"      value={fmtCurrency(totalCost)}     color="#10b981" sub={topProvider ? `Top: ${topProvider}` : undefined} />
                                <KpiCard icon={Zap}          label="Total Requests"   value={fmtInt(totalReqs)}          color="#6366f1" />
                                <KpiCard icon={CheckCircle2} label="Avg Success Rate" value={fmtPct(avgSuccess)}         color="#f59e0b" />
                                <KpiCard icon={Clock}        label="Avg Latency"      value={`${avgLatency.toFixed(0)}ms`} color="#14b8a6" />
                                <KpiCard icon={AlertCircle}  label="Failed Requests"  value={fmtInt(totalFailed)}        color="#ef4444" sub={totalReqs ? `${((totalFailed / totalReqs) * 100).toFixed(2)}% of total` : undefined} />
                            </div>

                            {/* Cost over time + Pie */}
                            <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
                                <ChartCard
                                    title="Cost Over Time"
                                    caption="Daily spend in USD — click a provider to toggle"
                                    className="lg:col-span-2"
                                >
                                    {timeline.length === 0 ? (
                                        <EmptyState icon={BarChart3} title="No usage data" description="Usage will appear once providers are active." size="sm" />
                                    ) : (
                                        <>
                                            <ResponsiveContainer width="100%" height={200}>
                                                <LineChart data={timeline} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
                                                    <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" className="dark:[stroke:#1e2535]" vertical={false} />
                                                    <XAxis dataKey="date" tick={{ fill: '#9ca3af', fontSize: 10 }} axisLine={false} tickLine={false} minTickGap={16} />
                                                    <YAxis tick={{ fill: '#9ca3af', fontSize: 10 }} axisLine={false} tickLine={false} width={52} tickFormatter={fmtCompactCurrency} />
                                                    <Tooltip content={<ChartTooltip prefix="$" />} />
                                                    {visibleTimelineProviders.map((p, i) => (
                                                        <Line
                                                            key={p}
                                                            type="monotone"
                                                            dataKey={p}
                                                            name={p}
                                                            stroke={getColor(p)}
                                                            strokeWidth={2}
                                                            strokeDasharray={LINE_DASHES[i % LINE_DASHES.length]}
                                                            dot={false}
                                                            activeDot={{ r: 4 }}
                                                            isAnimationActive={false}
                                                        />
                                                    ))}
                                                </LineChart>
                                            </ResponsiveContainer>
                                            <LineLegend providers={timelineProviders} hidden={hiddenSeries} onToggle={toggleSeries} />
                                        </>
                                    )}
                                </ChartCard>

                                <ChartCard title="Cost Distribution" caption="Share of total spend by provider">
                                    {pieData.length === 0 ? (
                                        <EmptyState icon={BarChart3} title="No usage data" description="Usage will appear once providers are active." size="sm" />
                                    ) : (
                                        <div className="relative">
                                            <ResponsiveContainer width="100%" height={200}>
                                                <PieChart>
                                                    <Pie
                                                        data={pieData}
                                                        cx="50%" cy="50%"
                                                        innerRadius={52}
                                                        outerRadius={78}
                                                        paddingAngle={3}
                                                        dataKey="value"
                                                        stroke="none"
                                                        isAnimationActive={false}
                                                    >
                                                        {pieData.map((entry, i) => (
                                                            <Cell key={i} fill={entry.fill} opacity={0.92} />
                                                        ))}
                                                    </Pie>
                                                    <Tooltip content={<ChartTooltip prefix="$" />} />
                                                </PieChart>
                                            </ResponsiveContainer>
                                            <div className="absolute inset-0 flex flex-col items-center justify-center pointer-events-none">
                                                <span className="text-[10px] font-medium text-gray-600 dark:text-gray-500 uppercase tracking-wide">Total</span>
                                                <span className="text-base font-bold text-gray-900 dark:text-white">{fmtCurrency(totalCost)}</span>
                                            </div>
                                        </div>
                                    )}
                                    {pieData.length > 0 && (
                                        <div className="mt-2 space-y-1 max-h-24 overflow-y-auto">
                                            {pieData.slice().sort((a, b) => b.value - a.value).map(d => (
                                                <div key={d.name} className="flex items-center justify-between text-[11px]">
                                                    <span className="flex items-center gap-1.5 text-gray-700 dark:text-gray-300">
                                                        <span className="w-2 h-2 rounded-full" style={{ background: d.fill }} aria-hidden />
                                                        {d.name}
                                                    </span>
                                                    <span className="font-medium text-gray-600 dark:text-gray-400">
                                                        {totalCost ? `${((d.value / totalCost) * 100).toFixed(1)}%` : '0%'}
                                                    </span>
                                                </div>
                                            ))}
                                        </div>
                                    )}
                                </ChartCard>
                            </div>

                            {/* Success rate + Latency */}
                            <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
                                <ChartCard title="Success Rate by Provider" caption="Percentage of successful requests">
                                    {summary.length === 0 ? (
                                        <EmptyState icon={BarChart3} title="No usage data" description="Usage will appear once providers are active." size="sm" />
                                    ) : (
                                        <ResponsiveContainer width="100%" height={190}>
                                            <BarChart data={summary} barSize={26} margin={{ top: 8, right: 4, bottom: 0, left: 0 }}>
                                                <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" className="dark:[stroke:#1e2535]" vertical={false} />
                                                <XAxis dataKey="provider" tick={{ fill: '#9ca3af', fontSize: 10 }} axisLine={false} tickLine={false} interval={0} angle={summary.length > 5 ? -35 : 0} textAnchor={summary.length > 5 ? 'end' : 'middle'} height={summary.length > 5 ? 48 : 24} />
                                                <YAxis domain={[0, 100]} tick={{ fill: '#9ca3af', fontSize: 10 }} axisLine={false} tickLine={false} width={28} tickFormatter={v => `${v}%`} />
                                                <Tooltip cursor={{ fill: 'rgba(148,163,184,0.08)' }} content={<ChartTooltip suffix="%" />} />
                                                <Bar dataKey="success_rate_pct" name="Success Rate" radius={[4, 4, 0, 0]}>
                                                    {summary.map((entry, i) => <Cell key={i} fill={getColor(entry.provider)} />)}
                                                </Bar>
                                            </BarChart>
                                        </ResponsiveContainer>
                                    )}
                                </ChartCard>

                                <ChartCard title="Avg Latency by Provider" caption="Mean response time in milliseconds">
                                    {summary.every(p => p.avg_latency_ms === 0) ? (
                                        <EmptyState icon={BarChart3} title="No usage data" description="Usage will appear once providers are active." size="sm" />
                                    ) : (
                                        <ResponsiveContainer width="100%" height={190}>
                                            <BarChart data={summary} barSize={26} margin={{ top: 8, right: 4, bottom: 0, left: 0 }}>
                                                <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" className="dark:[stroke:#1e2535]" vertical={false} />
                                                <XAxis dataKey="provider" tick={{ fill: '#9ca3af', fontSize: 10 }} axisLine={false} tickLine={false} interval={0} angle={summary.length > 5 ? -35 : 0} textAnchor={summary.length > 5 ? 'end' : 'middle'} height={summary.length > 5 ? 48 : 24} />
                                                <YAxis tick={{ fill: '#9ca3af', fontSize: 10 }} axisLine={false} tickLine={false} width={40} tickFormatter={v => `${v}ms`} />
                                                <Tooltip cursor={{ fill: 'rgba(148,163,184,0.08)' }} content={<ChartTooltip suffix="ms" />} />
                                                <Bar dataKey="avg_latency_ms" name="Avg Latency" radius={[4, 4, 0, 0]}>
                                                    {summary.map((entry, i) => <Cell key={i} fill={getColor(entry.provider)} />)}
                                                </Bar>
                                            </BarChart>
                                        </ResponsiveContainer>
                                    )}
                                </ChartCard>
                            </div>

                            {/* Model breakdown table */}
                            <ChartCard title="Model-Level Breakdown" caption="Per-model usage, cost and performance">
                                <div className="overflow-x-auto -mx-1">
                                    <table className="w-full text-xs">
                                        <thead>
                                            <tr className="text-gray-600 dark:text-gray-500 border-b border-gray-100 dark:border-[#1e2535]">
                                                <th className="text-left px-3 py-2.5 font-semibold">Provider</th>
                                                <th className="text-left px-3 py-2.5 font-semibold">Model</th>
                                                <th className="text-right px-3 py-2.5 font-semibold">Requests</th>
                                                <th className="text-right px-3 py-2.5 font-semibold">Success</th>
                                                <th className="text-right px-3 py-2.5 font-semibold">Avg Latency</th>
                                                <th className="text-right px-3 py-2.5 font-semibold">Total Cost</th>
                                                <th className="text-right px-3 py-2.5 font-semibold">Cost / 1K</th>
                                            </tr>
                                        </thead>
                                        <tbody className="divide-y divide-gray-100 dark:divide-[#1e2535]">
                                            {models.map((row, i) => (
                                                <tr key={i} className="hover:bg-gray-100/60 dark:hover:bg-white/5 transition-colors">
                                                    <td className="px-3 py-2.5">
                                                        <div className="flex items-center gap-2">
                                                            <span className="w-2 h-2 rounded-full flex-shrink-0" style={{ background: getColor(row.provider) }} aria-hidden />
                                                            <span className="text-gray-700 dark:text-gray-300">{row.provider}</span>
                                                        </div>
                                                    </td>
                                                    <td className="px-3 py-2.5 font-medium text-gray-900 dark:text-gray-100">{row.model}</td>
                                                    <td className="px-3 py-2.5 text-right text-gray-700 dark:text-gray-300 tabular-nums">{fmtInt(row.total_requests)}</td>
                                                    <td className="px-3 py-2.5 text-right">
                                                        <span className={`font-semibold tabular-nums ${successTone(row.success_rate_pct)}`}>
                                                            {row.success_rate_pct.toFixed(1)}%
                                                        </span>
                                                    </td>
                                                    <td className="px-3 py-2.5 text-right text-gray-700 dark:text-gray-300 tabular-nums">
                                                        {row.avg_latency_ms > 0 ? `${row.avg_latency_ms.toFixed(0)}ms` : '—'}
                                                    </td>
                                                    <td className="px-3 py-2.5 text-right font-semibold text-gray-900 dark:text-gray-100 tabular-nums">
                                                        {fmtCurrency(row.total_cost_usd)}
                                                    </td>
                                                    <td className="px-3 py-2.5 text-right text-gray-700 dark:text-gray-300 tabular-nums">
                                                        {row.cost_per_1k_tokens > 0 ? `$${row.cost_per_1k_tokens.toFixed(4)}` : '—'}
                                                    </td>
                                                </tr>
                                            ))}
                                        </tbody>
                                    </table>
                                </div>
                            </ChartCard>

                        </div>
                    )}
                </div>
            )}
        </WidgetCard>
    );
}

// src/components/dashboard/ProviderAnalytics.tsx
import { useEffect, useState, useCallback } from 'react';
import { api } from '@/services/api';
import {
    LineChart, Line, BarChart, Bar, XAxis, YAxis, CartesianGrid,
    Tooltip, ResponsiveContainer, Cell, PieChart, Pie, Legend,
} from 'recharts';
import {
    TrendingUp, DollarSign, Zap, CheckCircle2,
    RefreshCw, ChevronDown, ChevronUp, AlertCircle, Clock,
} from 'lucide-react';
import { LoadingSpinner } from '@/components/ui/LoadingSpinner';

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

// ─── Sub-components ───────────────────────────────────────────────────────────

const ChartTooltip = ({ active, payload, label, prefix = '', suffix = '' }: any) => {
    if (!active || !payload?.length) return null;
    return (
        <div className="bg-[#1a2035] border border-[#2a3347] rounded-lg px-3 py-2 text-xs shadow-xl">
            <p className="text-gray-400 mb-1">{label}</p>
            {payload.map((p: any) => (
                <p key={p.dataKey} style={{ color: p.color ?? p.fill }} className="font-semibold">
                    {p.name}: {prefix}{typeof p.value === 'number' ? p.value.toFixed(p.value < 1 ? 6 : 1) : p.value}{suffix}
                </p>
            ))}
        </div>
    );
};

function KpiPill({ icon: Icon, label, value, color }: { icon: any; label: string; value: string; color: string }) {
    return (
        <div className="flex items-center gap-2.5 bg-gray-50 dark:bg-[#0f1117] border border-gray-200 dark:border-[#1e2535] rounded-lg px-3 py-2.5">
            <div className="w-7 h-7 rounded-md flex items-center justify-center flex-shrink-0" style={{ background: `${color}20` }}>
                <Icon className="w-3.5 h-3.5" style={{ color }} />
            </div>
            <div>
                <p className="text-[10px] text-gray-500 leading-none mb-0.5">{label}</p>
                <p className="text-sm font-bold text-gray-900 dark:text-white leading-none">{value}</p>
            </div>
        </div>
    );
}

function SectionLabel({ children }: { children: React.ReactNode }) {
    return <p className="text-[11px] font-semibold text-gray-400 uppercase tracking-wider mb-3">{children}</p>;
}

function EmptyChart({ message = 'No data yet' }: { message?: string }) {
    return <div className="h-40 flex items-center justify-center text-xs text-gray-400">{message}</div>;
}

// ─── Main Component ───────────────────────────────────────────────────────────

export function ProviderAnalytics() {
    const [summary, setSummary]                   = useState<ProviderStat[]>([]);
    const [timeline, setTimeline]                 = useState<TimelineEntry[]>([]);
    const [timelineProviders, setTimelineProviders] = useState<string[]>([]);
    const [models, setModels]                     = useState<ModelRow[]>([]);
    const [loading, setLoading]                   = useState(true);
    const [error, setError]                       = useState<string | null>(null);
    const [expanded, setExpanded]                 = useState(true);
    const [days, setDays]                         = useState(30);
    const [lastUpdated, setLastUpdated]           = useState<Date | null>(null);

    const fetchAll = useCallback(async () => {
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
            setLastUpdated(new Date());
        } catch (e: any) {
            setError(e?.response?.data?.detail ?? 'Failed to load analytics');
        } finally {
            setLoading(false);
        }
    }, [days]);

    useEffect(() => { fetchAll(); }, [fetchAll]);

    // ── Derived ──────────────────────────────────────────────────────────────

    const totalCost   = summary.reduce((s, p) => s + p.total_cost_usd, 0);
    const totalReqs   = summary.reduce((s, p) => s + p.total_requests, 0);
    const totalFailed = summary.reduce((s, p) => s + p.failed_requests, 0);
    const avgLatency  = summary.length ? summary.reduce((s, p) => s + p.avg_latency_ms, 0) / summary.length : 0;
    const avgSuccess  = summary.length ? summary.reduce((s, p) => s + p.success_rate_pct, 0) / summary.length : 0;

    const pieData = summary.filter(p => p.total_cost_usd > 0).map(p => ({
        name: p.provider,
        value: parseFloat(p.total_cost_usd.toFixed(6)),
    }));

    return (
        <div className="bg-white dark:bg-[#161b27] rounded-xl border border-gray-200 dark:border-[#1e2535] shadow-sm dark:shadow-[0_2px_16px_rgba(0,0,0,0.25)] transition-colors duration-200 overflow-hidden">

            {/* Header */}
            <div className="flex items-center justify-between px-6 py-4 border-b border-gray-100 dark:border-[#1e2535]">
                <div className="flex items-center gap-3">
                    <div className="w-8 h-8 rounded-lg bg-indigo-100 dark:bg-indigo-500/10 flex items-center justify-center">
                        <TrendingUp className="w-4 h-4 text-indigo-600 dark:text-indigo-400" />
                    </div>
                    <div>
                        <h2 className="text-base font-semibold text-gray-900 dark:text-white leading-none">Provider Analytics</h2>
                        {lastUpdated && <p className="text-[10px] text-gray-400 mt-0.5">Updated {lastUpdated.toLocaleTimeString()}</p>}
                    </div>
                </div>

                <div className="flex items-center gap-2">
                    <select
                        value={days}
                        onChange={e => setDays(Number(e.target.value))}
                        className="text-xs bg-gray-100 dark:bg-[#0f1117] border border-gray-200 dark:border-[#2a3347] text-gray-700 dark:text-gray-300 rounded-lg px-2.5 py-1.5 focus:outline-none"
                    >
                        <option value={7}>Last 7 days</option>
                        <option value={14}>Last 14 days</option>
                        <option value={30}>Last 30 days</option>
                        <option value={90}>Last 90 days</option>
                    </select>

                    <button onClick={fetchAll} disabled={loading} className="p-1.5 rounded-lg text-gray-400 hover:text-gray-600 dark:hover:text-gray-200 hover:bg-gray-100 dark:hover:bg-[#1e2535] transition-colors" title="Refresh">
                        {loading ? <LoadingSpinner size="sm" /> : <RefreshCw className="w-3.5 h-3.5" />}
                    </button>
                    <button onClick={() => setExpanded(v => !v)} className="p-1.5 rounded-lg text-gray-400 hover:text-gray-600 dark:hover:text-gray-200 hover:bg-gray-100 dark:hover:bg-[#1e2535] transition-colors">
                        {expanded ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
                    </button>
                </div>
            </div>

            {/* Error */}
            {error && (
                <div className="mx-6 mt-4 p-3 bg-red-50 dark:bg-red-500/10 border border-red-200 dark:border-red-500/20 rounded-lg flex items-center gap-2">
                    <AlertCircle className="w-4 h-4 text-red-500 flex-shrink-0" />
                    <p className="text-xs text-red-600 dark:text-red-400">{error}</p>
                </div>
            )}

            {/* Loading */}
            {loading && (
                <div className="px-6 py-10 flex items-center justify-center gap-2">
                    <LoadingSpinner size="md" />
                    <span className="text-sm text-gray-400">Loading analytics…</span>
                </div>
            )}

            {/* Empty */}
            {!loading && !error && summary.length === 0 && (
                <div className="px-6 py-10 text-center">
                    <p className="text-sm text-gray-500 dark:text-gray-400">No usage data for this period.</p>
                    <p className="text-xs text-gray-400 mt-1">Data appears once agents start making API calls.</p>
                </div>
            )}

            {/* Content */}
            {!loading && !error && summary.length > 0 && expanded && (
                <div className="px-6 py-5 space-y-8">

                    {/* KPIs */}
                    <div className="flex flex-wrap gap-3">
                        <KpiPill icon={DollarSign}   label="Total Spend"      value={`$${totalCost.toFixed(4)}`}     color="#10b981" />
                        <KpiPill icon={Zap}          label="Total Requests"   value={totalReqs.toLocaleString()}      color="#6366f1" />
                        <KpiPill icon={CheckCircle2} label="Avg Success Rate" value={`${avgSuccess.toFixed(1)}%`}     color="#f59e0b" />
                        <KpiPill icon={Clock}        label="Avg Latency"      value={`${avgLatency.toFixed(0)}ms`}    color="#14b8a6" />
                        <KpiPill icon={AlertCircle}  label="Failed Requests"  value={totalFailed.toLocaleString()}    color="#ef4444" />
                    </div>

                    {/* Cost over time + Pie */}
                    <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                        <div className="lg:col-span-2">
                            <SectionLabel>Cost Over Time (USD)</SectionLabel>
                            {timeline.length === 0 ? <EmptyChart /> : (
                                <ResponsiveContainer width="100%" height={180}>
                                    <LineChart data={timeline} margin={{ top: 4, right: 8, bottom: 0, left: 0 }}>
                                        <CartesianGrid strokeDasharray="3 3" stroke="#1e2535" vertical={false} />
                                        <XAxis dataKey="date" tick={{ fill: '#6b7280', fontSize: 10 }} axisLine={false} tickLine={false} />
                                        <YAxis tick={{ fill: '#6b7280', fontSize: 10 }} axisLine={false} tickLine={false} width={58} tickFormatter={v => `$${Number(v).toFixed(4)}`} />
                                        <Tooltip content={<ChartTooltip prefix="$" />} />
                                        {timelineProviders.map(p => (
                                            <Line key={p} type="monotone" dataKey={p} name={p} stroke={getColor(p)} strokeWidth={2} dot={false} activeDot={{ r: 4 }} />
                                        ))}
                                    </LineChart>
                                </ResponsiveContainer>
                            )}
                        </div>

                        <div>
                            <SectionLabel>Cost Distribution</SectionLabel>
                            {pieData.length === 0 ? <EmptyChart message="No cost data" /> : (
                                <ResponsiveContainer width="100%" height={180}>
                                    <PieChart>
                                        <Pie data={pieData} cx="50%" cy="50%" innerRadius={44} outerRadius={70} paddingAngle={3} dataKey="value">
                                            {pieData.map((entry, i) => <Cell key={i} fill={getColor(entry.name)} opacity={0.9} />)}
                                        </Pie>
                                        <Tooltip formatter={(v: any) => `$${Number(v).toFixed(6)}`} />
                                        <Legend iconType="circle" iconSize={7} formatter={v => <span style={{ color: '#9ca3af', fontSize: 10 }}>{v}</span>} />
                                    </PieChart>
                                </ResponsiveContainer>
                            )}
                        </div>
                    </div>

                    {/* Success rate + Latency */}
                    <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                        <div>
                            <SectionLabel>Success Rate per Provider (%)</SectionLabel>
                            {summary.length === 0 ? <EmptyChart /> : (
                                <ResponsiveContainer width="100%" height={160}>
                                    <BarChart data={summary} barSize={28} margin={{ top: 4, right: 4, bottom: 0, left: 0 }}>
                                        <CartesianGrid strokeDasharray="3 3" stroke="#1e2535" vertical={false} />
                                        <XAxis dataKey="provider" tick={{ fill: '#6b7280', fontSize: 10 }} axisLine={false} tickLine={false} />
                                        <YAxis domain={[0, 100]} tick={{ fill: '#6b7280', fontSize: 10 }} axisLine={false} tickLine={false} width={28} />
                                        <Tooltip content={<ChartTooltip suffix="%" />} />
                                        <Bar dataKey="success_rate_pct" name="Success Rate" radius={[4, 4, 0, 0]}>
                                            {summary.map((entry, i) => <Cell key={i} fill={getColor(entry.provider)} />)}
                                        </Bar>
                                    </BarChart>
                                </ResponsiveContainer>
                            )}
                        </div>

                        <div>
                            <SectionLabel>Avg Latency per Provider (ms)</SectionLabel>
                            {summary.every(p => p.avg_latency_ms === 0) ? <EmptyChart message="No latency data yet" /> : (
                                <ResponsiveContainer width="100%" height={160}>
                                    <BarChart data={summary} barSize={28} margin={{ top: 4, right: 4, bottom: 0, left: 0 }}>
                                        <CartesianGrid strokeDasharray="3 3" stroke="#1e2535" vertical={false} />
                                        <XAxis dataKey="provider" tick={{ fill: '#6b7280', fontSize: 10 }} axisLine={false} tickLine={false} />
                                        <YAxis tick={{ fill: '#6b7280', fontSize: 10 }} axisLine={false} tickLine={false} width={40} />
                                        <Tooltip content={<ChartTooltip suffix="ms" />} />
                                        <Bar dataKey="avg_latency_ms" name="Avg Latency" radius={[4, 4, 0, 0]}>
                                            {summary.map((entry, i) => <Cell key={i} fill={getColor(entry.provider)} />)}
                                        </Bar>
                                    </BarChart>
                                </ResponsiveContainer>
                            )}
                        </div>
                    </div>

                    {/* Model breakdown table */}
                    <div>
                        <SectionLabel>Model-Level Breakdown</SectionLabel>
                        <div className="overflow-x-auto rounded-lg border border-gray-100 dark:border-[#1e2535]">
                            <table className="w-full text-xs">
                                <thead>
                                    <tr className="bg-gray-50 dark:bg-[#0f1117] text-gray-400">
                                        <th className="text-left px-4 py-2.5 font-semibold">Provider</th>
                                        <th className="text-left px-4 py-2.5 font-semibold">Model</th>
                                        <th className="text-right px-4 py-2.5 font-semibold">Requests</th>
                                        <th className="text-right px-4 py-2.5 font-semibold">Success</th>
                                        <th className="text-right px-4 py-2.5 font-semibold">Avg Latency</th>
                                        <th className="text-right px-4 py-2.5 font-semibold">Total Cost</th>
                                        <th className="text-right px-4 py-2.5 font-semibold">Cost / 1K tok</th>
                                    </tr>
                                </thead>
                                <tbody className="divide-y divide-gray-100 dark:divide-[#1e2535]">
                                    {models.map((row, i) => (
                                        <tr key={i} className="hover:bg-gray-50 dark:hover:bg-[#0f1117] transition-colors">
                                            <td className="px-4 py-2.5">
                                                <div className="flex items-center gap-2">
                                                    <span className="w-2 h-2 rounded-full flex-shrink-0" style={{ background: getColor(row.provider) }} />
                                                    <span className="text-gray-500 dark:text-gray-400">{row.provider}</span>
                                                </div>
                                            </td>
                                            <td className="px-4 py-2.5 font-medium text-gray-800 dark:text-gray-200">{row.model}</td>
                                            <td className="px-4 py-2.5 text-right text-gray-600 dark:text-gray-300">{row.total_requests.toLocaleString()}</td>
                                            <td className="px-4 py-2.5 text-right">
                                                <span className={`font-semibold ${row.success_rate_pct >= 90 ? 'text-green-500' : row.success_rate_pct >= 70 ? 'text-yellow-500' : 'text-red-500'}`}>
                                                    {row.success_rate_pct.toFixed(1)}%
                                                </span>
                                            </td>
                                            <td className="px-4 py-2.5 text-right text-gray-600 dark:text-gray-300">
                                                {row.avg_latency_ms > 0 ? `${row.avg_latency_ms.toFixed(0)}ms` : '—'}
                                            </td>
                                            <td className="px-4 py-2.5 text-right font-semibold text-gray-800 dark:text-gray-100">
                                                ${row.total_cost_usd.toFixed(5)}
                                            </td>
                                            <td className="px-4 py-2.5 text-right text-gray-600 dark:text-gray-300">
                                                {row.cost_per_1k_tokens > 0 ? `$${row.cost_per_1k_tokens.toFixed(5)}` : '—'}
                                            </td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </div>
                    </div>

                </div>
            )}
        </div>
    );
}
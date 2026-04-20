import React, { useEffect, useState, useCallback } from 'react';
import { lifecycleService, CapacityData, LifecycleStats, CapacityTier } from '../../services/agents';
import {
    BarChart2, Zap, TrendingUp, Trash2, RefreshCw, AlertTriangle,
    Shield, Users, Brain, Terminal, } from 'lucide-react';
import { LoadingSpinner } from '@/components/ui/LoadingSpinner';

interface LifecycleDashboardProps {
    /** Called when user clicks "Promote" CTA from the stats panel */
    onOpenBulkLiquidate?: () => void;
}

// ─── Tier config ──────────────────────────────────────────────────────────────

const TIERS = [
    { key: 'head',    label: 'Head',    icon: Shield,   color: 'violet' },
    { key: 'council', label: 'Council', icon: Users,    color: 'blue'   },
    { key: 'lead',    label: 'Lead',    icon: Brain,    color: 'emerald'},
    { key: 'task',    label: 'Task',    icon: Terminal, color: 'amber'  },
] as const;

const COLOR_MAP: Record<string, {
    bar:    string;
    bg:     string;
    border: string;
    text:   string;
    badge:  string;
}> = {
    violet:  { bar: 'bg-violet-500',  bg: 'bg-violet-50 dark:bg-violet-500/10',  border: 'border-violet-200 dark:border-violet-500/20',  text: 'text-violet-700 dark:text-violet-300',  badge: 'bg-violet-100 dark:bg-violet-500/20 text-violet-700 dark:text-violet-300' },
    blue:    { bar: 'bg-blue-500',    bg: 'bg-blue-50 dark:bg-blue-500/10',      border: 'border-blue-200 dark:border-blue-500/20',      text: 'text-blue-700 dark:text-blue-300',      badge: 'bg-blue-100 dark:bg-blue-500/20 text-blue-700 dark:text-blue-300'       },
    emerald: { bar: 'bg-emerald-500', bg: 'bg-emerald-50 dark:bg-emerald-500/10',border: 'border-emerald-200 dark:border-emerald-500/20',text: 'text-emerald-700 dark:text-emerald-300',badge: 'bg-emerald-100 dark:bg-emerald-500/20 text-emerald-700 dark:text-emerald-300' },
    amber:   { bar: 'bg-amber-500',   bg: 'bg-amber-50 dark:bg-amber-500/10',    border: 'border-amber-200 dark:border-amber-500/20',    text: 'text-amber-700 dark:text-amber-300',    badge: 'bg-amber-100 dark:bg-amber-500/20 text-amber-700 dark:text-amber-300'   },
};

// ─── Sub-components ───────────────────────────────────────────────────────────

function CapacityBar({ tier, color }: { tier: CapacityTier; color: string }) {
    const { bar } = COLOR_MAP[color];
    const barColor = tier.critical ? 'bg-red-500'
                   : tier.warning  ? 'bg-amber-500'
                   : bar;
    return (
        <div className="w-full h-1.5 rounded-full bg-slate-200 dark:bg-slate-700 overflow-hidden">
            <div
                className={`h-full rounded-full transition-all duration-500 ${barColor}`}
                style={{ width: `${Math.min(tier.percentage, 100)}%` }}
            />
        </div>
    );
}

function CapacityCard({
    label, icon: Icon, color, tier,
}: {
    label: string;
    icon:  React.ElementType;
    color: string;
    tier:  CapacityTier;
}) {
    const { bg, border, text } = COLOR_MAP[color];
    const statusColor = tier.critical ? 'text-red-600 dark:text-red-400'
                      : tier.warning  ? 'text-amber-600 dark:text-amber-400'
                      : 'text-slate-500 dark:text-slate-400';
    return (
        <div className={`rounded-xl border p-4 ${bg} ${border}`}>
            <div className="flex items-center justify-between mb-3">
                <div className="flex items-center gap-2">
                    <Icon className={`w-4 h-4 ${text}`} />
                    <span className={`text-sm font-semibold ${text}`}>{label}</span>
                </div>
                {(tier.warning || tier.critical) && (
                    <AlertTriangle className={`w-3.5 h-3.5 ${statusColor}`} />
                )}
            </div>
            <CapacityBar tier={tier} color={color} />
            <div className="flex justify-between mt-2">
                <span className={`text-xs ${statusColor}`}>{tier.percentage}% used</span>
                <span className="text-xs text-slate-400 dark:text-slate-500 font-mono">
                    {tier.used} / {tier.total}
                </span>
            </div>
        </div>
    );
}

function EventStat({
    label, value, icon: Icon, colorClass,
}: {
    label:      string;
    value:      number;
    icon:       React.ElementType;
    colorClass: string;
}) {
    return (
        <div className="flex items-center gap-3 p-3 rounded-xl border border-slate-200 dark:border-[#1e2535] bg-white dark:bg-[#0f1117]">
            <div className={`w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0 ${colorClass}`}>
                <Icon className="w-4 h-4" />
            </div>
            <div>
                <p className="text-lg font-bold text-slate-900 dark:text-white leading-none">{value}</p>
                <p className="text-xs text-slate-400 dark:text-slate-500 mt-0.5">{label}</p>
            </div>
        </div>
    );
}

// ─── Main component ───────────────────────────────────────────────────────────

export const LifecycleDashboard: React.FC<LifecycleDashboardProps> = ({
    onOpenBulkLiquidate,
}) => {
    const [capacity,     setCapacity]     = useState<CapacityData | null>(null);
    const [stats,        setStats]        = useState<LifecycleStats | null>(null);
    const [isLoading,    setIsLoading]    = useState(true);
    const [isRefreshing, setIsRefreshing] = useState(false);
    const [error,        setError]        = useState<string | null>(null);

    const load = useCallback(async (silent = false) => {
        if (!silent) setIsLoading(true);
        else setIsRefreshing(true);
        setError(null);
        try {
            const [cap, st] = await Promise.all([
                lifecycleService.getCapacity(),
                lifecycleService.getLifecycleStats(),
            ]);
            setCapacity(cap);
            setStats(st);
        } catch (err: any) {
            setError(err.response?.data?.detail || 'Failed to load lifecycle data.');
        } finally {
            setIsLoading(false);
            setIsRefreshing(false);
        }
    }, []);

    useEffect(() => { load(); }, [load]);

    // ── Render ────────────────────────────────────────────────────────────────

    if (isLoading) {
        return (
            <div className="flex items-center justify-center py-10 gap-2 text-slate-400 dark:text-slate-500">
                <LoadingSpinner size="md" />
                <span className="text-sm">Loading lifecycle data…</span>
            </div>
        );
    }

    if (error) {
        return (
            <div className="flex items-center gap-2 text-sm text-red-600 dark:text-red-400 p-4 rounded-xl border border-red-200 dark:border-red-500/20 bg-red-50 dark:bg-red-500/10">
                <AlertTriangle className="w-4 h-4 flex-shrink-0" />
                {error}
                <button
                    onClick={() => load()}
                    className="ml-auto text-xs underline underline-offset-2 hover:opacity-80"
                >
                    Retry
                </button>
            </div>
        );
    }

    const hasWarnings = capacity?.warnings && capacity.warnings.length > 0;

    return (
        <div className="space-y-6">

            {/* ── Section header ───────────────────────────────────────── */}
            <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                    <BarChart2 className="w-4 h-4 text-slate-400 dark:text-slate-500" />
                    <span className="text-xs font-semibold tracking-widest uppercase text-slate-400 dark:text-slate-500">
                        Lifecycle
                    </span>
                </div>
                <button
                    onClick={() => load(true)}
                    disabled={isRefreshing}
                    title="Refresh"
                    className="p-1.5 rounded-lg border border-slate-200 dark:border-[#1e2535] text-slate-400 hover:text-slate-600 dark:hover:text-slate-300 hover:bg-slate-50 dark:hover:bg-[#1e2535] disabled:opacity-50 transition-colors"
                >
                    <RefreshCw className={`w-3.5 h-3.5 ${isRefreshing ? 'animate-spin' : ''}`} />
                </button>
            </div>

            {/* ── Capacity warnings banner ─────────────────────────────── */}
            {hasWarnings && (
                <div className="rounded-xl border border-amber-200 dark:border-amber-500/20 bg-amber-50 dark:bg-amber-500/10 px-4 py-3 space-y-1">
                    {capacity!.warnings.map((w, i) => (
                        <div key={i} className="flex items-center gap-2 text-xs text-amber-700 dark:text-amber-300">
                            <AlertTriangle className="w-3.5 h-3.5 flex-shrink-0" />
                            {w}
                        </div>
                    ))}
                </div>
            )}

            {/* ── Capacity grid ────────────────────────────────────────── */}
            {capacity && (
                <>
                    <h3 className="text-sm font-semibold text-slate-700 dark:text-slate-200">
                        ID Pool Capacity
                    </h3>
                    <div className="grid grid-cols-2 gap-3">
                        {TIERS.map(({ key, label, icon, color }) => (
                            <CapacityCard
                                key={key}
                                label={label}
                                icon={icon}
                                color={color}
                                tier={capacity[key]}
                            />
                        ))}
                    </div>
                </>
            )}

            {/* ── Lifecycle event stats (30 days) ──────────────────────── */}
            {stats && (
                <>
                    <div className="flex items-center justify-between">
                        <h3 className="text-sm font-semibold text-slate-700 dark:text-slate-200">
                            Events — Last {stats.period_days} Days
                        </h3>
                    </div>
                    <div className="grid grid-cols-2 gap-2">
                        <EventStat
                            label="Spawned"
                            value={stats.lifecycle_events.spawned}
                            icon={Zap}
                            colorClass="bg-blue-100 dark:bg-blue-500/20 text-blue-600 dark:text-blue-400"
                        />
                        <EventStat
                            label="Promoted"
                            value={stats.lifecycle_events.promoted}
                            icon={TrendingUp}
                            colorClass="bg-emerald-100 dark:bg-emerald-500/20 text-emerald-600 dark:text-emerald-400"
                        />
                        <EventStat
                            label="Liquidated"
                            value={stats.lifecycle_events.liquidated}
                            icon={Trash2}
                            colorClass="bg-rose-100 dark:bg-rose-500/20 text-rose-600 dark:text-rose-400"
                        />
                        <EventStat
                            label="Reincarnated"
                            value={stats.lifecycle_events.reincarnated}
                            icon={RefreshCw}
                            colorClass="bg-violet-100 dark:bg-violet-500/20 text-violet-600 dark:text-violet-400"
                        />
                    </div>

                    {/* Active agents by tier */}
                    <div>
                        <h3 className="text-sm font-semibold text-slate-700 dark:text-slate-200 mb-2">
                            Active Agents by Tier
                        </h3>
                        <div className="rounded-xl border border-slate-200 dark:border-[#1e2535] divide-y divide-slate-100 dark:divide-[#1e2535] overflow-hidden">
                            {TIERS.map(({ key, label, icon: Icon, color }) => {
                                const tierKey = `tier_${['head','council','lead','task'].indexOf(key)}` as keyof typeof stats.active_agents_by_tier;
                                const count = stats.active_agents_by_tier[tierKey] ?? 0;
                                const { text, badge } = COLOR_MAP[color];
                                return (
                                    <div
                                        key={key}
                                        className="flex items-center justify-between px-4 py-2.5 bg-white dark:bg-[#0f1117]"
                                    >
                                        <div className="flex items-center gap-2">
                                            <Icon className={`w-3.5 h-3.5 ${text}`} />
                                            <span className="text-sm text-slate-700 dark:text-slate-300">{label}</span>
                                        </div>
                                        <span className={`text-xs font-semibold px-2 py-0.5 rounded-full ${badge}`}>
                                            {count}
                                        </span>
                                    </div>
                                );
                            })}
                        </div>
                    </div>
                </>
            )}

            {/* ── Bulk liquidate CTA ───────────────────────────────────── */}
            {onOpenBulkLiquidate && (
                <button
                    onClick={onOpenBulkLiquidate}
                    className="w-full flex items-center justify-center gap-2 px-4 py-2.5 rounded-xl border border-rose-200 dark:border-rose-500/20 bg-rose-50 dark:bg-rose-500/10 text-rose-700 dark:text-rose-300 text-sm font-medium hover:bg-rose-100 dark:hover:bg-rose-500/20 transition-colors"
                >
                    <Trash2 className="w-4 h-4" />
                    Bulk Liquidate Idle Agents
                </button>
            )}
        </div>
    );
};
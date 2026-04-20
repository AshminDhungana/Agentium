/**
 * CriticStatsPanel
 *
 * Shows aggregate critic statistics in the Agents page sidebar.
 * Ephemeral critic instances (7/8/9xxxx) are never shown individually —
 * only aggregate counts and approval rates per critic type are displayed.
 */

import React, { useEffect, useState, useCallback } from 'react';
import { api } from '../../services/api';
import { ShieldAlert, RefreshCw } from 'lucide-react';
import { LoadingSpinner } from '@/components/ui/LoadingSpinner';

interface CriticTypeStats {
    count: number;
    active: number;
    reviews: number;
    vetoes: number;
    escalations: number;
    approval_rate: number;
}

interface CriticStats {
    total_critics: number;
    active_critics: number;
    total_reviews: number;
    total_vetoes: number;
    total_escalations: number;
    overall_approval_rate: number;
    by_type: Record<string, CriticTypeStats>;
}

const TYPE_LABELS: Record<string, string> = {
    code:   'Code',
    output: 'Output',
    plan:   'Plan',
};

const TYPE_COLORS: Record<string, string> = {
    code:   'text-rose-600 dark:text-rose-400',
    output: 'text-amber-600 dark:text-amber-400',
    plan:   'text-blue-600 dark:text-blue-400',
};

export const CriticStatsPanel: React.FC = () => {
    const [stats, setStats]     = useState<CriticStats | null>(null);
    const [loading, setLoading] = useState(true);
    const [error, setError]     = useState<string | null>(null);

    const load = useCallback(async (silent = false) => {
        if (!silent) setLoading(true);
        setError(null);
        try {
            const res = await api.get('/api/v1/critics/stats');
            setStats(res.data);
        } catch {
            setError('Failed to load critic stats.');
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => { load(); }, [load]);

    if (loading) {
        return (
            <div className="flex items-center gap-2 text-slate-400 dark:text-slate-500 py-4">
                <LoadingSpinner size="sm" />
                <span className="text-xs">Loading critic stats…</span>
            </div>
        );
    }

    if (error || !stats) {
        return (
            <p className="text-xs text-slate-400 dark:text-slate-500 py-2">{error ?? 'No data'}</p>
        );
    }

    return (
        <div className="space-y-3">
            {/* Section header */}
            <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                    <ShieldAlert className="w-4 h-4 text-rose-500 dark:text-rose-400" />
                    <span className="text-xs font-semibold tracking-widest uppercase text-slate-400 dark:text-slate-500">
                        Critics
                    </span>
                </div>
                <button
                    onClick={() => load(true)}
                    className="p-1 rounded text-slate-400 hover:text-slate-600 dark:hover:text-slate-300 transition-colors"
                    title="Refresh"
                >
                    <RefreshCw className="w-3 h-3" />
                </button>
            </div>

            {/* Overall summary */}
            <div className="grid grid-cols-2 gap-2">
                <div className="rounded-lg border border-slate-200 dark:border-[#1e2535] bg-white dark:bg-[#0f1117] px-3 py-2">
                    <p className="text-xs text-slate-400 dark:text-slate-500">Total reviews</p>
                    <p className="text-base font-semibold text-slate-900 dark:text-white">
                        {stats.total_reviews.toLocaleString()}
                    </p>
                </div>
                <div className="rounded-lg border border-slate-200 dark:border-[#1e2535] bg-white dark:bg-[#0f1117] px-3 py-2">
                    <p className="text-xs text-slate-400 dark:text-slate-500">Approval rate</p>
                    <p className={`text-base font-semibold ${
                        stats.overall_approval_rate >= 80
                            ? 'text-emerald-600 dark:text-emerald-400'
                            : stats.overall_approval_rate >= 60
                            ? 'text-amber-600 dark:text-amber-400'
                            : 'text-rose-600 dark:text-rose-400'
                    }`}>
                        {stats.overall_approval_rate.toFixed(1)}%
                    </p>
                </div>
            </div>

            {/* Per-type breakdown */}
            <div className="rounded-xl border border-slate-200 dark:border-[#1e2535] divide-y divide-slate-100 dark:divide-[#1e2535] overflow-hidden">
                {(['code', 'output', 'plan'] as const).map(type => {
                    const t = stats.by_type[type];
                    if (!t) return null;
                    return (
                        <div
                            key={type}
                            className="flex items-center justify-between px-3 py-2.5 bg-white dark:bg-[#0f1117]"
                        >
                            <div>
                                <span className={`text-xs font-medium ${TYPE_COLORS[type]}`}>
                                    {TYPE_LABELS[type]}
                                </span>
                                <span className="text-xs text-slate-400 dark:text-slate-500 ml-1">
                                    {t.reviews.toLocaleString()} reviews
                                </span>
                            </div>
                            <div className="text-right">
                                <span className="text-xs font-semibold text-slate-700 dark:text-slate-300">
                                    {t.approval_rate.toFixed(0)}%
                                </span>
                                {t.vetoes > 0 && (
                                    <span className="ml-1.5 text-xs text-rose-500 dark:text-rose-400">
                                        {t.vetoes} veto{t.vetoes !== 1 ? 's' : ''}
                                    </span>
                                )}
                            </div>
                        </div>
                    );
                })}
            </div>

            <p className="text-xs text-slate-400 dark:text-slate-500 leading-relaxed">
                Critics spawn per-task and terminate on completion. Instances are not shown in the agent list.
            </p>
        </div>
    );
};
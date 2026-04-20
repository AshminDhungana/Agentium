import React, { useState, useEffect } from 'react';
import { adminService } from '@/services/admin';
import {
    DollarSign,
    Zap,
    TrendingUp,
    AlertTriangle,
    Activity,
    Server,
    } from 'lucide-react';
import { LoadingSpinner } from '@/components/ui/LoadingSpinner';

interface BudgetStatus {
    current_limits: {
        daily_token_limit: number;
        daily_cost_limit: number;
    };
    usage: {
        tokens_used_today: number;
        tokens_remaining: number;
        cost_used_today_usd: number;
        cost_remaining_usd: number;
        cost_percentage_used: number;
        cost_percentage_tokens: number;
    };
    can_modify: boolean;
}

interface BudgetHistory {
    period_days: number;
    total_tokens: number;
    total_requests: number;
    total_cost_usd: number;
    daily_breakdown: Record<string, {
        tokens: number;
        requests: number;
        cost_usd: number;
    }>;
    by_provider: Record<string, {
        tokens: number;
        requests: number;
        cost_usd: number;
    }>;
}

/**
 * Normalize the /admin/budget API response into the expected BudgetStatus shape.
 *
 * The API may return a flat object (all fields at the top level) instead of
 * the nested { current_limits: {}, usage: {} } structure the component expects.
 * This function handles both shapes gracefully.
 */
function normalizeBudgetStatus(data: any): BudgetStatus {
    // Already nested correctly
    if (data?.usage && data?.current_limits) {
        return data as BudgetStatus;
    }

    // Flat response — reconstruct the nested shape
    return {
        can_modify: data?.can_modify ?? false,
        current_limits: {
            daily_token_limit: data?.daily_token_limit ?? data?.current_limits?.daily_token_limit ?? 0,
            daily_cost_limit:  data?.daily_cost_limit  ?? data?.current_limits?.daily_cost_limit  ?? 0,
        },
        usage: {
            tokens_used_today:      data?.tokens_used_today      ?? 0,
            tokens_remaining:       data?.tokens_remaining       ?? 0,
            cost_used_today_usd:    data?.cost_used_today_usd    ?? 0,
            cost_remaining_usd:     data?.cost_remaining_usd     ?? 0,
            cost_percentage_used:   data?.cost_percentage_used   ?? 0,
            cost_percentage_tokens: data?.cost_percentage_tokens ?? 0,
        },
    };
}

function normalizeBudgetHistory(data: any): BudgetHistory {
    return {
        period_days:     data?.period_days     ?? 7,
        total_tokens:    data?.total_tokens    ?? 0,
        total_requests:  data?.total_requests  ?? 0,
        total_cost_usd:  data?.total_cost_usd  ?? 0,
        daily_breakdown: data?.daily_breakdown ?? {},
        by_provider:     data?.by_provider     ?? {},
    };
}

export const FinancialBurnDashboard: React.FC = () => {
    const [status,    setStatus]    = useState<BudgetStatus | null>(null);
    const [history,   setHistory]   = useState<BudgetHistory | null>(null);
    const [isLoading, setIsLoading] = useState(true);
    const [error,     setError]     = useState<string | null>(null);

    useEffect(() => {
        const fetchDashboardData = async () => {
            try {
                setIsLoading(true);
                setError(null);

                // C12: replaced direct api.get() calls with adminService methods
                // — consistent with the rest of the frontend service layer and
                //   mockable in tests without importing the axios instance directly.
                const [statusData, historyData] = await Promise.all([
                    adminService.getBudgetStatus(),
                    adminService.getBudgetHistory(7),
                ]);

                setStatus(normalizeBudgetStatus(statusData));
                setHistory(normalizeBudgetHistory(historyData));
            } catch (err: any) {
                console.error('Failed to fetch financial data:', err);
                setError(err?.response?.data?.detail || 'Failed to load financial data');
            } finally {
                setIsLoading(false);
            }
        };

        fetchDashboardData();
    }, []);

    if (isLoading) {
        return (
            <div className="flex flex-col items-center justify-center py-20 gap-3 text-slate-400 dark:text-slate-500">
                <LoadingSpinner size="lg" />
                <span>Loading financial metrics...</span>
            </div>
        );
    }

    if (error) {
        return (
            <div className="bg-red-50 dark:bg-red-500/10 border border-red-200 dark:border-red-500/20 rounded-xl p-6 text-center text-red-600 dark:text-red-400">
                <AlertTriangle className="w-10 h-10 mx-auto mb-3 opacity-80" />
                <h3 className="text-lg font-semibold mb-1">Failed to load metrics</h3>
                <p className="text-sm">{error}</p>
            </div>
        );
    }

    if (!status || !history) return null;

    // Guard: if usage is still undefined after normalization, show a safe empty state
    if (!status.usage || !status.current_limits) {
        return (
            <div className="bg-amber-50 dark:bg-amber-500/10 border border-amber-200 dark:border-amber-500/20 rounded-xl p-6 text-center text-amber-600 dark:text-amber-400">
                <AlertTriangle className="w-10 h-10 mx-auto mb-3 opacity-80" />
                <h3 className="text-lg font-semibold mb-1">Unexpected data format</h3>
                <p className="text-sm">The budget API returned an unrecognised response shape. Check the console for the raw response.</p>
            </div>
        );
    }

    const { usage, current_limits } = status;

    const getBarColor = (percentage: number) => {
        if (percentage >= 90) return 'bg-red-500 dark:bg-red-500';
        if (percentage >= 75) return 'bg-amber-500 dark:bg-amber-400';
        if (percentage >= 50) return 'bg-blue-500 dark:bg-blue-400';
        return 'bg-emerald-500 dark:bg-emerald-400';
    };

    return (
        <div className="space-y-6">
            {/* Top Cards: Live Usage vs Limits */}
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-5">
                {/* Cost Today */}
                <div className="bg-white dark:bg-[#161b27] p-6 rounded-xl border border-slate-200 dark:border-[#1e2535] shadow-sm hover:shadow-md transition-shadow">
                    <div className="flex items-center justify-between mb-4">
                        <div className="w-11 h-11 rounded-lg bg-emerald-100 dark:bg-emerald-500/10 flex items-center justify-center">
                            <DollarSign className="w-5 h-5 text-emerald-600 dark:text-emerald-400" />
                        </div>
                        <span className="text-2xl font-bold text-slate-900 dark:text-white">
                            ${(usage.cost_used_today_usd ?? 0).toFixed(2)}
                        </span>
                    </div>
                    <p className="text-sm font-medium text-slate-500 dark:text-slate-400 mb-3">Today's Spend</p>
                    <div className="w-full bg-slate-100 dark:bg-[#1e2535] rounded-full h-1.5 overflow-hidden">
                        <div
                            className={`${getBarColor(usage.cost_percentage_used ?? 0)} h-full transition-all duration-500`}
                            style={{ width: `${Math.min(usage.cost_percentage_used ?? 0, 100)}%` }}
                        />
                    </div>
                    <p className="text-xs text-slate-400 dark:text-slate-500 mt-2 flex justify-between">
                        <span>{(usage.cost_percentage_used ?? 0).toFixed(1)}% of limit</span>
                        <span>Max ${current_limits.daily_cost_limit}</span>
                    </p>
                </div>

                {/* Tokens Today */}
                <div className="bg-white dark:bg-[#161b27] p-6 rounded-xl border border-slate-200 dark:border-[#1e2535] shadow-sm hover:shadow-md transition-shadow">
                    <div className="flex items-center justify-between mb-4">
                        <div className="w-11 h-11 rounded-lg bg-blue-100 dark:bg-blue-500/10 flex items-center justify-center">
                            <Zap className="w-5 h-5 text-blue-600 dark:text-blue-400" />
                        </div>
                        <span className="text-2xl font-bold text-slate-900 dark:text-white">
                            {((usage.tokens_used_today ?? 0) / 1000).toFixed(1)}k
                        </span>
                    </div>
                    <p className="text-sm font-medium text-slate-500 dark:text-slate-400 mb-3">Tokens Used Today</p>
                    <div className="w-full bg-slate-100 dark:bg-[#1e2535] rounded-full h-1.5 overflow-hidden">
                        <div
                            className={`${getBarColor(usage.cost_percentage_tokens ?? 0)} h-full transition-all duration-500`}
                            style={{ width: `${Math.min(usage.cost_percentage_tokens ?? 0, 100)}%` }}
                        />
                    </div>
                    <p className="text-xs text-slate-400 dark:text-slate-500 mt-2 flex justify-between">
                        <span>{(usage.cost_percentage_tokens ?? 0).toFixed(1)}% of limit</span>
                        <span>Max {((current_limits.daily_token_limit ?? 0) / 1000).toFixed(0)}k</span>
                    </p>
                </div>

                {/* 7-Day Spend */}
                <div className="bg-white dark:bg-[#161b27] p-6 rounded-xl border border-slate-200 dark:border-[#1e2535] shadow-sm hover:shadow-md transition-shadow">
                    <div className="flex items-center justify-between mb-4">
                        <div className="w-11 h-11 rounded-lg bg-purple-100 dark:bg-purple-500/10 flex items-center justify-center">
                            <TrendingUp className="w-5 h-5 text-purple-600 dark:text-purple-400" />
                        </div>
                        <span className="text-2xl font-bold text-slate-900 dark:text-white">
                            ${(history.total_cost_usd ?? 0).toFixed(2)}
                        </span>
                    </div>
                    <p className="text-sm font-medium text-slate-500 dark:text-slate-400 mb-2">7-Day Total Spend</p>
                    <p className="text-xs text-slate-400 dark:text-slate-500">
                        Avg ${((history.total_cost_usd ?? 0) / (history.period_days || 1)).toFixed(2)} / day
                    </p>
                </div>

                {/* 7-Day Total Requests */}
                <div className="bg-white dark:bg-[#161b27] p-6 rounded-xl border border-slate-200 dark:border-[#1e2535] shadow-sm hover:shadow-md transition-shadow">
                    <div className="flex items-center justify-between mb-4">
                        <div className="w-11 h-11 rounded-lg bg-orange-100 dark:bg-orange-500/10 flex items-center justify-center">
                            <Activity className="w-5 h-5 text-orange-600 dark:text-orange-400" />
                        </div>
                        <span className="text-2xl font-bold text-slate-900 dark:text-white">
                            {history.total_requests ?? 0}
                        </span>
                    </div>
                    <p className="text-sm font-medium text-slate-500 dark:text-slate-400 mb-2">7-Day Total Requests</p>
                    <p className="text-xs text-slate-400 dark:text-slate-500">
                        {(history.total_requests ? (history.total_tokens / history.total_requests) : 0).toFixed(0)} avg tokens per req
                    </p>
                </div>
            </div>

            {/* Provider Breakdown */}
            <div className="bg-white dark:bg-[#161b27] rounded-xl border border-slate-200 dark:border-[#1e2535] shadow-sm overflow-hidden">
                <div className="p-5 border-b border-slate-100 dark:border-[#1e2535] flex items-center gap-3">
                    <div className="w-8 h-8 rounded-lg bg-indigo-100 dark:bg-indigo-500/10 flex items-center justify-center">
                        <Server className="w-4 h-4 text-indigo-600 dark:text-indigo-400" />
                    </div>
                    <h3 className="text-base font-semibold text-slate-900 dark:text-white">Usage by Provider</h3>
                </div>
                <div className="p-0 overflow-x-auto">
                    <table className="w-full text-sm text-left">
                        <thead className="bg-slate-50 dark:bg-[#0f1117] text-slate-500 dark:text-slate-400">
                            <tr>
                                <th className="px-6 py-3 font-medium">Provider</th>
                                <th className="px-6 py-3 font-medium">Cost (USD)</th>
                                <th className="px-6 py-3 font-medium">Tokens</th>
                                <th className="px-6 py-3 font-medium">Requests</th>
                            </tr>
                        </thead>
                        <tbody className="divide-y divide-slate-100 dark:divide-[#1e2535]">
                            {Object.entries(history.by_provider).map(([provider, stats]) => (
                                <tr key={provider} className="hover:bg-slate-50 dark:hover:bg-[#161b27]/80">
                                    <td className="px-6 py-4 font-medium text-slate-900 dark:text-white">
                                        {provider}
                                    </td>
                                    <td className="px-6 py-4 text-slate-600 dark:text-slate-300">
                                        ${(stats.cost_usd ?? 0).toFixed(4)}
                                    </td>
                                    <td className="px-6 py-4 text-slate-600 dark:text-slate-300">
                                        {(stats.tokens ?? 0).toLocaleString()}
                                    </td>
                                    <td className="px-6 py-4 text-slate-600 dark:text-slate-300">
                                        {(stats.requests ?? 0).toLocaleString()}
                                    </td>
                                </tr>
                            ))}
                            {Object.keys(history.by_provider).length === 0 && (
                                <tr>
                                    <td colSpan={4} className="px-6 py-8 text-center text-slate-500">
                                        No provider usage data available for this period.
                                    </td>
                                </tr>
                            )}
                        </tbody>
                    </table>
                </div>
            </div>
        </div>
    );
};
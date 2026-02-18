import { useState, useEffect } from 'react';
import { Coins, DollarSign, Shield, AlertTriangle } from 'lucide-react';
import { api } from '@/services/api';
import { useAuthStore } from '@/store/authStore';

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
    optimizer_status: {
        idle_mode_active: boolean;
        time_since_last_activity_seconds: number;
    };
}

export default function BudgetControl() {
    const [budget, setBudget] = useState<BudgetStatus | null>(null);
    const [tokenInput, setTokenInput] = useState('');
    const [costInput, setCostInput] = useState('');
    const [loading, setLoading] = useState(false);
    const [success, setSuccess] = useState(false);
    const { user } = useAuthStore();

    const fetchBudget = async () => {
        try {
            const response = await api.get('/api/v1/admin/budget');
            setBudget(response.data);
            setTokenInput(response.data.current_limits.daily_token_limit.toString());
            setCostInput(response.data.current_limits.daily_cost_limit.toString());
        } catch (error) {
            console.error('Failed to fetch budget:', error);
        }
    };

    useEffect(() => {
        fetchBudget();
    }, []);

    const handleUpdateBudget = async () => {
        setLoading(true);
        setSuccess(false);
        try {
            await api.post('/api/v1/admin/budget', {
                daily_token_limit: parseInt(tokenInput),
                daily_cost_limit: parseFloat(costInput),
            });
            setSuccess(true);
            await fetchBudget();
            setTimeout(() => setSuccess(false), 3000);
        } catch (error: any) {
            console.error('Failed to update budget:', error);
            alert(error.response?.data?.detail || 'Failed to update budget');
        } finally {
            setLoading(false);
        }
    };

    if (!budget) return (
        <div className="text-center p-4 text-gray-500 dark:text-gray-400 text-sm">
            Loading budget control…
        </div>
    );

    const canModifyBudget = budget.can_modify;
    const isOverBudget  = budget.usage.cost_percentage_used > 90;
    const isNearLimit   = budget.usage.cost_percentage_used > 75;

    const barColor = isOverBudget ? 'bg-red-500' : isNearLimit ? 'bg-amber-500' : '';

    return (
        <div className="w-full bg-white dark:bg-[#161b27] border border-gray-200 dark:border-[#1e2535] rounded-xl shadow-sm dark:shadow-[0_2px_16px_rgba(0,0,0,0.25)] transition-colors duration-200">

            {/* ── Header ──────────────────────────────────────────────── */}
            <div className="flex items-center justify-between px-6 py-5 border-b border-gray-100 dark:border-[#1e2535]">
                <h2 className="flex items-center gap-2.5 text-base font-semibold text-gray-900 dark:text-white">
                    <div className="w-8 h-8 rounded-lg bg-blue-100 dark:bg-blue-500/10 flex items-center justify-center">
                        <Coins className="h-4 w-4 text-blue-600 dark:text-blue-400" />
                    </div>
                    Budget Control Dashboard
                </h2>
                {canModifyBudget && (
                    <div title="Admin Access" className="w-8 h-8 rounded-lg bg-green-100 dark:bg-green-500/10 flex items-center justify-center">
                        <Shield className="h-4 w-4 text-green-600 dark:text-green-400" />
                    </div>
                )}
            </div>

            <div className="space-y-5 p-6">

                {/* ── Alert Banners ─────────────────────────────────────── */}
                {budget.optimizer_status.idle_mode_active && (
                    <div className="flex items-start gap-3 px-4 py-3 rounded-xl bg-yellow-50 dark:bg-yellow-500/10 border border-yellow-200 dark:border-yellow-500/20">
                        <AlertTriangle className="h-4 w-4 text-yellow-600 dark:text-yellow-400 mt-0.5 flex-shrink-0" />
                        <p className="text-sm text-yellow-800 dark:text-yellow-300">
                            System is in <span className="font-semibold">IDLE MODE</span> — using local models to save tokens.
                        </p>
                    </div>
                )}

                {isOverBudget && (
                    <div className="flex items-start gap-3 px-4 py-3 rounded-xl bg-red-50 dark:bg-red-500/10 border border-red-200 dark:border-red-500/20">
                        <AlertTriangle className="h-4 w-4 text-red-600 dark:text-red-400 mt-0.5 flex-shrink-0" />
                        <p className="text-sm text-red-800 dark:text-red-300">
                            <span className="font-semibold">CRITICAL:</span> You have exceeded 90% of your daily budget.
                        </p>
                    </div>
                )}

                {isNearLimit && !isOverBudget && (
                    <div className="flex items-start gap-3 px-4 py-3 rounded-xl bg-amber-50 dark:bg-amber-500/10 border border-amber-200 dark:border-amber-500/20">
                        <AlertTriangle className="h-4 w-4 text-amber-600 dark:text-amber-400 mt-0.5 flex-shrink-0" />
                        <p className="text-sm text-amber-800 dark:text-amber-300">
                            <span className="font-semibold">Warning:</span> You have used {budget.usage.cost_percentage_used}% of your budget.
                        </p>
                    </div>
                )}

                {/* ── Token + Cost Cards ────────────────────────────────── */}
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">

                    {/* Token Card */}
                    <div className="bg-blue-50 dark:bg-blue-500/10 border border-blue-200 dark:border-blue-500/20 rounded-xl p-4">
                        <div className="flex items-center gap-2 text-sm font-medium text-blue-900 dark:text-blue-400 mb-2">
                            <Coins className="h-4 w-4" />
                            Token Limit
                        </div>
                        <div className="text-3xl font-bold text-blue-700 dark:text-white mb-3">
                            {budget.current_limits.daily_token_limit.toLocaleString()}
                        </div>
                        <div className="flex justify-between text-xs text-blue-600 dark:text-blue-400/70 mb-1.5">
                            <span>Used</span>
                            <span className="font-medium text-blue-600 dark:text-blue-400">
                                {budget.usage.cost_percentage_tokens}%
                            </span>
                        </div>
                        <div className="w-full bg-blue-200 dark:bg-blue-500/20 rounded-full h-1.5">
                            <div
                                className={`h-1.5 rounded-full transition-all ${barColor || 'bg-blue-500'}`}
                                style={{ width: `${Math.min(budget.usage.cost_percentage_tokens, 100)}%` }}
                            />
                        </div>
                        <div className="text-xs text-blue-600/70 dark:text-blue-400/60 mt-1.5">
                            {budget.usage.tokens_used_today.toLocaleString()} / {budget.current_limits.daily_token_limit.toLocaleString()} used
                        </div>
                    </div>

                    {/* Cost Card */}
                    <div className="bg-green-50 dark:bg-green-500/10 border border-green-200 dark:border-green-500/20 rounded-xl p-4">
                        <div className="flex items-center gap-2 text-sm font-medium text-green-900 dark:text-green-400 mb-2">
                            <DollarSign className="h-4 w-4" />
                            Cost Limit (USD)
                        </div>
                        <div className="text-3xl font-bold text-green-700 dark:text-white mb-3">
                            ${budget.current_limits.daily_cost_limit.toFixed(2)}
                        </div>
                        <div className="flex justify-between text-xs text-green-600 dark:text-green-400/70 mb-1.5">
                            <span>Used</span>
                            <span className="font-medium text-green-600 dark:text-green-400">
                                {budget.usage.cost_percentage_used}%
                            </span>
                        </div>
                        <div className="w-full bg-green-200 dark:bg-green-500/20 rounded-full h-1.5">
                            <div
                                className={`h-1.5 rounded-full transition-all ${barColor || 'bg-green-500'}`}
                                style={{ width: `${Math.min(budget.usage.cost_percentage_used, 100)}%` }}
                            />
                        </div>
                        <div className="text-xs text-green-600/70 dark:text-green-400/60 mt-1.5">
                            ${budget.usage.cost_used_today_usd.toFixed(4)} / ${budget.current_limits.daily_cost_limit.toFixed(2)} used
                        </div>
                    </div>
                </div>

                {/* ── Usage Details ─────────────────────────────────────── */}
                <div className="bg-gray-50 dark:bg-[#0f1117] border border-gray-100 dark:border-[#1e2535] rounded-xl px-4 py-3 space-y-2.5">
                    {[
                        { label: 'Tokens Remaining',          value: budget.usage.tokens_remaining.toLocaleString() },
                        { label: 'Cost Remaining',            value: `$${budget.usage.cost_remaining_usd.toFixed(4)}` },
                        { label: 'Time Since Last Activity',  value: `${Math.floor(budget.optimizer_status.time_since_last_activity_seconds)}s` },
                    ].map(({ label, value }) => (
                        <div key={label} className="flex justify-between text-sm">
                            <span className="text-gray-500 dark:text-gray-400">{label}</span>
                            <span className="font-medium text-gray-900 dark:text-gray-100">{value}</span>
                        </div>
                    ))}
                </div>

                {/* ── Update Form — Admin Only ───────────────────────────── */}
                {canModifyBudget ? (
                    <div className="space-y-4 border-t border-gray-100 dark:border-[#1e2535] pt-5">
                        <h3 className="flex items-center gap-2 text-sm font-semibold text-gray-900 dark:text-white">
                            <Shield className="h-4 w-4 text-green-600 dark:text-green-400" />
                            Update Budget Settings
                        </h3>

                        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                            <div className="space-y-1.5">
                                <label htmlFor="token-limit" className="block text-xs font-medium text-gray-600 dark:text-gray-400">
                                    Token Limit
                                </label>
                                <input
                                    id="token-limit"
                                    type="number"
                                    value={tokenInput}
                                    onChange={(e) => setTokenInput(e.target.value)}
                                    min="1000"
                                    step="1000"
                                    className="w-full px-3 py-2 text-sm bg-white dark:bg-[#0f1117] border border-gray-200 dark:border-[#1e2535] rounded-lg text-gray-900 dark:text-white placeholder-gray-400 dark:placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500/40 focus:border-blue-500 transition-colors duration-150"
                                />
                                <p className="text-xs text-gray-400 dark:text-gray-500">Minimum: 1,000 tokens</p>
                            </div>

                            <div className="space-y-1.5">
                                <label htmlFor="cost-limit" className="block text-xs font-medium text-gray-600 dark:text-gray-400">
                                    Cost Limit (USD)
                                </label>
                                <input
                                    id="cost-limit"
                                    type="number"
                                    value={costInput}
                                    onChange={(e) => setCostInput(e.target.value)}
                                    min="0"
                                    step="0.1"
                                    className="w-full px-3 py-2 text-sm bg-white dark:bg-[#0f1117] border border-gray-200 dark:border-[#1e2535] rounded-lg text-gray-900 dark:text-white placeholder-gray-400 dark:placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500/40 focus:border-blue-500 transition-colors duration-150"
                                />
                                <p className="text-xs text-gray-400 dark:text-gray-500">Maximum: $ as much as you want/day</p>
                            </div>
                        </div>

                        <button
                            onClick={handleUpdateBudget}
                            disabled={loading}
                            className="w-full flex items-center justify-center gap-2 px-4 py-2.5 bg-blue-600 hover:bg-blue-700 dark:hover:bg-blue-500 disabled:opacity-50 disabled:cursor-not-allowed text-white text-sm font-medium rounded-lg transition-colors duration-150 shadow-sm"
                        >
                            {loading ? (
                                <>
                                    <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                                    Updating…
                                </>
                            ) : (
                                <>
                                    <Coins className="h-4 w-4" />
                                    Update Budget
                                </>
                            )}
                        </button>

                        {success && (
                            <div className="flex items-center gap-3 px-4 py-3 rounded-xl bg-green-50 dark:bg-green-500/10 border border-green-200 dark:border-green-500/20">
                                <Shield className="h-4 w-4 text-green-600 dark:text-green-400 flex-shrink-0" />
                                <p className="text-sm text-green-700 dark:text-green-300">Budget updated successfully!</p>
                            </div>
                        )}
                    </div>
                ) : (
                    <div className="flex items-center gap-3 px-4 py-3 rounded-xl bg-blue-50 dark:bg-blue-500/10 border border-blue-200 dark:border-blue-500/20">
                        <Shield className="h-4 w-4 text-blue-600 dark:text-blue-400 flex-shrink-0" />
                        <p className="text-sm text-blue-700 dark:text-blue-300">Only administrators can modify budget settings.</p>
                    </div>
                )}
            </div>
        </div>
    );
}

import { useState, useEffect, useCallback } from 'react';
import {
    Key,
    AlertTriangle,
    CheckCircle,
    XCircle,
    Clock,
    DollarSign,
    RefreshCw,
    Shield,
    Wifi,
    WifiOff,
    ChevronDown,
    ChevronUp,
    Zap,
    RotateCcw,
    Ban,
    TrendingUp,
    Activity
} from 'lucide-react';
import { api } from '@/services/api';
import { useAuthStore } from '@/store/authStore';
import { showToast } from '@/hooks/useToast';
import { LoadingSpinner } from '@/components/ui/LoadingSpinner';

// ── Types ─────────────────────────────────────────────────────────────────────

interface KeyHealth {
    id: string;
    provider: string;
    priority: number;
    status: 'healthy' | 'cooldown' | 'rate_limited' | 'exhausted' | 'error' | 'disabled';
    failure_count: number;
    cooldown_until: string | null;
    monthly_budget_usd: number;
    current_spend_usd: number;
    budget_remaining_pct: number;
}

interface ProviderSummary {
    total_keys: number;
    healthy: number;
    cooldown: number;
    rate_limited: number;
    exhausted: number;
    error: number;
    keys: KeyHealth[];
}

interface HealthReport {
    overall_status: 'healthy' | 'degraded' | 'critical';
    providers: Record<string, ProviderSummary>;
    summary: {
        total_keys: number;
        healthy_keys: number;
        keys_in_cooldown: number;
        budget_exhausted: number;
        total_monthly_spend: number;
    };
    generated_at: string;
}

interface ProviderAvailability {
    provider: string;
    available: boolean;
    healthy_keys_count: number;
}

// ── Constants ─────────────────────────────────────────────────────────────────

const PROVIDER_COLORS: Record<string, string> = {
    openai: 'from-emerald-500 to-teal-600',
    anthropic: 'from-orange-500 to-amber-600',
    gemini: 'from-blue-500 to-indigo-600',
    groq: 'from-purple-500 to-fuchsia-600',
    mistral: 'from-rose-500 to-pink-600',
    together: 'from-cyan-500 to-sky-600',
    cohere: 'from-violet-500 to-purple-600',
    moonshot: 'from-indigo-500 to-blue-600',
    deepseek: 'from-red-500 to-rose-600',
    azure_openai: 'from-blue-600 to-blue-800',
    local: 'from-slate-500 to-gray-600',
    custom: 'from-yellow-500 to-orange-600',
};

const PROVIDER_NAMES: Record<string, string> = {
    openai: 'OpenAI',
    anthropic: 'Anthropic',
    gemini: 'Google Gemini',
    groq: 'Groq',
    mistral: 'Mistral AI',
    together: 'Together AI',
    cohere: 'Cohere',
    moonshot: 'Moonshot (Kimi)',
    deepseek: 'DeepSeek',
    azure_openai: 'Azure OpenAI',
    local: 'Local (Ollama)',
    custom: 'Custom Provider',
};

const STATUS_CONFIG = {
    healthy: {
        icon: CheckCircle,
        color: 'text-green-600 dark:text-green-400',
        bg: 'bg-green-100 dark:bg-green-500/10',
        border: 'border-green-200 dark:border-green-500/20',
        label: 'Healthy',
    },
    cooldown: {
        icon: Clock,
        color: 'text-amber-600 dark:text-amber-400',
        bg: 'bg-amber-100 dark:bg-amber-500/10',
        border: 'border-amber-200 dark:border-amber-500/20',
        label: 'Cooldown',
    },
    rate_limited: {
        icon: Zap,
        color: 'text-yellow-600 dark:text-yellow-400',
        bg: 'bg-yellow-100 dark:bg-yellow-500/10',
        border: 'border-yellow-200 dark:border-yellow-500/20',
        label: 'Rate Limited',
    },
    exhausted: {
        icon: DollarSign,
        color: 'text-red-600 dark:text-red-400',
        bg: 'bg-red-100 dark:bg-red-500/10',
        border: 'border-red-200 dark:border-red-500/20',
        label: 'Budget Exhausted',
    },
    error: {
        icon: XCircle,
        color: 'text-red-600 dark:text-red-400',
        bg: 'bg-red-100 dark:bg-red-500/10',
        border: 'border-red-200 dark:border-red-500/20',
        label: 'Error',
    },
    disabled: {
        icon: Ban,
        color: 'text-gray-600 dark:text-gray-400',
        bg: 'bg-gray-100 dark:bg-gray-500/10',
        border: 'border-gray-200 dark:border-gray-500/20',
        label: 'Disabled',
    },
};

// ── Component ─────────────────────────────────────────────────────────────────

export default function APIKeyHealth() {
    const { user } = useAuthStore();
    const [report, setReport] = useState<HealthReport | null>(null);
    const [availability, setAvailability] = useState<ProviderAvailability[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [expandedProviders, setExpandedProviders] = useState<Set<string>>(new Set());
    const [recoveringKeys, setRecoveringKeys] = useState<Set<string>>(new Set());
    const [lastUpdated, setLastUpdated] = useState<Date>(new Date());
    const [autoRefresh, setAutoRefresh] = useState(true);
    // Tracks which key is pending force-recovery confirmation
    const [forceRecoveryPendingId, setForceRecoveryPendingId] = useState<string | null>(null);
    const [forceCooldownMsg, setForceCooldownMsg] = useState<string>('');

    const isAdmin = user?.is_admin || user?.role === 'admin';

    const fetchHealthData = useCallback(async () => {
        try {
            const [healthRes, availRes] = await Promise.all([
                api.get('/api/v1/api-keys/health'),
                api.get('/api/v1/api-keys/availability'),
            ]);

            setReport(healthRes.data);
            setAvailability(availRes.data);
            setLastUpdated(new Date());
            setError(null);
        } catch (err: any) {
            setError(err.response?.data?.detail || 'Failed to fetch API key health');
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => {
        fetchHealthData();
    }, [fetchHealthData]);

    useEffect(() => {
        if (!autoRefresh) return;
        const interval = setInterval(() => {
            fetchHealthData();
        }, 30000);
        return () => clearInterval(interval);
    }, [autoRefresh, fetchHealthData]);

    const toggleProvider = (provider: string) => {
        setExpandedProviders(prev => {
            const next = new Set(prev);
            if (next.has(provider)) next.delete(provider);
            else next.add(provider);
            return next;
        });
    };

    /**
     * Attempt normal recovery first.
     * If the backend returns a cooldown-related error, show inline confirmation
     * UI instead of calling window.confirm().
     */
    const handleRecoverKey = async (keyId: string, force = false) => {
        setRecoveringKeys(prev => new Set(prev).add(keyId));
        // Clear any pending force confirmation for this key when starting a recovery
        if (!force) setForceRecoveryPendingId(null);

        try {
            await api.post(`/api/v1/api-keys/${keyId}/recover`, { force });
            showToast.success('Key recovery successful');
            await fetchHealthData();
        } catch (err: any) {
            const msg = err.response?.data?.detail || 'Recovery failed';
            if (!force && msg.toLowerCase().includes('cooldown')) {
                // Surface inline force-recovery confirmation
                setForceCooldownMsg(msg);
                setForceRecoveryPendingId(keyId);
            } else {
                showToast.error(msg);
            }
        } finally {
            setRecoveringKeys(prev => {
                const next = new Set(prev);
                next.delete(keyId);
                return next;
            });
        }
    };

    const handleCancelForceRecovery = () => {
        setForceRecoveryPendingId(null);
        setForceCooldownMsg('');
    };

    const formatCooldown = (isoDate: string | null): string => {
        if (!isoDate) return '';
        const end = new Date(isoDate);
        const now = new Date();
        const diffMs = end.getTime() - now.getTime();
        if (diffMs <= 0) return 'Expired';
        const diffMins = Math.ceil(diffMs / 60000);
        return `${diffMins}m remaining`;
    };

    const getOverallStatusConfig = (status: string) => {
        switch (status) {
            case 'healthy':
                return {
                    icon: CheckCircle,
                    color: 'text-green-600 dark:text-green-400',
                    bg: 'bg-green-100 dark:bg-green-500/10',
                    border: 'border-green-200 dark:border-green-500/20',
                    label: 'All Systems Operational',
                };
            case 'degraded':
                return {
                    icon: AlertTriangle,
                    color: 'text-amber-600 dark:text-amber-400',
                    bg: 'bg-amber-100 dark:bg-amber-500/10',
                    border: 'border-amber-200 dark:border-amber-500/20',
                    label: 'Degraded Performance',
                };
            case 'critical':
                return {
                    icon: XCircle,
                    color: 'text-red-600 dark:text-red-400',
                    bg: 'bg-red-100 dark:bg-red-500/10',
                    border: 'border-red-200 dark:border-red-500/20',
                    label: 'Critical: No Healthy Keys',
                };
            default:
                return STATUS_CONFIG.error;
        }
    };

    if (loading) {
        return (
            <div className="w-full bg-white dark:bg-[#161b27] border border-gray-200 dark:border-[#1e2535] rounded-xl shadow-sm dark:shadow-[0_2px_16px_rgba(0,0,0,0.25)] p-8">
                <div className="flex items-center justify-center gap-3">
                    <LoadingSpinner size="md" />
                    <span className="text-sm text-gray-500 dark:text-gray-400">Loading API key health...</span>
                </div>
            </div>
        );
    }

    if (error) {
        return (
            <div className="w-full bg-white dark:bg-[#161b27] border border-gray-200 dark:border-[#1e2535] rounded-xl shadow-sm dark:shadow-[0_2px_16px_rgba(0,0,0,0.25)] p-6">
                <div className="flex items-start gap-3 p-4 bg-red-50 dark:bg-red-500/10 border border-red-200 dark:border-red-500/20 rounded-xl">
                    <AlertTriangle className="w-5 h-5 text-red-600 dark:text-red-400 flex-shrink-0 mt-0.5" />
                    <div>
                        <p className="text-sm font-medium text-red-900 dark:text-red-300">Failed to Load API Key Health</p>
                        <p className="text-sm text-red-700 dark:text-red-400/80 mt-0.5">{error}</p>
                        <button
                            onClick={fetchHealthData}
                            className="mt-3 text-xs font-medium text-red-700 dark:text-red-400 hover:text-red-800 dark:hover:text-red-300 flex items-center gap-1.5"
                        >
                            <RefreshCw className="w-3 h-3" />
                            Retry
                        </button>
                    </div>
                </div>
            </div>
        );
    }

    if (!report) return null;

    const overall = getOverallStatusConfig(report.overall_status);
    const OverallIcon = overall.icon;

    return (
        <div className="w-full bg-white dark:bg-[#161b27] border border-gray-200 dark:border-[#1e2535] rounded-xl shadow-sm dark:shadow-[0_2px_16px_rgba(0,0,0,0.25)] transition-colors duration-200">

            {/* ── Header ──────────────────────────────────────────────── */}
            <div className="flex items-center justify-between px-6 py-5 border-b border-gray-100 dark:border-[#1e2535]">
                <div className="flex items-center gap-3">
                    <div className="w-9 h-9 rounded-lg bg-gradient-to-br from-blue-500 to-indigo-600 flex items-center justify-center">
                        <Key className="w-5 h-5 text-white" />
                    </div>
                    <div>
                        <h2 className="text-base font-semibold text-gray-900 dark:text-white">
                            API Key Health
                        </h2>
                        <p className="text-xs text-gray-500 dark:text-gray-400">
                            Phase 5.4 Resilience & Failover System
                        </p>
                    </div>
                </div>

                <div className="flex items-center gap-3">
                    <button
                        onClick={() => setAutoRefresh(!autoRefresh)}
                        className={`flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-xs font-medium transition-colors ${
                            autoRefresh
                                ? 'bg-green-100 dark:bg-green-500/10 text-green-700 dark:text-green-400'
                                : 'bg-gray-100 dark:bg-[#1e2535] text-gray-600 dark:text-gray-400'
                        }`}
                        title={autoRefresh ? 'Auto-refresh enabled (30s)' : 'Auto-refresh disabled'}
                    >
                        <Activity className="w-3.5 h-3.5" />
                        {autoRefresh ? 'Live' : 'Paused'}
                    </button>

                    <button
                        onClick={fetchHealthData}
                        className="p-2 rounded-lg text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200 hover:bg-gray-100 dark:hover:bg-[#1e2535] transition-colors"
                        title="Refresh now"
                    >
                        <RefreshCw className="w-4 h-4" />
                    </button>

                    <div className={`flex items-center gap-2 px-3 py-1.5 rounded-lg ${overall.bg} ${overall.border} border`}>
                        <OverallIcon className={`w-4 h-4 ${overall.color}`} />
                        <span className={`text-xs font-semibold ${overall.color}`}>{overall.label}</span>
                    </div>
                </div>
            </div>

            <div className="p-6 space-y-6">

                {/* ── Critical Alert ──────────────────────────────────────── */}
                {report.overall_status === 'critical' && (
                    <div className="flex items-start gap-3 p-4 bg-red-50 dark:bg-red-500/10 border border-red-200 dark:border-red-500/20 rounded-xl">
                        <WifiOff className="w-5 h-5 text-red-600 dark:text-red-400 flex-shrink-0 mt-0.5" />
                        <div>
                            <p className="text-sm font-semibold text-red-900 dark:text-red-300">
                                Critical: No Healthy API Keys
                            </p>
                            <p className="text-sm text-red-700 dark:text-red-400/80 mt-0.5">
                                All API providers are currently unavailable. The system is operating in local-only mode.
                                Check your API keys and budgets immediately.
                            </p>
                        </div>
                    </div>
                )}

                {/* ── Summary Cards ─────────────────────────────────────────── */}
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                    <div className="bg-blue-50 dark:bg-blue-500/10 border border-blue-200 dark:border-blue-500/20 rounded-xl p-4">
                        <div className="flex items-center gap-2 text-sm font-medium text-blue-900 dark:text-blue-400 mb-1">
                            <Key className="w-4 h-4" />
                            Total Keys
                        </div>
                        <div className="text-2xl font-bold text-blue-700 dark:text-white">
                            {report.summary.total_keys}
                        </div>
                    </div>

                    <div className="bg-green-50 dark:bg-green-500/10 border border-green-200 dark:border-green-500/20 rounded-xl p-4">
                        <div className="flex items-center gap-2 text-sm font-medium text-green-900 dark:text-green-400 mb-1">
                            <CheckCircle className="w-4 h-4" />
                            Healthy
                        </div>
                        <div className="text-2xl font-bold text-green-700 dark:text-white">
                            {report.summary.healthy_keys}
                        </div>
                    </div>

                    <div className="bg-amber-50 dark:bg-amber-500/10 border border-amber-200 dark:border-amber-500/20 rounded-xl p-4">
                        <div className="flex items-center gap-2 text-sm font-medium text-amber-900 dark:text-amber-400 mb-1">
                            <Clock className="w-4 h-4" />
                            In Cooldown
                        </div>
                        <div className="text-2xl font-bold text-amber-700 dark:text-white">
                            {report.summary.keys_in_cooldown}
                        </div>
                    </div>

                    <div className="bg-purple-50 dark:bg-purple-500/10 border border-purple-200 dark:border-purple-500/20 rounded-xl p-4">
                        <div className="flex items-center gap-2 text-sm font-medium text-purple-900 dark:text-purple-400 mb-1">
                            <DollarSign className="w-4 h-4" />
                            Monthly Spend
                        </div>
                        <div className="text-2xl font-bold text-purple-700 dark:text-white">
                            ${report.summary.total_monthly_spend.toFixed(2)}
                        </div>
                    </div>
                </div>

                {/* ── Provider Details ────────────────────────────────────── */}
                <div className="space-y-3">
                    <h3 className="text-sm font-semibold text-gray-900 dark:text-white flex items-center gap-2">
                        <Shield className="w-4 h-4 text-gray-500 dark:text-gray-400" />
                        Provider Status
                    </h3>

                    {Object.entries(report.providers).length === 0 ? (
                        <div className="text-center py-8 text-sm text-gray-500 dark:text-gray-400 bg-gray-50 dark:bg-[#0f1117] rounded-xl border border-dashed border-gray-200 dark:border-[#1e2535]">
                            No API keys configured.{' '}
                            <a href="/models" className="text-blue-600 dark:text-blue-400 hover:underline ml-1">
                                Add your first key
                            </a>
                        </div>
                    ) : (
                        Object.entries(report.providers).map(([provider, data]) => {
                            const isExpanded = expandedProviders.has(provider);
                            const colorClass = PROVIDER_COLORS[provider] || 'from-gray-500 to-slate-600';
                            const isAvailable = availability.find(a => a.provider === provider)?.available ?? false;

                            return (
                                <div
                                    key={provider}
                                    className="bg-gray-50 dark:bg-[#0f1117] border border-gray-200 dark:border-[#1e2535] rounded-xl overflow-hidden"
                                >
                                    <button
                                        onClick={() => toggleProvider(provider)}
                                        className="w-full flex items-center justify-between px-4 py-3.5 hover:bg-gray-100 dark:hover:bg-[#1e2535] transition-colors"
                                    >
                                        <div className="flex items-center gap-3">
                                            <div className={`w-8 h-8 rounded-lg bg-gradient-to-br ${colorClass} flex items-center justify-center flex-shrink-0`}>
                                                <Key className="w-4 h-4 text-white" />
                                            </div>
                                            <div className="text-left">
                                                <p className="text-sm font-semibold text-gray-900 dark:text-white">
                                                    {PROVIDER_NAMES[provider] || provider}
                                                </p>
                                                <p className="text-xs text-gray-500 dark:text-gray-400">
                                                    {data.total_keys} key{data.total_keys !== 1 ? 's' : ''} •{' '}
                                                    {data.healthy} healthy
                                                    {data.cooldown > 0 && ` • ${data.cooldown} in cooldown`}
                                                    {data.exhausted > 0 && ` • ${data.exhausted} budget exhausted`}
                                                </p>
                                            </div>
                                        </div>

                                        <div className="flex items-center gap-3">
                                            <div className={`flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium ${
                                                isAvailable
                                                    ? 'bg-green-100 dark:bg-green-500/10 text-green-700 dark:text-green-400'
                                                    : 'bg-red-100 dark:bg-red-500/10 text-red-700 dark:text-red-400'
                                            }`}>
                                                {isAvailable
                                                    ? <><Wifi className="w-3 h-3" /> Available</>
                                                    : <><WifiOff className="w-3 h-3" /> Unavailable</>
                                                }
                                            </div>

                                            {isExpanded
                                                ? <ChevronUp className="w-4 h-4 text-gray-400 dark:text-gray-500" />
                                                : <ChevronDown className="w-4 h-4 text-gray-400 dark:text-gray-500" />
                                            }
                                        </div>
                                    </button>

                                    {isExpanded && (
                                        <div className="border-t border-gray-200 dark:border-[#1e2535]">
                                            <div className="p-4 space-y-3">
                                                {data.keys.map((key) => {
                                                    const statusConfig = STATUS_CONFIG[key.status];
                                                    const StatusIcon = statusConfig.icon;
                                                    const isRecovering = recoveringKeys.has(key.id);
                                                    const isPendingForce = forceRecoveryPendingId === key.id;

                                                    return (
                                                        <div
                                                            key={key.id}
                                                            className={`flex flex-col p-3 rounded-lg border ${
                                                                key.status === 'healthy'
                                                                    ? 'bg-white dark:bg-[#161b27] border-gray-200 dark:border-[#1e2535]'
                                                                    : `${statusConfig.bg} ${statusConfig.border} border`
                                                            }`}
                                                        >
                                                            <div className="flex items-center justify-between">
                                                                <div className="flex items-center gap-3">
                                                                    <div className={`w-8 h-8 rounded-lg flex items-center justify-center ${
                                                                        key.priority <= 2
                                                                            ? 'bg-blue-100 dark:bg-blue-500/10'
                                                                            : 'bg-gray-100 dark:bg-[#1e2535]'
                                                                    }`}>
                                                                        <span className={`text-xs font-bold ${
                                                                            key.priority <= 2
                                                                                ? 'text-blue-600 dark:text-blue-400'
                                                                                : 'text-gray-500 dark:text-gray-400'
                                                                        }`}>
                                                                            P{key.priority}
                                                                        </span>
                                                                    </div>

                                                                    <div>
                                                                        <div className="flex items-center gap-2">
                                                                            <StatusIcon className={`w-4 h-4 ${statusConfig.color}`} />
                                                                            <span className={`text-sm font-medium ${statusConfig.color}`}>
                                                                                {statusConfig.label}
                                                                            </span>
                                                                            {key.failure_count > 0 && (
                                                                                <span className="text-xs text-gray-500 dark:text-gray-400">
                                                                                    ({key.failure_count} failures)
                                                                                </span>
                                                                            )}
                                                                        </div>

                                                                        {key.cooldown_until && (
                                                                            <p className="text-xs text-amber-600 dark:text-amber-400 mt-0.5">
                                                                                <Clock className="w-3 h-3 inline mr-1" />
                                                                                {formatCooldown(key.cooldown_until)}
                                                                            </p>
                                                                        )}

                                                                        {key.monthly_budget_usd > 0 && (
                                                                            <div className="mt-2">
                                                                                <div className="flex items-center justify-between text-xs mb-1">
                                                                                    <span className="text-gray-500 dark:text-gray-400">
                                                                                        Budget: ${key.current_spend_usd.toFixed(2)} / ${key.monthly_budget_usd.toFixed(2)}
                                                                                    </span>
                                                                                    <span className={`font-medium ${
                                                                                        key.budget_remaining_pct < 10
                                                                                            ? 'text-red-600 dark:text-red-400'
                                                                                            : key.budget_remaining_pct < 25
                                                                                                ? 'text-amber-600 dark:text-amber-400'
                                                                                                : 'text-green-600 dark:text-green-400'
                                                                                    }`}>
                                                                                        {key.budget_remaining_pct.toFixed(0)}%
                                                                                    </span>
                                                                                </div>
                                                                                <div className="w-full bg-gray-200 dark:bg-[#1e2535] rounded-full h-1.5">
                                                                                    <div
                                                                                        className={`h-1.5 rounded-full transition-all ${
                                                                                            key.budget_remaining_pct < 10
                                                                                                ? 'bg-red-500'
                                                                                                : key.budget_remaining_pct < 25
                                                                                                    ? 'bg-amber-500'
                                                                                                    : 'bg-green-500'
                                                                                        }`}
                                                                                        style={{ width: `${Math.min(100, 100 - key.budget_remaining_pct)}%` }}
                                                                                    />
                                                                                </div>
                                                                            </div>
                                                                        )}
                                                                    </div>
                                                                </div>

                                                                {/* Actions */}
                                                                <div className="flex items-center gap-2">
                                                                    {key.status !== 'healthy' && key.status !== 'disabled' && isAdmin && !isPendingForce && (
                                                                        <button
                                                                            onClick={() => handleRecoverKey(key.id)}
                                                                            disabled={isRecovering}
                                                                            className="flex items-center gap-1.5 px-3 py-1.5 bg-white dark:bg-[#161b27] border border-gray-200 dark:border-[#1e2535] hover:border-green-300 dark:hover:border-green-500/30 text-gray-700 dark:text-gray-300 text-xs font-medium rounded-lg transition-colors disabled:opacity-50"
                                                                        >
                                                                            {isRecovering
                                                                                ? <><LoadingSpinner size="xs" /> Recovering...</>
                                                                                : <><RotateCcw className="w-3 h-3" /> Recover</>
                                                                            }
                                                                        </button>
                                                                    )}

                                                                    {key.status === 'healthy' && (
                                                                        <span className="text-xs text-green-600 dark:text-green-400 font-medium flex items-center gap-1">
                                                                            <TrendingUp className="w-3 h-3" />
                                                                            Active
                                                                        </span>
                                                                    )}
                                                                </div>
                                                            </div>

                                                            {/* Inline force-recovery confirmation (replaces window.confirm) */}
                                                            {isPendingForce && (
                                                                <div className="mt-3 p-3 rounded-lg bg-amber-50 dark:bg-amber-500/10 border border-amber-200 dark:border-amber-500/20">
                                                                    <p className="text-xs text-amber-700 dark:text-amber-300 mb-2">
                                                                        {forceCooldownMsg} — force recovery anyway?
                                                                    </p>
                                                                    <div className="flex gap-2">
                                                                        <button
                                                                            onClick={() => handleRecoverKey(key.id, true)}
                                                                            disabled={isRecovering}
                                                                            className="flex items-center gap-1.5 px-3 py-1.5 bg-amber-600 hover:bg-amber-700 text-white text-xs font-medium rounded-lg transition-colors disabled:opacity-50"
                                                                        >
                                                                            {isRecovering
                                                                                ? <><LoadingSpinner size="xs" /> Forcing...</>
                                                                                : <><RotateCcw className="w-3 h-3" /> Force Recovery</>
                                                                            }
                                                                        </button>
                                                                        <button
                                                                            onClick={handleCancelForceRecovery}
                                                                            className="px-3 py-1.5 border border-gray-200 dark:border-[#1e2535] text-gray-600 dark:text-gray-400 text-xs font-medium rounded-lg hover:bg-gray-50 dark:hover:bg-[#1e2535] transition-colors"
                                                                        >
                                                                            Cancel
                                                                        </button>
                                                                    </div>
                                                                </div>
                                                            )}
                                                        </div>
                                                    );
                                                })}
                                            </div>
                                        </div>
                                    )}
                                </div>
                            );
                        })
                    )}
                </div>

                {/* ── Footer ───────────────────────────────────────────────── */}
                <div className="flex items-center justify-between pt-4 border-t border-gray-100 dark:border-[#1e2535] text-xs text-gray-500 dark:text-gray-400">
                    <div className="flex items-center gap-4">
                        <span>Last updated: {lastUpdated.toLocaleTimeString()}</span>
                        {report.generated_at && (
                            <span>Backend: {new Date(report.generated_at).toLocaleTimeString()}</span>
                        )}
                    </div>
                    <div className="flex items-center gap-2">
                        <span className="w-2 h-2 rounded-full bg-green-500" />
                        <span>Failover active</span>
                    </div>
                </div>
            </div>
        </div>
    );
}
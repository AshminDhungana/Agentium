/**
 * frontend/src/pages/ModelsPage.tsx
 *
 * AI Model Configurations page.
 */

import React, { useState, Component } from 'react';
import {
    Plus,
    AlertCircle,
    Server,
    CheckCircle2,
    BarChart3,
    Activity,
    Settings,
    RefreshCw,
} from 'lucide-react';

import { ModelConfigForm } from '@/components/models/ModelConfigForm';
import { ModelCard } from '@/components/models/ModelCard';
import { ModelCardSkeleton } from '@/components/models/ModelCardSkeleton';
import { useModelConfigs } from '@/hooks/useModelConfigs';
import { formatTokenCount } from '@/utils/time';

// ─── Error Boundary ───────────────────────────────────────────────────────────
//
// Catches render-time errors (such as React error #31 — objects rendered as
// JSX children) so the page never goes completely dark. Instead the user sees
// a friendly error card with a Reload button.

interface EBState { hasError: boolean; message: string }

class ModelConfigErrorBoundary extends Component<
    { children: React.ReactNode },
    EBState
> {
    state: EBState = { hasError: false, message: '' };

    static getDerivedStateFromError(err: unknown): EBState {
        const message =
            err instanceof Error ? err.message : String(err ?? 'Unknown render error');
        return { hasError: true, message };
    }

    handleReload = () => {
        this.setState({ hasError: false, message: '' });
    };

    render() {
        if (!this.state.hasError) return this.props.children;

        return (
            <div className="min-h-screen bg-gray-50 dark:bg-[#0f1117] p-6 flex items-center justify-center">
                <div className="max-w-md w-full bg-white dark:bg-[#161b27] rounded-xl border border-red-200 dark:border-red-500/20 shadow-sm p-8 text-center">
                    <div className="inline-flex items-center justify-center w-14 h-14 rounded-full bg-red-100 dark:bg-red-500/10 mb-5">
                        <AlertCircle className="w-7 h-7 text-red-600 dark:text-red-400" />
                    </div>
                    <h2 className="text-xl font-bold text-gray-900 dark:text-white mb-2">
                        Something went wrong
                    </h2>
                    <p className="text-sm text-gray-500 dark:text-gray-400 mb-2">
                        An unexpected error occurred while rendering this page.
                    </p>
                    {this.state.message && (
                        <p className="text-xs font-mono text-red-600 dark:text-red-400 bg-red-50 dark:bg-red-500/10 rounded-lg px-3 py-2 mb-6 break-all text-left">
                            {this.state.message}
                        </p>
                    )}
                    <button
                        onClick={this.handleReload}
                        className="inline-flex items-center gap-2 px-5 py-2.5 bg-blue-600 hover:bg-blue-700 text-white rounded-lg text-sm font-medium transition-colors duration-150"
                    >
                        <RefreshCw className="w-4 h-4" />
                        Try Again
                    </button>
                </div>
            </div>
        );
    }
}

// ─── Summary stat card (local — uses the existing shared StatCard shape) ──────
// We keep a local version here because the ModelsPage SummaryCard accepts
// ReactNode icons (not LucideIcon constructors like the dashboard StatCard does).
// If StatCard is ever refactored to accept ReactNode, this can be removed.

const SummaryCard: React.FC<{
    label: string;
    value: string | number;
    icon: React.ReactNode;
    color: 'blue' | 'green' | 'purple' | 'orange';
}> = ({ label, value, icon, color }) => {
    const colorClasses = {
        blue: { bg: 'bg-blue-100 dark:bg-blue-500/10', text: 'text-blue-600 dark:text-blue-400' },
        green: { bg: 'bg-green-100 dark:bg-green-500/10', text: 'text-green-600 dark:text-green-400' },
        purple: { bg: 'bg-purple-100 dark:bg-purple-500/10', text: 'text-purple-600 dark:text-purple-400' },
        orange: { bg: 'bg-orange-100 dark:bg-orange-500/10', text: 'text-orange-600 dark:text-orange-400' },
    };
    const c = colorClasses[color];
    return (
        <div
            className="bg-white dark:bg-[#161b27] p-6 rounded-xl border border-gray-200 dark:border-[#1e2535] hover:border-gray-300 dark:hover:border-[#2a3347] hover:shadow-md dark:hover:shadow-[0_4px_20px_rgba(0,0,0,0.35)] transition-all duration-150"
            role="region"
            aria-label={`${label}: ${value}`}
        >
            <div className="flex items-center justify-between mb-4">
                <div className={`w-11 h-11 rounded-lg ${c.bg} flex items-center justify-center`}>
                    <span className={c.text} aria-hidden="true">{icon}</span>
                </div>
                <span className="text-2xl font-bold text-gray-900 dark:text-white">{value}</span>
            </div>
            <p className="text-sm font-medium text-gray-500 dark:text-gray-400">{label}</p>
        </div>
    );
};

// ─── Inner page (wrapped by ErrorBoundary below) ──────────────────────────────

const ModelsPageInner: React.FC = () => {
    const [showForm, setShowForm] = useState(false);
    const [editingConfig, setEditingConfig] = useState<import('@/types').ModelConfig | null>(null);

    const {
        configs,
        loading,
        error,
        activeActions,
        pendingDeleteId,
        activeCount,
        totalTokens,
        totalCost,
        loadConfigs,
        handleDelete,
        handleSetDefault,
        handleTest,
        handleFetchModels,
        handleSave,
        setPendingDeleteId,
    } = useModelConfigs();

    const handleEdit = (config: import('@/types').ModelConfig) => {
        setEditingConfig(config);
        setShowForm(true);
    };

    const handleSaveAndClose = async (config: import('@/types').ModelConfig) => {
        await handleSave(config);
        setShowForm(false);
        setEditingConfig(null);
    };

    // ── Initial load skeleton (no configs in cache yet) ────────────────────
    if (loading && configs.length === 0) {
        return (
            <div
                className="min-h-screen bg-gray-50 dark:bg-[#0f1117] p-6 transition-colors duration-200 flex items-center justify-center"
                aria-live="polite"
                aria-busy="true"
            >
                <div className="flex flex-col items-center gap-3">
                    <div className="w-12 h-12 border-4 border-blue-200 dark:border-blue-500/30 border-t-blue-600 dark:border-t-blue-400 rounded-full animate-spin" />
                    <p className="text-gray-500 dark:text-gray-400 text-sm">Loading configurations…</p>
                </div>
            </div>
        );
    }

    // ── Form view ──────────────────────────────────────────────────────────
    if (showForm) {
        return (
            <ModelConfigForm
                initialConfig={editingConfig || undefined}
                onSave={handleSaveAndClose}
                onCancel={() => {
                    setShowForm(false);
                    setEditingConfig(null);
                }}
            />
        );
    }

    // ── Main view ──────────────────────────────────────────────────────────
    return (
        <div className="min-h-screen bg-gray-50 dark:bg-[#0f1117] p-6 transition-colors duration-200">
            <div className="max-w-7xl mx-auto">

                {/* ── Page Header ──────────────────────────────────────────── */}
                <div className="mb-8">
                    <div className="flex items-center justify-between mb-1">
                        <h1 className="text-3xl font-bold text-gray-900 dark:text-white">
                            AI Model Configurations
                        </h1>
                        <button
                            onClick={() => setShowForm(true)}
                            aria-label="Add new AI provider"
                            className="px-4 py-2 bg-blue-600 hover:bg-blue-700 dark:bg-blue-600 dark:hover:bg-blue-500 text-white rounded-lg font-medium transition-colors duration-150 flex items-center gap-2 shadow-sm"
                        >
                            <Plus className="w-4 h-4" aria-hidden="true" />
                            <span>Add Provider</span>
                        </button>
                    </div>
                    <p className="text-gray-500 dark:text-gray-400 text-sm">
                        Connect to powerful AI providers and manage your model fleet.
                    </p>
                </div>

                {/* ── Summary Stats ─────────────────────────────────────────── */}
                <div
                    className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-5 mb-8"
                    role="region"
                    aria-label="Provider statistics"
                >
                    <SummaryCard
                        label="Total Providers"
                        value={configs.length}
                        icon={<Server className="w-5 h-5" />}
                        color="blue"
                    />
                    <SummaryCard
                        label="Active Providers"
                        value={activeCount}
                        icon={<CheckCircle2 className="w-5 h-5" />}
                        color="green"
                    />
                    <SummaryCard
                        label="Total Tokens"
                        value={formatTokenCount(totalTokens)}
                        icon={<BarChart3 className="w-5 h-5" />}
                        color="purple"
                    />
                    <SummaryCard
                        label="Est. Cost"
                        value={`$${totalCost.toFixed(2)}`}
                        icon={<Activity className="w-5 h-5" />}
                        color="orange"
                    />
                </div>

                {/* ── Error Banner ──────────────────────────────────────────── */}
                {error && (
                    <div
                        className="mb-6 p-4 bg-red-50 dark:bg-red-500/10 border border-red-200 dark:border-red-500/20 rounded-xl flex items-start gap-3"
                        role="alert"
                    >
                        <AlertCircle className="w-5 h-5 text-red-600 dark:text-red-400 shrink-0 mt-0.5" aria-hidden="true" />
                        <div className="flex-1">
                            <p className="font-medium text-red-900 dark:text-red-300 text-sm">
                                Failed to load configurations
                            </p>
                            {/* FIX: String() coercion — ensures we never render a raw error object */}
                            <p className="text-sm text-red-700 dark:text-red-400/80 mt-0.5">{String(error)}</p>
                        </div>
                        <button
                            onClick={loadConfigs}
                            aria-label="Retry loading configurations"
                            className="px-3 py-1.5 bg-red-100 dark:bg-red-500/10 hover:bg-red-200 dark:hover:bg-red-500/20 text-red-700 dark:text-red-400 rounded-lg text-sm font-medium transition-colors duration-150 border border-red-200 dark:border-red-500/20"
                        >
                            Retry
                        </button>
                    </div>
                )}

                {/* ── Configs Grid ──────────────────────────────────────────── */}
                {/* Show skeletons while refreshing (configs already in state) */}
                {loading && configs.length > 0 ? (
                    <div
                        className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-5"
                        aria-busy="true"
                        aria-label="Loading configurations"
                    >
                        {Array.from({ length: configs.length || 3 }).map((_, i) => (
                            <ModelCardSkeleton key={i} />
                        ))}
                    </div>
                ) : configs.length === 0 ? (
                    // Empty state
                    <div className="text-center py-20" role="status">
                        <div className="inline-flex items-center justify-center w-20 h-20 bg-white dark:bg-[#161b27] border border-gray-200 dark:border-[#1e2535] rounded-2xl mb-6 shadow-sm dark:shadow-[0_2px_16px_rgba(0,0,0,0.25)]">
                            <Settings className="w-9 h-9 text-gray-400 dark:text-gray-500" aria-hidden="true" />
                        </div>
                        <h3 className="text-2xl font-bold text-gray-900 dark:text-white mb-2">
                            No Configurations Yet
                        </h3>
                        <p className="text-gray-500 dark:text-gray-400 text-sm mb-8 max-w-md mx-auto">
                            Get started by adding your first AI provider. Connect OpenAI, Claude, Gemini, Groq, or run models locally with Ollama.
                        </p>
                        <button
                            onClick={() => setShowForm(true)}
                            aria-label="Add your first AI provider"
                            className="px-6 py-2.5 bg-blue-600 hover:bg-blue-700 dark:hover:bg-blue-500 text-white rounded-lg font-medium transition-colors duration-150 inline-flex items-center gap-2 shadow-sm"
                        >
                            <Plus className="w-4 h-4" aria-hidden="true" />
                            Add Your First Provider
                        </button>
                    </div>
                ) : (
                    <div
                        className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-5"
                        role="list"
                        aria-label="Model configurations"
                    >
                        {configs.map((config) => (
                            <div key={config.id} role="listitem">
                                <ModelCard
                                    config={config}
                                    activeAction={activeActions.get(config.id) ?? null}
                                    pendingDeleteId={pendingDeleteId}
                                    onTest={handleTest}
                                    onFetchModels={handleFetchModels}
                                    onEdit={handleEdit}
                                    onDelete={handleDelete}
                                    onSetDefault={handleSetDefault}
                                    onPendingDelete={setPendingDeleteId}
                                />
                            </div>
                        ))}
                    </div>
                )}
            </div>
        </div>
    );
};

// ─── Page (exported) ──────────────────────────────────────────────────────────
//
// Wrapping ModelsPageInner in ModelConfigErrorBoundary means any render crash
// (React error #31, null-deref in a card, etc.) shows a friendly error card
// instead of a blank/dark page. The "Try Again" button resets the boundary
// so the user doesn't need to reload the whole app.

export const ModelsPage: React.FC = () => (
    <ModelConfigErrorBoundary>
        <ModelsPageInner />
    </ModelConfigErrorBoundary>
);

export default ModelsPage;
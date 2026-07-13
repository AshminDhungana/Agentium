/**
 * @description Individual provider configuration card for the Models page.
 * Extracted from ModelsPage so it can be memoised — the grid only re-renders
 * cards that actually changed, not the entire list on every action.
 * @example
 * ```tsx
 * import { ModelCard } from '@/components/models/ModelCard';
 *
 * <ModelCard config={config} onUpdate={handleUpdate} onDelete={handleDelete} />
 * ```
 * @param {ModelConfig} props.config - The model configuration to display.
 * @param {(config: ModelConfig) => void} props.onUpdate - Callback to update the configuration.
 * @param {(id: string) => void} props.onDelete - Callback to delete the configuration.
 */

import React, { useMemo, useRef, useEffect, useState } from 'react';
import {
    Check,
    RefreshCw,
    Play,
    Edit2,
    Trash2,
    Key,
    CheckCircle2,
    XCircle,
    Clock,
    AlertTriangle,
} from 'lucide-react';
import type { ModelConfig } from '@/types';
import { getProviderMeta } from '@/constants/providerMeta';
import { formatTokenCount } from '@/utils/time';
import { LoadingSpinner } from '@/components/ui/LoadingSpinner';

// ─── Types ────────────────────────────────────────────────────────────────────

/** The per-card async action currently in flight, or null if idle. */
export type CardAction = 'testing' | 'deleting' | 'fetching';

export interface ModelCardProps {
    config: ModelConfig;
    /** The action currently running on THIS card (null = nothing running). */
    activeAction: CardAction | null;
    /**
     * When non-null and matches config.id, the card shows inline delete
     * confirmation instead of the normal delete button.
     */
    pendingDeleteId: string | null;
    onTest: (id: string) => void;
    onFetchModels: (id: string) => void;
    onEdit: (config: ModelConfig) => void;
    onDelete: (id: string) => void;
    onSetDefault: (id: string) => void;
    onPendingDelete: (id: string | null) => void;
}

// ─── Sub-components ───────────────────────────────────────────────────────────

const StatusBadge: React.FC<{ status: string }> = ({ status }) => {
    // FIX: previously every card had role="status" unconditionally, so a bulk
    // refresh that updates 6 cards at once could trigger 6 simultaneous screen
    // reader announcements. role="status" is now only applied once this badge's
    // status has actually changed post-mount — the initial render of the grid
    // stays silent.
    const isInitialMount = useRef(true);
    const [announceChange, setAnnounceChange] = useState(false);

    useEffect(() => {
        if (isInitialMount.current) {
            isInitialMount.current = false;
            return;
        }
        setAnnounceChange(true);
    }, [status]);

    const map: Record<string, { cls: string; icon: React.ReactNode; label: string }> = {
        active: {
            cls: 'bg-green-100 text-green-700 border-green-200 dark:bg-green-500/10 dark:text-green-400 dark:border-green-500/20',
            icon: <CheckCircle2 className="w-3 h-3" />,
            label: 'Active',
        },
        testing: {
            cls: 'bg-yellow-100 text-yellow-700 border-yellow-200 dark:bg-yellow-500/10 dark:text-yellow-400 dark:border-yellow-500/20',
            icon: <Clock className="w-3 h-3 animate-pulse" />,
            label: 'Testing',
        },
        error: {
            cls: 'bg-red-100 text-red-700 border-red-200 dark:bg-red-500/10 dark:text-red-400 dark:border-red-500/20',
            icon: <XCircle className="w-3 h-3" />,
            label: 'Error',
        },
    };
    const s = map[status] ?? {
        cls: 'bg-gray-100 text-gray-600 border-gray-200 dark:bg-[#1e2535] dark:text-gray-400 dark:border-[#2a3347]',
        icon: <Clock className="w-3 h-3" />,
        label: status ?? 'Unknown',
    };
    return (
        <span
            className={`inline-flex items-center gap-1 px-2 py-0.5 text-xs font-medium rounded-full border ${s.cls}`}
            role={announceChange ? 'status' : undefined}
            aria-label={`Status: ${s.label}`}
        >
            {s.icon}
            {s.label}
        </span>
    );
};

// ─── Main component ───────────────────────────────────────────────────────────

export const ModelCard: React.FC<ModelCardProps> = React.memo(({
    config,
    activeAction,
    pendingDeleteId,
    onTest,
    onFetchModels,
    onEdit,
    onDelete,
    onSetDefault,
    onPendingDelete,
}) => {
    // FIX: pure lookup keyed only on config.provider — memoized so it doesn't
    // recompute (and rebuild any icon JSX) on every render of every card.
    const meta = useMemo(() => getProviderMeta(config.provider), [config.provider]);
    const isTesting = activeAction === 'testing';
    const isDeleting = activeAction === 'deleting';
    const isFetching = activeAction === 'fetching';
    const isAnyBusy = activeAction !== null;
    const awaitingDeleteConfirm = pendingDeleteId === config.id;

    // FIX: when the Trash button is swapped for Confirm/Cancel, focus stayed
    // wherever it was — keyboard and screen-reader users got no signal the UI
    // changed under them. Move focus to Confirm as soon as it appears.
    const confirmButtonRef = useRef<HTMLButtonElement>(null);
    useEffect(() => {
        if (awaitingDeleteConfirm) {
            confirmButtonRef.current?.focus();
        }
    }, [awaitingDeleteConfirm]);

    return (
        <div
            className="group relative bg-white dark:bg-[#161b27] rounded-xl border border-gray-200 dark:border-[#1e2535] hover:border-gray-300 dark:hover:border-[#2a3347] hover:shadow-md dark:hover:shadow-[0_4px_20px_rgba(0,0,0,0.35)] transition-all duration-150 overflow-hidden"
            role="article"
            aria-label={`${config.config_name} configuration`}
        >
            {/* Gradient accent bar */}
            <div className={`h-0.5 bg-gradient-to-r ${meta.gradient}`} aria-hidden="true" />

            <div className="p-5">

                {/* ── Header row ─────────────────────────────────────────── */}
                <div className="flex items-start justify-between mb-4">
                    <div className={`flex items-center gap-2 px-3 py-1.5 rounded-lg ${meta.bg} border ${meta.border} border-transparent`}>
                        <span className={meta.color} aria-hidden="true">{meta.cardIcon}</span>
                        <span className={`text-sm font-semibold ${meta.color}`}>
                            {config.provider_name || meta.label}
                        </span>
                    </div>
                    <div className="flex items-center gap-2">
                        {config.is_default && (
                            <span
                                className="inline-flex items-center gap-1 px-2 py-0.5 text-xs font-semibold rounded-full border bg-green-100 text-green-700 border-green-200 dark:bg-green-500/10 dark:text-green-400 dark:border-green-500/20"
                                aria-label="Default configuration"
                            >
                                <Check className="w-3 h-3" aria-hidden="true" />
                                Default
                            </span>
                        )}
                        <StatusBadge status={config.status} />
                    </div>
                </div>

                {/* ── Config name ────────────────────────────────────────── */}
                <h3 className="text-base font-semibold text-gray-900 dark:text-white mb-4 truncate">
                    {config.config_name}
                </h3>

                {/* ── Model info ─────────────────────────────────────────── */}
                <div className="space-y-2 mb-4">
                    <div className="flex items-center justify-between text-sm">
                        <span className="text-gray-600 dark:text-gray-400">Model</span>
                        <span
                            className="font-mono text-xs text-gray-900 dark:text-gray-100 bg-gray-100 dark:bg-[#0f1117] border border-gray-200 dark:border-[#1e2535] px-2 py-0.5 rounded-md truncate max-w-[180px]"
                            title={config.default_model}
                        >
                            {config.default_model}
                        </span>
                    </div>
                    {config.api_key_masked && (
                        <div className="flex items-center justify-between text-sm">
                            <span className="text-gray-600 dark:text-gray-400 flex items-center gap-1.5">
                                <Key className="w-3 h-3" aria-hidden="true" />
                                API Key
                            </span>
                            <span className="font-mono text-xs text-gray-600 dark:text-gray-500">
                                {config.api_key_masked}
                            </span>
                        </div>
                    )}
                    <div className="flex items-center justify-between text-sm">
                        <span className="text-gray-600 dark:text-gray-400">Rate limit</span>
                        <span className="font-mono text-xs text-gray-600 dark:text-gray-500">
                            {config.requests_per_minute} requests/minute
                        </span>
                    </div>
                </div>

                {/* ── Available model tags ────────────────────────────────── */}
                {config.available_models && config.available_models.length > 0 && (
                    <div className="mb-4">
                        <div className="text-xs text-gray-600 dark:text-gray-400 mb-2">Available Models</div>
                        <div className="flex flex-wrap gap-1.5" role="list" aria-label="Available models">
                            {config.available_models.slice(0, 4).map((model) => (
                                <span
                                    key={model}
                                    role="listitem"
                                    title={model}
                                    className={`text-xs px-2 py-0.5 rounded-md border font-mono transition-colors duration-150 ${model === config.default_model
                                            ? 'bg-blue-50 dark:bg-blue-500/10 text-blue-700 dark:text-blue-300 border-blue-200 dark:border-blue-500/20'
                                            : 'bg-gray-50 dark:bg-[#0f1117] text-gray-600 dark:text-gray-400 border-gray-200 dark:border-[#1e2535]'
                                        }`}
                                >
                                    {model.split('/').pop()?.slice(0, 20)}
                                </span>
                            ))}
                            {config.available_models.length > 4 && (
                                <span
                                    role="listitem"
                                    aria-label={`${config.available_models.length - 4} more models`}
                                    className="text-xs text-gray-600 dark:text-gray-500 px-2 py-0.5 bg-gray-50 dark:bg-[#0f1117] border border-gray-200 dark:border-[#1e2535] rounded-md"
                                >
                                    +{config.available_models.length - 4}
                                </span>
                            )}
                        </div>
                    </div>
                )}

                {/* ── Usage stats ─────────────────────────────────────────── */}
                <div
                    className="grid grid-cols-3 gap-0 mb-4 bg-gray-50 dark:bg-[#0f1117] rounded-lg border border-gray-100 dark:border-[#1e2535] overflow-hidden"
                    role="group"
                    aria-label="Usage statistics"
                >
                    <div className="text-center px-3 py-2.5">
                        <div className="text-xs text-gray-600 dark:text-gray-400 mb-1">Requests</div>
                        <div className="text-sm font-bold text-gray-900 dark:text-white">
                            {(config.total_usage?.requests ?? 0).toLocaleString()}
                        </div>
                    </div>
                    <div className="text-center px-3 py-2.5 border-x border-gray-100 dark:border-[#1e2535]">
                        <div className="text-xs text-gray-600 dark:text-gray-400 mb-1">Tokens</div>
                        <div className="text-sm font-bold text-gray-900 dark:text-white">
                            {formatTokenCount(config.total_usage?.tokens ?? 0)}
                        </div>
                    </div>
                    <div className="text-center px-3 py-2.5">
                        <div className="text-xs text-gray-600 dark:text-gray-400 mb-1">Cost</div>
                        <div className="text-sm font-bold text-emerald-600 dark:text-emerald-400">
                            ${(config.total_usage?.cost_usd ?? 0).toFixed(2)}
                        </div>
                    </div>
                </div>

                {/* ── Action buttons ──────────────────────────────────────── */}
                <div className="flex gap-2" role="group" aria-label={`Actions for ${config.config_name}`}>

                    {/* Set Default */}
                    {!config.is_default && (
                        <button
                            onClick={() => onSetDefault(config.id)}
                            disabled={isAnyBusy}
                            aria-label={`Set ${config.config_name} as default`}
                            title="Set as default"
                            className="flex-1 px-2.5 py-2 bg-gray-100 dark:bg-[#1e2535] hover:bg-gray-200 dark:hover:bg-[#2a3347] text-gray-700 dark:text-gray-300 rounded-lg text-xs font-medium transition-colors duration-150 flex items-center justify-center gap-1.5 border border-transparent dark:border-[#2a3347]/0 hover:dark:border-[#2a3347] disabled:opacity-50"
                        >
                            <Check className="w-3.5 h-3.5" aria-hidden="true" />
                            Default
                        </button>
                    )}

                    {/* Test */}
                    <button
                        onClick={() => onTest(config.id)}
                        disabled={isAnyBusy}
                        aria-label={`Test connection for ${config.config_name}`}
                        title="Test connection"
                        className="flex-1 px-2.5 py-2 bg-blue-100 dark:bg-blue-500/10 hover:bg-blue-200 dark:hover:bg-blue-500/20 text-blue-700 dark:text-blue-400 rounded-lg text-xs font-medium transition-colors duration-150 flex items-center justify-center gap-1.5 disabled:opacity-50 border border-blue-200 dark:border-blue-500/20"
                    >
                        {isTesting
                            ? <LoadingSpinner size="sm" />
                            : <Play className="w-3.5 h-3.5" aria-hidden="true" />
                        }
                        {isTesting ? 'Testing…' : 'Test'}
                    </button>

                    {/* Fetch Models — hidden only for custom providers that have no base URL stored,
                        since there is no endpoint to call without one. */}
                    {(config.provider !== 'custom' || !!config.api_base_url) && (
                    <button
                        onClick={() => onFetchModels(config.id)}
                        disabled={isAnyBusy}
                        aria-label={`Fetch available models for ${config.config_name}`}
                        title="Fetch available models"
                        className="flex-1 px-2.5 py-2 bg-purple-100 dark:bg-purple-500/10 hover:bg-purple-200 dark:hover:bg-purple-500/20 text-purple-700 dark:text-purple-400 rounded-lg text-xs font-medium transition-colors duration-150 flex items-center justify-center gap-1.5 disabled:opacity-50 border border-purple-200 dark:border-purple-500/20"
                    >
                        {isFetching ? (
                            <LoadingSpinner size="sm" />
                        ) : (
                            <RefreshCw className="w-3.5 h-3.5" aria-hidden="true" />
                        )}
                        {isFetching ? 'Fetching…' : 'Fetch'}
                    </button>
                    )}

                    {/* Edit */}
                    <button
                        onClick={() => onEdit(config)}
                        disabled={isAnyBusy}
                        aria-label={`Edit ${config.config_name}`}
                        title="Edit configuration"
                        className="px-2.5 py-2 bg-gray-100 dark:bg-[#1e2535] hover:bg-gray-200 dark:hover:bg-[#2a3347] text-gray-600 dark:text-gray-400 rounded-lg transition-colors duration-150 border border-transparent dark:border-[#2a3347]/0 hover:dark:border-[#2a3347] disabled:opacity-50"
                    >
                        <Edit2 className="w-3.5 h-3.5" aria-hidden="true" />
                    </button>

                    {/* Delete — shows inline confirm when pending */}
                    {awaitingDeleteConfirm ? (
                        <div className="flex items-center gap-1">
                            <button
                                ref={confirmButtonRef}
                                onClick={() => onDelete(config.id)}
                                disabled={isDeleting}
                                aria-label={`Confirm delete ${config.config_name}`}
                                className="px-2.5 py-2 bg-red-600 hover:bg-red-700 text-white rounded-lg text-xs font-medium transition-colors duration-150 disabled:opacity-50 flex items-center gap-1"
                            >
                                {isDeleting
                                    ? <LoadingSpinner size="sm" />
                                    : 'Confirm'
                                }
                            </button>
                            <button
                                onClick={() => onPendingDelete(null)}
                                aria-label="Cancel delete"
                                className="px-2.5 py-2 bg-gray-100 dark:bg-[#1e2535] hover:bg-gray-200 dark:hover:bg-[#2a3347] text-gray-600 dark:text-gray-400 rounded-lg text-xs transition-colors duration-150"
                            >
                                Cancel
                            </button>
                        </div>
                    ) : (
                        <button
                            onClick={() => onPendingDelete(config.id)}
                            disabled={isAnyBusy}
                            aria-label={`Delete ${config.config_name}`}
                            title="Delete configuration"
                            className="px-2.5 py-2 bg-red-100 dark:bg-red-500/10 hover:bg-red-200 dark:hover:bg-red-500/20 text-red-700 dark:text-red-400 rounded-lg transition-colors duration-150 disabled:opacity-50 border border-red-200 dark:border-red-500/20"
                        >
                            <Trash2 className="w-3.5 h-3.5" aria-hidden="true" />
                        </button>
                    )}
                </div>
            </div>

            {/* Subtle gradient hover glow */}
            <div
                className={`absolute inset-0 bg-gradient-to-br ${meta.gradient} opacity-0 group-hover:opacity-[0.03] transition-opacity duration-300 pointer-events-none`}
                aria-hidden="true"
            />
        </div>
    );
});

ModelCard.displayName = 'ModelCard';
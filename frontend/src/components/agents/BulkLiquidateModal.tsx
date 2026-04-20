import React, { useState } from 'react';
import { lifecycleService, BulkLiquidateDryRunResult, BulkLiquidateResult } from '../../services/agents';
import { X, Trash2, AlertCircle, Eye, CheckCircle2, SkipForward } from 'lucide-react';
import { LoadingSpinner } from '@/components/ui/LoadingSpinner';

interface BulkLiquidateModalProps {
    onClose:   () => void;
    onSuccess: (count: number) => void;
}

type Step = 'configure' | 'preview' | 'confirm' | 'done';

/**
 * BulkLiquidateModal
 *
 * Three-step flow:
 *  1. Configure  — set idle threshold
 *  2. Preview    — dry-run to show which agents would be liquidated
 *  3. Confirm    — execute with a final "Are you sure?" gate
 *  4. Done       — show summary
 */
export const BulkLiquidateModal: React.FC<BulkLiquidateModalProps> = ({
    onClose,
    onSuccess,
}) => {
    const [step,          setStep]          = useState<Step>('configure');
    const [threshold,     setThreshold]     = useState(7);
    const [isLoading,     setIsLoading]     = useState(false);
    const [error,         setError]         = useState<string | null>(null);
    const [previewResult, setPreviewResult] = useState<BulkLiquidateDryRunResult | null>(null);
    const [execResult,    setExecResult]    = useState<BulkLiquidateResult | null>(null);

    // ── Step 1 → Step 2: dry-run preview ─────────────────────────────────────
    const runDryRun = async () => {
        setIsLoading(true);
        setError(null);
        try {
            const result = await lifecycleService.bulkLiquidateIdle(threshold, true);
            setPreviewResult(result as BulkLiquidateDryRunResult);
            setStep('preview');
        } catch (err: any) {
            setError(err.response?.data?.detail || 'Failed to fetch idle agents.');
        } finally {
            setIsLoading(false);
        }
    };

    // ── Step 3 → Step 4: execute liquidation ─────────────────────────────────
    const execute = async () => {
        setIsLoading(true);
        setError(null);
        try {
            const result = await lifecycleService.bulkLiquidateIdle(threshold, false);
            setExecResult(result as BulkLiquidateResult);
            setStep('done');
            onSuccess((result as BulkLiquidateResult).liquidated_count);
        } catch (err: any) {
            setError(err.response?.data?.detail || 'Bulk liquidation failed.');
        } finally {
            setIsLoading(false);
        }
    };

    const titleMap: Record<Step, string> = {
        configure: 'Bulk Liquidate Idle Agents',
        preview:   'Preview — Agents to Liquidate',
        confirm:   'Confirm Bulk Liquidation',
        done:      'Liquidation Complete',
    };

    return (
        <div className="fixed inset-0 bg-black/50 dark:bg-black/70 backdrop-blur-sm flex items-center justify-center z-50 p-4">
            <div className="bg-white dark:bg-[#161b27] rounded-2xl shadow-2xl dark:shadow-[0_24px_80px_rgba(0,0,0,0.7)] w-full max-w-md border border-gray-200 dark:border-[#1e2535]">

                {/* ── Header ─────────────────────────────────────────────── */}
                <div className="flex justify-between items-center px-6 py-5 border-b border-gray-100 dark:border-[#1e2535]">
                    <h2 className="text-base font-semibold text-gray-900 dark:text-white flex items-center gap-2.5">
                        <div className="w-8 h-8 rounded-lg bg-rose-100 dark:bg-rose-500/10 border border-rose-200 dark:border-rose-500/20 flex items-center justify-center">
                            <Trash2 className="w-4 h-4 text-rose-600 dark:text-rose-400" />
                        </div>
                        {titleMap[step]}
                    </h2>
                    <button
                        aria-label="Close"
                        onClick={onClose}
                        className="w-8 h-8 rounded-lg flex items-center justify-center text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 hover:bg-gray-100 dark:hover:bg-[#1e2535] transition-colors"
                    >
                        <X className="w-4 h-4" />
                    </button>
                </div>

                <div className="p-6 space-y-4">

                    {/* ═══════════════════════════════════════════════════════
                        STEP 1 — Configure
                    ═══════════════════════════════════════════════════════ */}
                    {step === 'configure' && (
                        <>
                            <p className="text-sm text-gray-600 dark:text-gray-400">
                                Scan for agents that have been inactive beyond a threshold and stage them for liquidation.
                                A <span className="font-semibold text-gray-900 dark:text-white">dry-run preview</span> will run first so you can review before committing.
                            </p>

                            <div>
                                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5">
                                    Idle threshold (days)
                                </label>
                                <input aria-label="Idle threshold (days)"
                                    type="number"
                                    min={1}
                                    max={365}
                                    value={threshold}
                                    onChange={e => setThreshold(Math.max(1, Number(e.target.value)))}
                                    className="w-full px-4 py-2.5 text-sm bg-white dark:bg-[#0f1117] border border-gray-200 dark:border-[#1e2535] rounded-lg text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-rose-500/40 focus:border-rose-500 transition-colors"
                                />
                                <p className="text-xs text-gray-400 dark:text-gray-500 mt-1">
                                    Agents inactive for ≥ {threshold} day{threshold !== 1 ? 's' : ''} will be flagged.
                                </p>
                            </div>

                            {error && <ErrorBanner message={error} />}

                            <div className="flex gap-3 pt-2">
                                <button onClick={onClose} className={cancelCls}>Cancel</button>
                                <button
                                    onClick={runDryRun}
                                    disabled={isLoading}
                                    className={`flex-1 px-4 py-2.5 bg-amber-500 hover:bg-amber-600 text-white text-sm font-medium rounded-lg transition-colors disabled:opacity-40 disabled:cursor-not-allowed shadow-sm flex items-center justify-center gap-2`}
                                >
                                    {isLoading
                                        ? <><LoadingSpinner size="sm" /> Scanning…</>
                                        : <><Eye className="w-4 h-4" /> Preview Idle Agents</>
                                    }
                                </button>
                            </div>
                        </>
                    )}

                    {/* ═══════════════════════════════════════════════════════
                        STEP 2 — Preview
                    ═══════════════════════════════════════════════════════ */}
                    {step === 'preview' && previewResult && (
                        <>
                            {previewResult.idle_agents_found === 0 ? (
                                <div className="flex flex-col items-center gap-2 py-4 text-emerald-700 dark:text-emerald-400">
                                    <CheckCircle2 className="w-8 h-8" />
                                    <p className="text-sm font-medium">No idle agents found.</p>
                                    <p className="text-xs text-gray-400 dark:text-gray-500">
                                        No agents have been idle for ≥ {threshold} days.
                                    </p>
                                </div>
                            ) : (
                                <>
                                    <p className="text-sm text-gray-700 dark:text-gray-300">
                                        <span className="font-semibold text-rose-600 dark:text-rose-400">
                                            {previewResult.idle_agents_found}
                                        </span>{' '}
                                        agent{previewResult.idle_agents_found !== 1 ? 's' : ''} would be liquidated:
                                    </p>

                                    <ul className="max-h-48 overflow-y-auto space-y-1.5 rounded-xl border border-gray-200 dark:border-[#1e2535] p-3 bg-gray-50 dark:bg-[#0f1117]">
                                        {previewResult.idle_agents.map(a => (
                                            <li
                                                key={a.agentium_id}
                                                className="flex justify-between items-center text-xs text-gray-700 dark:text-gray-300"
                                            >
                                                <span className="font-medium truncate">{a.name}</span>
                                                <span className="ml-2 shrink-0 font-mono text-gray-400 dark:text-gray-500">
                                                    {a.agentium_id} · {a.idle_days}d idle
                                                </span>
                                            </li>
                                        ))}
                                    </ul>
                                </>
                            )}

                            {error && <ErrorBanner message={error} />}

                            <div className="flex gap-3 pt-2">
                                <button onClick={() => setStep('configure')} className={cancelCls}>
                                    Back
                                </button>
                                {previewResult.idle_agents_found > 0 && (
                                    <button
                                        onClick={() => setStep('confirm')}
                                        className="flex-1 px-4 py-2.5 bg-rose-600 hover:bg-rose-700 text-white text-sm font-medium rounded-lg transition-colors shadow-sm flex items-center justify-center gap-2"
                                    >
                                        <Trash2 className="w-4 h-4" />
                                        Proceed to Liquidate
                                    </button>
                                )}
                                {previewResult.idle_agents_found === 0 && (
                                    <button onClick={onClose} className="flex-1 px-4 py-2.5 bg-gray-100 dark:bg-[#1e2535] text-gray-700 dark:text-gray-300 text-sm font-medium rounded-lg transition-colors">
                                        Close
                                    </button>
                                )}
                            </div>
                        </>
                    )}

                    {/* ═══════════════════════════════════════════════════════
                        STEP 3 — Confirm
                    ═══════════════════════════════════════════════════════ */}
                    {step === 'confirm' && previewResult && (
                        <>
                            <div className="flex items-start gap-3 px-4 py-3 rounded-xl bg-rose-50 dark:bg-rose-500/10 border border-rose-200 dark:border-rose-500/20">
                                <AlertCircle className="w-5 h-5 text-rose-600 dark:text-rose-400 flex-shrink-0 mt-0.5" />
                                <p className="text-sm text-rose-700 dark:text-rose-300">
                                    This will permanently liquidate{' '}
                                    <span className="font-bold">{previewResult.idle_agents_found}</span> idle agent{previewResult.idle_agents_found !== 1 ? 's' : ''}.
                                    This action <span className="font-bold">cannot be undone</span>.
                                </p>
                            </div>

                            {error && <ErrorBanner message={error} />}

                            <div className="flex gap-3 pt-2">
                                <button onClick={() => setStep('preview')} className={cancelCls}>
                                    Back
                                </button>
                                <button
                                    onClick={execute}
                                    disabled={isLoading}
                                    className="flex-1 px-4 py-2.5 bg-rose-600 hover:bg-rose-700 text-white text-sm font-medium rounded-lg transition-colors disabled:opacity-40 disabled:cursor-not-allowed shadow-sm flex items-center justify-center gap-2"
                                >
                                    {isLoading
                                        ? <><LoadingSpinner size="sm" /> Liquidating…</>
                                        : <><Trash2 className="w-4 h-4" /> Confirm Liquidation</>
                                    }
                                </button>
                            </div>
                        </>
                    )}

                    {/* ═══════════════════════════════════════════════════════
                        STEP 4 — Done
                    ═══════════════════════════════════════════════════════ */}
                    {step === 'done' && execResult && (
                        <>
                            <div className="flex flex-col items-center gap-2 py-2">
                                <div className="w-12 h-12 rounded-full bg-rose-100 dark:bg-rose-500/10 border border-rose-200 dark:border-rose-500/20 flex items-center justify-center">
                                    <CheckCircle2 className="w-6 h-6 text-rose-600 dark:text-rose-400" />
                                </div>
                                <p className="text-base font-semibold text-gray-900 dark:text-white">
                                    {execResult.liquidated_count} agent{execResult.liquidated_count !== 1 ? 's' : ''} liquidated
                                </p>
                            </div>

                            <div className="grid grid-cols-2 gap-2">
                                <StatTile label="Liquidated" value={execResult.liquidated_count} color="rose" />
                                <StatTile label="Skipped"    value={execResult.skipped_count}    color="slate" />
                            </div>

                            {execResult.skipped_count > 0 && (
                                <div className="rounded-xl border border-gray-200 dark:border-[#1e2535] p-3 bg-gray-50 dark:bg-[#0f1117] space-y-1">
                                    <p className="text-xs font-medium text-gray-500 dark:text-gray-400 flex items-center gap-1">
                                        <SkipForward className="w-3 h-3" /> Skipped agents
                                    </p>
                                    {execResult.skipped.map(s => (
                                        <p key={s.agentium_id} className="text-xs text-gray-600 dark:text-gray-400 font-mono">
                                            {s.agentium_id} — {s.reason}
                                        </p>
                                    ))}
                                </div>
                            )}

                            <button
                                onClick={onClose}
                                className="w-full px-4 py-2.5 bg-gray-100 dark:bg-[#1e2535] text-gray-700 dark:text-gray-300 text-sm font-medium rounded-lg hover:bg-gray-200 dark:hover:bg-[#2a3347] transition-colors"
                            >
                                Close
                            </button>
                        </>
                    )}
                </div>
            </div>
        </div>
    );
};

// ─── Mini helpers ─────────────────────────────────────────────────────────────

const cancelCls =
    'flex-1 px-4 py-2.5 border border-gray-200 dark:border-[#1e2535] text-gray-700 dark:text-gray-300 text-sm font-medium rounded-lg hover:bg-gray-50 dark:hover:bg-[#1e2535] transition-all duration-150';

function ErrorBanner({ message }: { message: string }) {
    return (
        <div className="flex items-center gap-2 text-sm text-red-700 dark:text-red-400 bg-red-50 dark:bg-red-500/10 border border-red-200 dark:border-red-500/20 px-4 py-3 rounded-xl">
            <AlertCircle className="w-4 h-4 flex-shrink-0" />
            {message}
        </div>
    );
}

function StatTile({ label, value, color }: { label: string; value: number; color: 'rose' | 'slate' }) {
    const palette = {
        rose:  'bg-rose-50 dark:bg-rose-500/10 border-rose-200 dark:border-rose-500/20 text-rose-700 dark:text-rose-300',
        slate: 'bg-slate-50 dark:bg-slate-700/30 border-slate-200 dark:border-slate-600 text-slate-700 dark:text-slate-300',
    }[color];
    return (
        <div className={`rounded-xl border p-3 ${palette}`}>
            <p className="text-xs opacity-70 mb-0.5">{label}</p>
            <p className="text-lg font-bold">{value}</p>
        </div>
    );
}
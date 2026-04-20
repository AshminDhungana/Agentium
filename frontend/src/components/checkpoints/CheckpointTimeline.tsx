import React, { useState, useEffect, useCallback, useMemo } from 'react';
import { showToast } from '@/hooks/useToast';
import { Download, Upload } from 'lucide-react';
import {
    Clock,
    GitBranch,
    RotateCcw,
    RefreshCw,
    ChevronDown,
    ChevronRight,
    CheckCircle2,
    Milestone,
    AlertCircle,
    Search,
    X,
    ArrowRightLeft,
} from 'lucide-react';
import { checkpointsService, Checkpoint, CheckpointPhase } from '../../services/checkpoints';
import { CheckpointDiffModal } from './CheckpointDiffModal';
import { LoadingSpinner } from '@/components/ui/LoadingSpinner';

// ─── Phase metadata ──────────────────────────────────────────────────────────

interface PhaseMeta {
    label: string;
    dotClass: string;
    badgeBg: string;
    badgeText: string;
    lineClass: string;
}

const PHASE_META: Record<CheckpointPhase, PhaseMeta> = {
    plan_approved: {
        label: 'Plan Approved',
        dotClass: 'bg-blue-500 dark:bg-blue-400',
        badgeBg: 'bg-blue-50 dark:bg-blue-500/15',
        badgeText: 'text-blue-700 dark:text-blue-300',
        lineClass: 'border-blue-300 dark:border-blue-500/40',
    },
    execution_complete: {
        label: 'Execution Complete',
        dotClass: 'bg-amber-500 dark:bg-amber-400',
        badgeBg: 'bg-amber-50 dark:bg-amber-500/15',
        badgeText: 'text-amber-700 dark:text-amber-300',
        lineClass: 'border-amber-300 dark:border-amber-500/40',
    },
    critique_passed: {
        label: 'Critique Passed',
        dotClass: 'bg-emerald-500 dark:bg-emerald-400',
        badgeBg: 'bg-emerald-50 dark:bg-emerald-500/15',
        badgeText: 'text-emerald-700 dark:text-emerald-300',
        lineClass: 'border-emerald-300 dark:border-emerald-500/40',
    },
    manual: {
        label: 'Manual Checkpoint',
        dotClass: 'bg-violet-500 dark:bg-violet-400',
        badgeBg: 'bg-violet-50 dark:bg-violet-500/15',
        badgeText: 'text-violet-700 dark:text-violet-300',
        lineClass: 'border-violet-300 dark:border-violet-500/40',
    },
};

function getPhaseMeta(phase: CheckpointPhase): PhaseMeta {
    return PHASE_META[phase] ?? {
        label: phase,
        dotClass: 'bg-slate-400',
        badgeBg: 'bg-slate-100 dark:bg-slate-700/50',
        badgeText: 'text-slate-600 dark:text-slate-300',
        lineClass: 'border-slate-300 dark:border-slate-600',
    };
}

function formatDate(dateStr: string): string {
    return new Date(dateStr).toLocaleString(undefined, {
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
    });
}

// ─── Props ───────────────────────────────────────────────────────────────────

interface CheckpointTimelineProps {
    taskId?: string;
    sessionId?: string;
    onRestore?: (checkpointId: string) => void;
    onBranch?: (checkpointId: string, branchName: string) => void;
}

// ─── Single checkpoint row ────────────────────────────────────────────────────

interface CheckpointRowProps {
    checkpoint: Checkpoint;
    isLast: boolean;
    onRestore: (id: string) => Promise<void>;
    onBranch: (id: string, name: string) => Promise<void>;
}

const CheckpointRow: React.FC<CheckpointRowProps> = ({
    checkpoint,
    isLast,
    onRestore,
    onBranch,
}) => {
    const [isExpanded, setIsExpanded] = useState(false);
    const [showBranchInput, setShowBranchInput] = useState(false);
    const [branchName, setBranchName] = useState('');
    const [isRestoring, setIsRestoring] = useState(false);
    const [isBranching, setIsBranching] = useState(false);
    const [isInspectorOpen, setIsInspectorOpen] = useState(false);
    const [isExporting, setIsExporting] = useState(false);

    const meta = getPhaseMeta(checkpoint.phase);

    const handleRestore = async (e: React.MouseEvent) => {
        e.stopPropagation();
        setIsRestoring(true);
        try {
            await onRestore(checkpoint.id);
        } finally {
            setIsRestoring(false);
        }
    };

    const handleExport = async (e: React.MouseEvent) => {
        e.stopPropagation();
        setIsExporting(true);
        try {
            const blob = await checkpointsService.exportCheckpoint(checkpoint.id);
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `checkpoint-${checkpoint.id}-${checkpoint.branch_name || 'main'}.json`;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            window.URL.revokeObjectURL(url);
            showToast.success('Checkpoint exported successfully');
        } catch (err: any) {
            showToast.error(err?.response?.data?.detail || 'Failed to export checkpoint');
        } finally {
            setIsExporting(false);
        }
    };

    const handleBranch = async (e: React.MouseEvent) => {
        e.stopPropagation();
        if (!branchName.trim()) {
            showToast.error('Please enter a branch name');
            return;
        }
        setIsBranching(true);
        try {
            await onBranch(checkpoint.id, branchName.trim());
            setBranchName('');
            setShowBranchInput(false);
        } finally {
            setIsBranching(false);
        }
    };

    const stateJson = JSON.stringify(checkpoint.task_state_snapshot, null, 2);
    const hasState = stateJson && stateJson !== '{}' && stateJson !== 'null';

    return (
        <div className="relative flex gap-4">
            {/* Timeline spine */}
            <div className="flex flex-col items-center flex-shrink-0 w-6">
                {/* Dot */}
                <div className={`w-3 h-3 rounded-full ring-2 ring-white dark:ring-[#161b27] mt-1 flex-shrink-0 ${meta.dotClass}`} />
                {/* Vertical line */}
                {!isLast && (
                    <div className={`flex-1 w-px border-l-2 border-dashed mt-1 ${meta.lineClass}`} />
                )}
            </div>

            {/* Card */}
            <div className="flex-1 pb-6">
                <div
                    className={`rounded-xl border transition-all duration-150 cursor-pointer
                        ${isExpanded
                            ? 'border-slate-300 dark:border-[#2a3347] bg-white dark:bg-[#161b27] shadow-sm'
                            : 'border-slate-200 dark:border-[#1e2535] bg-white dark:bg-[#161b27] hover:border-slate-300 dark:hover:border-[#2a3347] hover:shadow-sm'
                        }`}
                    onClick={() => setIsExpanded(x => !x)}
                >
                    {/* Row header */}
                    <div className="flex items-start justify-between gap-3 px-4 py-3">
                        <div className="flex-1 min-w-0">
                            <div className="flex items-center gap-2 flex-wrap mb-1">
                                {/* Phase badge */}
                                <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium ${meta.badgeBg} ${meta.badgeText}`}>
                                    <CheckCircle2 className="w-3 h-3" />
                                    {meta.label}
                                </span>
                                {/* Branch name */}
                                {checkpoint.branch_name && checkpoint.branch_name !== 'main' && (
                                    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-slate-100 dark:bg-slate-700/50 text-slate-600 dark:text-slate-300">
                                        <GitBranch className="w-3 h-3" />
                                        {checkpoint.branch_name}
                                    </span>
                                )}
                            </div>

                            {/* Agent + date */}
                            <div className="flex items-center gap-2 text-xs text-slate-500 dark:text-slate-400">
                                <Milestone className="w-3 h-3 flex-shrink-0" />
                                <span className="font-mono truncate">{checkpoint.agentium_id}</span>
                                <span className="text-slate-300 dark:text-slate-600">·</span>
                                <Clock className="w-3 h-3 flex-shrink-0" />
                                <span>{formatDate(checkpoint.created_at)}</span>
                            </div>
                        </div>

                        {/* Expand chevron */}
                        <div className="flex-shrink-0 mt-0.5 text-slate-400 dark:text-slate-500">
                            {isExpanded
                                ? <ChevronDown className="w-4 h-4" />
                                : <ChevronRight className="w-4 h-4" />
                            }
                        </div>
                    </div>

                    {/* Expanded detail */}
                    {isExpanded && (
                        <div
                            className="px-4 pb-4 border-t border-slate-100 dark:border-[#1e2535] pt-4 space-y-4"
                            onClick={e => e.stopPropagation()}
                        >
                            {/* Task state preview */}
                            {hasState && (
                                <div>
                                    <p className="text-xs font-semibold text-slate-500 dark:text-slate-400 uppercase tracking-widest mb-2">
                                        Task State Snapshot
                                    </p>
                                    <pre className="text-xs font-mono bg-slate-50 dark:bg-[#0f1117] border border-slate-200 dark:border-[#1e2535] rounded-lg p-3 max-h-40 overflow-auto text-slate-700 dark:text-slate-300 whitespace-pre-wrap break-all">
                                        {stateJson}
                                    </pre>
                                </div>
                            )}

                            {/* Actions */}
                            <div className="flex flex-wrap gap-2">
                                {/* Inspect State */}
                                <button
                                    onClick={(e) => { e.stopPropagation(); setIsInspectorOpen(true); }}
                                    className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium
                                        bg-slate-50 dark:bg-slate-800/50 text-slate-700 dark:text-slate-300
                                        border border-slate-200 dark:border-slate-700
                                        hover:bg-slate-100 dark:hover:bg-slate-800
                                        transition-colors duration-150"
                                >
                                    <Search className="w-3 h-3" />
                                    Inspect State
                                </button>
                                <button
                                    onClick={handleExport}
                                    disabled={isExporting}
                                    className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium
                                        bg-emerald-50 dark:bg-emerald-500/15 text-emerald-700 dark:text-emerald-300
                                        border border-emerald-200 dark:border-emerald-500/25
                                        hover:bg-emerald-100 dark:hover:bg-emerald-500/25
                                        disabled:opacity-50 transition-colors duration-150"
                                >
                                    {isExporting ? <LoadingSpinner size="xs" /> : <Download className="w-3 h-3" />}
                                    {isExporting ? 'Exporting…' : 'Export'}
                                </button>
                                {/* Restore */}
                                <button
                                    onClick={handleRestore}
                                    disabled={isRestoring}
                                    className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium
                                        bg-blue-50 dark:bg-blue-500/15 text-blue-700 dark:text-blue-300
                                        border border-blue-200 dark:border-blue-500/25
                                        hover:bg-blue-100 dark:hover:bg-blue-500/25
                                        disabled:opacity-50 transition-colors duration-150"
                                >
                                    {isRestoring
                                        ? <LoadingSpinner size="xs" />
                                        : <RotateCcw className="w-3 h-3" />
                                    }
                                    {isRestoring ? 'Restoring…' : 'Restore'}
                                </button>

                                {/* Branch toggle */}
                                <button
                                    onClick={() => setShowBranchInput(x => !x)}
                                    className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium
                                        bg-violet-50 dark:bg-violet-500/15 text-violet-700 dark:text-violet-300
                                        border border-violet-200 dark:border-violet-500/25
                                        hover:bg-violet-100 dark:hover:bg-violet-500/25
                                        transition-colors duration-150"
                                >
                                    <GitBranch className="w-3 h-3" />
                                    {showBranchInput ? 'Cancel Branch' : 'Branch from here'}
                                </button>
                            </div>

                            {/* Branch form */}
                            {showBranchInput && (
                                <div className="flex gap-2 items-center">
                                    <input
                                        type="text"
                                        placeholder="Branch name (e.g. alt-approach-v2)…"
                                        value={branchName}
                                        onChange={e => setBranchName(e.target.value)}
                                        onKeyDown={e => { if (e.key === 'Enter') handleBranch(e as any); }}
                                        className="flex-1 px-3 py-1.5 text-xs rounded-lg border border-slate-200 dark:border-[#1e2535]
                                            bg-white dark:bg-[#0f1117] text-slate-800 dark:text-slate-100
                                            placeholder-slate-400 dark:placeholder-slate-600
                                            focus:outline-none focus:ring-2 focus:ring-violet-500/40 focus:border-violet-500
                                            transition-colors duration-150"
                                    />
                                    <button
                                        onClick={handleBranch}
                                        disabled={isBranching || !branchName.trim()}
                                        className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium
                                            bg-violet-600 hover:bg-violet-700 text-white
                                            disabled:opacity-40 disabled:cursor-not-allowed
                                            transition-colors duration-150"
                                    >
                                        {isBranching
                                            ? <LoadingSpinner size="xs" />
                                            : <GitBranch className="w-3 h-3" />
                                        }
                                        {isBranching ? 'Creating…' : 'Create'}
                                    </button>
                                </div>
                            )}
                        </div>
                    )}
                </div>
            </div>

            {/* Inpsector Modal */}
            {isInspectorOpen && (
                <div
                    className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm p-4"
                    onClick={(e) => { e.stopPropagation(); setIsInspectorOpen(false); }}
                >
                    <div
                        className="bg-white dark:bg-[#161b27] border border-slate-200 dark:border-[#1e2535] rounded-xl shadow-2xl w-full max-w-4xl max-h-[90vh] flex flex-col"
                        onClick={(e) => e.stopPropagation()}
                    >
                        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-100 dark:border-[#1e2535]">
                            <div>
                                <h3 className="text-lg font-semibold text-slate-800 dark:text-slate-100">
                                    State Inspector
                                </h3>
                                <p className="text-sm text-slate-500 dark:text-slate-400">
                                    Checkpoint ID: {checkpoint.id}
                                </p>
                            </div>
                            <button
                                onClick={(e) => { e.stopPropagation(); setIsInspectorOpen(false); }}
                                className="p-2 -mr-2 text-slate-400 hover:bg-slate-100 hover:text-slate-600 dark:hover:bg-[#1e2535] dark:hover:text-slate-300 rounded-lg transition-colors"
                            >
                                <X className="w-5 h-5" />
                            </button>
                        </div>
                        <div className="flex-1 overflow-auto p-6 bg-slate-50 dark:bg-[#0f1117] rounded-b-xl">
                            <pre className="text-xs font-mono text-slate-700 dark:text-slate-300 whitespace-pre-wrap break-words">
                                {stateJson}
                            </pre>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
};

// ─── Main component ───────────────────────────────────────────────────────────

export const CheckpointTimeline: React.FC<CheckpointTimelineProps> = ({
    taskId,
    sessionId,
    onRestore,
    onBranch,
}) => {
    const [checkpoints, setCheckpoints] = useState<Checkpoint[]>([]);
    const [isLoading, setIsLoading] = useState(true);
    const [isRefreshing, setIsRefreshing] = useState(false);
    const [error, setError] = useState<string | null>(null);

    // Filter branches
    const availableBranches = useMemo(() => {
        const branches = new Set<string>();
        for (const cp of checkpoints) {
            if (cp.branch_name) branches.add(cp.branch_name);
        }
        return Array.from(branches).sort();
    }, [checkpoints]);

    const [isCompareModalOpen, setIsCompareModalOpen] = useState(false);
    const [compareLeft, setCompareLeft] = useState<string>('');
    const [compareRight, setCompareRight] = useState<string>('');
    const [showDiff, setShowDiff] = useState(false);

    const load = useCallback(async (silent = false) => {
        if (silent) setIsRefreshing(true);
        else setIsLoading(true);
        setError(null);

        try {
            const data = await checkpointsService.getCheckpoints({ task_id: taskId, session_id: sessionId });
            // Sort oldest first so the timeline reads top-to-bottom chronologically
            setCheckpoints([...data].sort((a, b) =>
                new Date(a.created_at).getTime() - new Date(b.created_at).getTime()
            ));
        } catch (err: any) {
            const msg = err?.response?.data?.detail || err?.message || 'Failed to load checkpoints';
            setError(msg);
            if (!silent) showToast.error(msg);
        } finally {
            setIsLoading(false);
            setIsRefreshing(false);
        }
    }, [taskId, sessionId]);

    useEffect(() => { load(); }, [load]);

    const handleRestore = async (checkpointId: string) => {
        try {
            await checkpointsService.resumeFromCheckpoint(checkpointId);
            showToast.success('Task restored to checkpoint');
            onRestore?.(checkpointId);
            load(true);
        } catch (err: any) {
            showToast.error(err?.response?.data?.detail || 'Failed to restore checkpoint');
            throw err;
        }
    };

    const handleBranch = async (checkpointId: string, name: string) => {
        try {
            await checkpointsService.branchFromCheckpoint(checkpointId, name);
            showToast.success(`Branch "${name}" created`);
            onBranch?.(checkpointId, name);
            load(true);
        } catch (err: any) {
            showToast.error(err?.response?.data?.detail || 'Failed to create branch');
            throw err;
        }
    };

    const openCompareSelector = () => {
        if (availableBranches.length < 2) {
            showToast.error('You need at least 2 branches to compare.');
            return;
        }
        setCompareLeft(availableBranches[0]);
        setCompareRight(availableBranches[1]);
        setIsCompareModalOpen(true);
    };

    // ── Loading state ─────────────────────────────────────────────────────────
    if (isLoading) {
        return (
            <div className="flex flex-col items-center justify-center py-12 gap-3 text-slate-400 dark:text-slate-500">
                <LoadingSpinner size="md" />
                <span className="text-sm">Loading checkpoints…</span>
            </div>
        );
    }

    // ── Error state ───────────────────────────────────────────────────────────
    if (error) {
        return (
            <div className="flex flex-col items-center justify-center py-12 gap-3">
                <AlertCircle className="w-8 h-8 text-red-400 dark:text-red-500 opacity-60" />
                <p className="text-sm text-red-600 dark:text-red-400">{error}</p>
                <button
                    onClick={() => load()}
                    className="text-xs text-blue-600 dark:text-blue-400 underline hover:no-underline"
                >
                    Try again
                </button>
            </div>
        );
    }

    // ── Empty state ───────────────────────────────────────────────────────────
    if (checkpoints.length === 0) {
        return (
            <div className="flex flex-col items-center justify-center py-12 gap-3 text-slate-400 dark:text-slate-500">
                <Milestone className="w-8 h-8 opacity-40" />
                <p className="text-sm">No checkpoints recorded yet.</p>
                <p className="text-xs text-slate-400 dark:text-slate-600">
                    Checkpoints are created automatically at plan, execution, and critique phases.
                </p>
                <button
                    onClick={() => load(true)}
                    className="mt-1 text-xs text-blue-600 dark:text-blue-400 underline hover:no-underline"
                >
                    Refresh
                </button>
            </div>
        );
    }

    // ── Timeline ──────────────────────────────────────────────────────────────
    return (
        <div className="space-y-0">
            {/* Header */}
            <div className="flex items-center justify-between mb-5">
                <div>
                    <h3 className="text-sm font-semibold text-slate-800 dark:text-slate-100">
                        Execution Timeline
                    </h3>
                    <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">
                        {checkpoints.length} checkpoint{checkpoints.length !== 1 ? 's' : ''} recorded
                    </p>
                </div>
                <div className="flex items-center gap-2">
                    <button
                        onClick={openCompareSelector}
                        className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium
                            bg-violet-50 dark:bg-violet-500/15 text-violet-700 dark:text-violet-300
                            border border-violet-200 dark:border-violet-500/25
                            hover:bg-violet-100 dark:hover:bg-violet-500/25
                            transition-colors duration-150"
                    >
                        <ArrowRightLeft className="w-3 h-3" />
                        Compare
                    </button>
                    <button
                        onClick={() => load(true)}
                        disabled={isRefreshing}
                        className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium
                            border border-slate-200 dark:border-[#1e2535]
                            bg-white dark:bg-[#161b27] text-slate-600 dark:text-slate-300
                            hover:bg-slate-50 dark:hover:bg-[#1e2535]
                            disabled:opacity-50 transition-colors duration-150"
                    >
                        <RefreshCw className={`w-3 h-3 ${isRefreshing ? 'animate-spin' : ''}`} />
                        Refresh
                    </button>
                </div>
            </div>

            {/* Branch legend */}
            <div className="flex flex-wrap gap-2 mb-5">
                {Object.entries(PHASE_META).map(([phase, meta]) => (
                    <span
                        key={phase}
                        className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-xs ${meta.badgeBg} ${meta.badgeText}`}
                    >
                        <span className={`w-2 h-2 rounded-full ${meta.dotClass}`} />
                        {meta.label}
                    </span>
                ))}
            </div>

            {/* Checkpoint rows */}
            <div>
                {checkpoints.map((cp, idx) => (
                    <CheckpointRow
                        key={cp.id}
                        checkpoint={cp}
                        isLast={idx === checkpoints.length - 1}
                        onRestore={handleRestore}
                        onBranch={handleBranch}
                    />
                ))}
            </div>

            {/* Compare Selector Modal */}
            {isCompareModalOpen && !showDiff && (
                <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm p-4" onClick={() => setIsCompareModalOpen(false)}>
                    <div className="bg-white dark:bg-[#161b27] border border-slate-200 dark:border-[#1e2535] rounded-xl shadow-2xl p-6 w-full max-w-sm" onClick={e => e.stopPropagation()}>
                        <h3 className="text-lg font-bold text-slate-900 dark:text-white mb-4">Compare Branches</h3>
                        
                        <div className="space-y-4">
                            <div>
                                <label className="block text-xs font-medium text-slate-700 dark:text-slate-300 mb-1">Left Branch</label>
                                <select 
                                    className="w-full px-3 py-2 text-sm rounded bg-slate-50 border border-slate-200 dark:bg-[#0f1117] dark:border-[#1e2535] dark:text-white"
                                    value={compareLeft}
                                    onChange={(e) => setCompareLeft(e.target.value)}
                                >
                                    {availableBranches.map(b => (
                                        <option key={b} value={b}>{b}</option>
                                    ))}
                                </select>
                            </div>

                            <div className="flex justify-center text-slate-400">
                                <ArrowRightLeft className="w-4 h-4" />
                            </div>

                            <div>
                                <label className="block text-xs font-medium text-slate-700 dark:text-slate-300 mb-1">Right Branch</label>
                                <select 
                                    className="w-full px-3 py-2 text-sm rounded bg-slate-50 border border-slate-200 dark:bg-[#0f1117] dark:border-[#1e2535] dark:text-white"
                                    value={compareRight}
                                    onChange={(e) => setCompareRight(e.target.value)}
                                >
                                    {availableBranches.map(b => (
                                        <option key={b} value={b}>{b}</option>
                                    ))}
                                </select>
                            </div>
                        </div>

                        <div className="mt-6 flex gap-2">
                            <button 
                                onClick={() => setIsCompareModalOpen(false)}
                                className="flex-1 px-4 py-2 text-sm border border-slate-200 dark:border-[#1e2535] rounded-lg text-slate-700 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-[#1e2535] transition-colors"
                            >
                                Cancel
                            </button>
                            <button 
                                onClick={() => setShowDiff(true)}
                                disabled={compareLeft === compareRight}
                                className="flex-1 px-4 py-2 text-sm bg-violet-600 text-white rounded-lg hover:bg-violet-700 disabled:opacity-50 transition-colors"
                            >
                                View Diff
                            </button>
                        </div>
                    </div>
                </div>
            )}

            {/* Diff Modal */}
            {showDiff && (
                <CheckpointDiffModal
                    taskId={taskId}
                    leftBranch={compareLeft}
                    rightBranch={compareRight}
                    onClose={() => {
                        setShowDiff(false);
                        setIsCompareModalOpen(false);
                    }}
                />
            )}
        </div>
    );
};

export default CheckpointTimeline;
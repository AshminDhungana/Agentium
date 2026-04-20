/**
 * BranchDiffView — Phase 6 + Phase 7
 *
 * Side-by-side branch comparison UI.
 * Visualises diffs for task state, agent states, and artifacts
 * returned by GET /api/v1/checkpoints/compare.
 */

import React, { useState, useCallback } from 'react';
import { showToast } from '@/hooks/useToast';
import {
    GitBranch,
    GitCompareArrows,
    RefreshCw,
    AlertCircle,
    ChevronDown,
    ChevronRight,
    Plus,
    Minus,
    ArrowLeftRight,
    Equal,
    Bot,
    PackageOpen,
    FileText,
    Clock,
    Hash,
} from 'lucide-react';
import {
    checkpointsService,
    BranchCompareResult,
    FieldDiff,
    AgentStateDiff,
    ArtifactDiff,
    DiffStatus,
} from '../../services/checkpoints';
import { LoadingSpinner } from '@/components/ui/LoadingSpinner';

// ─── Diff status config ───────────────────────────────────────────────────────

interface StatusCfg {
    icon: React.ReactNode;
    rowBg: string;
    leftBg: string;
    rightBg: string;
    badge: string;
    label: string;
}

function getStatusCfg(status: DiffStatus): StatusCfg {
    switch (status) {
        case 'added':
            return {
                icon: <Plus className="w-3 h-3" />,
                rowBg: 'bg-emerald-50/60 dark:bg-emerald-500/8',
                leftBg: 'bg-slate-50 dark:bg-[#0f1117]',
                rightBg: 'bg-emerald-50 dark:bg-emerald-500/10',
                badge: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-500/20 dark:text-emerald-300',
                label: 'Added',
            };
        case 'removed':
            return {
                icon: <Minus className="w-3 h-3" />,
                rowBg: 'bg-red-50/60 dark:bg-red-500/8',
                leftBg: 'bg-red-50 dark:bg-red-500/10',
                rightBg: 'bg-slate-50 dark:bg-[#0f1117]',
                badge: 'bg-red-100 text-red-700 dark:bg-red-500/20 dark:text-red-300',
                label: 'Removed',
            };
        case 'changed':
            return {
                icon: <ArrowLeftRight className="w-3 h-3" />,
                rowBg: 'bg-amber-50/60 dark:bg-amber-500/8',
                leftBg: 'bg-amber-50 dark:bg-amber-500/10',
                rightBg: 'bg-amber-50 dark:bg-amber-500/10',
                badge: 'bg-amber-100 text-amber-700 dark:bg-amber-500/20 dark:text-amber-300',
                label: 'Changed',
            };
        default:
            return {
                icon: <Equal className="w-3 h-3" />,
                rowBg: '',
                leftBg: 'bg-slate-50 dark:bg-[#0f1117]',
                rightBg: 'bg-slate-50 dark:bg-[#0f1117]',
                badge: 'bg-slate-100 text-slate-500 dark:bg-slate-700/50 dark:text-slate-400',
                label: 'Unchanged',
            };
    }
}

// ─── Serialise any value concisely ───────────────────────────────────────────

function renderValue(v: any): string {
    if (v === null || v === undefined) return '—';
    if (typeof v === 'string') return v;
    if (typeof v === 'number' || typeof v === 'boolean') return String(v);
    return JSON.stringify(v, null, 2);
}

// ─── Single diff row ──────────────────────────────────────────────────────────

const DiffRow: React.FC<{ diff: FieldDiff; hideUnchanged: boolean }> = ({ diff, hideUnchanged }) => {
    if (hideUnchanged && diff.status === 'unchanged') return null;
    const cfg = getStatusCfg(diff.status);
    const leftVal = renderValue(diff.left);
    const rightVal = renderValue(diff.right);
    const isMultiline = leftVal.includes('\n') || rightVal.includes('\n');

    return (
        <div className={`border-b border-slate-100 dark:border-[#1e2535] last:border-0 ${cfg.rowBg}`}>
            {/* Key header */}
            <div className="flex items-center gap-2 px-3 py-1.5 border-b border-slate-100 dark:border-[#1e2535]/60">
                <span className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-medium ${cfg.badge}`}>
                    {cfg.icon}
                    {cfg.label}
                </span>
                <code className="text-xs font-mono text-slate-700 dark:text-slate-300 font-semibold">{diff.key}</code>
            </div>
            {/* Side-by-side values */}
            <div className={`grid ${isMultiline ? 'grid-cols-1' : 'grid-cols-2'} divide-x divide-slate-200 dark:divide-[#1e2535]`}>
                <div className={`px-3 py-2 ${cfg.leftBg}`}>
                    <pre className="text-xs font-mono text-slate-600 dark:text-slate-400 whitespace-pre-wrap break-all leading-relaxed">
                        {leftVal}
                    </pre>
                </div>
                {!isMultiline && (
                    <div className={`px-3 py-2 ${cfg.rightBg}`}>
                        <pre className="text-xs font-mono text-slate-600 dark:text-slate-400 whitespace-pre-wrap break-all leading-relaxed">
                            {rightVal}
                        </pre>
                    </div>
                )}
            </div>
        </div>
    );
};

// ─── Collapsible section ──────────────────────────────────────────────────────

const Section: React.FC<{
    icon: React.ReactNode;
    title: string;
    subtitle?: string;
    badge?: React.ReactNode;
    defaultOpen?: boolean;
    children: React.ReactNode;
}> = ({ icon, title, subtitle, badge, defaultOpen = true, children }) => {
    const [open, setOpen] = useState(defaultOpen);
    return (
        <div className="rounded-xl border border-slate-200 dark:border-[#1e2535] bg-white dark:bg-[#161b27] overflow-hidden">
            <button
                onClick={() => setOpen(x => !x)}
                className="w-full flex items-center gap-3 px-5 py-4 hover:bg-slate-50 dark:hover:bg-[#1e2535]/50 transition-colors text-left"
            >
                <span className="text-slate-500 dark:text-slate-400">{icon}</span>
                <div className="flex-1 min-w-0">
                    <p className="text-sm font-semibold text-slate-800 dark:text-slate-100">{title}</p>
                    {subtitle && <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">{subtitle}</p>}
                </div>
                {badge}
                {open ? <ChevronDown className="w-4 h-4 text-slate-400 flex-shrink-0" /> : <ChevronRight className="w-4 h-4 text-slate-400 flex-shrink-0" />}
            </button>
            {open && (
                <div className="border-t border-slate-100 dark:border-[#1e2535]">
                    {children}
                </div>
            )}
        </div>
    );
};

// ─── Agent state diff block ───────────────────────────────────────────────────

const AgentDiffBlock: React.FC<{ agent: AgentStateDiff; hideUnchanged: boolean }> = ({ agent, hideUnchanged }) => {
    const [open, setOpen] = useState(agent.status !== 'unchanged');
    const cfg = getStatusCfg(agent.status);
    const visibleDiffs = hideUnchanged ? agent.diffs.filter(d => d.status !== 'unchanged') : agent.diffs;

    if (hideUnchanged && agent.status === 'unchanged') return null;

    return (
        <div className="border-b border-slate-100 dark:border-[#1e2535] last:border-0">
            <button
                onClick={() => setOpen(x => !x)}
                className="w-full flex items-center gap-2.5 px-4 py-3 hover:bg-slate-50 dark:hover:bg-[#1e2535]/40 transition-colors text-left"
            >
                <Bot className="w-3.5 h-3.5 text-slate-400 flex-shrink-0" />
                <code className="text-xs font-mono text-slate-700 dark:text-slate-300 flex-1 truncate">{agent.agent_id}</code>
                <span className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-medium ${cfg.badge}`}>
                    {cfg.icon}
                    {cfg.label}
                </span>
                <span className="text-xs text-slate-400">{visibleDiffs.length} field{visibleDiffs.length !== 1 ? 's' : ''}</span>
                {open ? <ChevronDown className="w-3.5 h-3.5 text-slate-400" /> : <ChevronRight className="w-3.5 h-3.5 text-slate-400" />}
            </button>
            {open && visibleDiffs.length > 0 && (
                <div className="border-t border-slate-100 dark:border-[#1e2535] mx-4 mb-3 mt-0 rounded-lg overflow-hidden border border-slate-200 dark:border-[#1e2535]">
                    {visibleDiffs.map(d => (
                        <DiffRow key={d.key} diff={d} hideUnchanged={false} />
                    ))}
                </div>
            )}
            {open && visibleDiffs.length === 0 && (
                <p className="text-xs text-slate-400 dark:text-slate-600 px-4 pb-3">No differences.</p>
            )}
        </div>
    );
};

// ─── Artifact diff block ──────────────────────────────────────────────────────

const ArtifactDiffBlock: React.FC<{ artifact: ArtifactDiff; hideUnchanged: boolean }> = ({ artifact, hideUnchanged }) => {
    if (hideUnchanged && artifact.status === 'unchanged') return null;
    const [open, setOpen] = useState(artifact.status !== 'unchanged');
    const cfg = getStatusCfg(artifact.status);
    const leftVal = renderValue(artifact.left);
    const rightVal = renderValue(artifact.right);

    return (
        <div className="border-b border-slate-100 dark:border-[#1e2535] last:border-0">
            <button
                onClick={() => setOpen(x => !x)}
                className="w-full flex items-center gap-2.5 px-4 py-3 hover:bg-slate-50 dark:hover:bg-[#1e2535]/40 transition-colors text-left"
            >
                <PackageOpen className="w-3.5 h-3.5 text-slate-400 flex-shrink-0" />
                <code className="text-xs font-mono text-slate-700 dark:text-slate-300 flex-1 truncate">{artifact.key}</code>
                <span className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-medium ${cfg.badge}`}>
                    {cfg.icon}
                    {cfg.label}
                </span>
                {open ? <ChevronDown className="w-3.5 h-3.5 text-slate-400" /> : <ChevronRight className="w-3.5 h-3.5 text-slate-400" />}
            </button>
            {open && (
                <div className="grid grid-cols-2 divide-x divide-slate-200 dark:divide-[#1e2535] border-t border-slate-100 dark:border-[#1e2535]">
                    <div className={`px-4 py-3 ${cfg.leftBg}`}>
                        <pre className="text-xs font-mono text-slate-600 dark:text-slate-400 whitespace-pre-wrap break-all leading-relaxed max-h-48 overflow-auto">
                            {leftVal}
                        </pre>
                    </div>
                    <div className={`px-4 py-3 ${cfg.rightBg}`}>
                        <pre className="text-xs font-mono text-slate-600 dark:text-slate-400 whitespace-pre-wrap break-all leading-relaxed max-h-48 overflow-auto">
                            {rightVal}
                        </pre>
                    </div>
                </div>
            )}
        </div>
    );
};

// ─── Summary pill ─────────────────────────────────────────────────────────────

const SummaryBadge: React.FC<{ count: number; status: DiffStatus }> = ({ count, status }) => {
    if (count === 0) return null;
    const cfg = getStatusCfg(status);
    return (
        <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium ${cfg.badge}`}>
            {cfg.icon}
            {count} {cfg.label}
        </span>
    );
};

// ─── Branch input bar ─────────────────────────────────────────────────────────

interface BranchInputBarProps {
    leftBranch: string;
    rightBranch: string;
    taskId: string;
    onLeftChange: (v: string) => void;
    onRightChange: (v: string) => void;
    onTaskIdChange: (v: string) => void;
    onCompare: () => void;
    isLoading: boolean;
}

const BranchInputBar: React.FC<BranchInputBarProps> = ({
    leftBranch, rightBranch, taskId,
    onLeftChange, onRightChange, onTaskIdChange,
    onCompare, isLoading,
}) => {
    const inputCls = `
        flex-1 min-w-0 px-3 py-2 text-sm rounded-lg
        border border-slate-200 dark:border-[#1e2535]
        bg-white dark:bg-[#0f1117]
        text-slate-800 dark:text-slate-100
        placeholder-slate-400 dark:placeholder-slate-600
        focus:outline-none focus:ring-2 focus:ring-blue-500/40 focus:border-blue-500
        transition-colors duration-150
    `;

    return (
        <div className="rounded-xl border border-slate-200 dark:border-[#1e2535] bg-white dark:bg-[#161b27] p-4">
            <div className="flex flex-wrap items-center gap-3">
                {/* Left branch */}
                <div className="flex items-center gap-2 flex-1 min-w-[140px]">
                    <GitBranch className="w-4 h-4 text-slate-400 flex-shrink-0" />
                    <input
                        type="text"
                        placeholder="Base branch (e.g. main)"
                        value={leftBranch}
                        onChange={e => onLeftChange(e.target.value)}
                        className={inputCls}
                    />
                </div>

                {/* Swap arrow */}
                <GitCompareArrows className="w-5 h-5 text-slate-400 flex-shrink-0" />

                {/* Right branch */}
                <div className="flex items-center gap-2 flex-1 min-w-[140px]">
                    <GitBranch className="w-4 h-4 text-slate-400 flex-shrink-0" />
                    <input
                        type="text"
                        placeholder="Compare branch"
                        value={rightBranch}
                        onChange={e => onRightChange(e.target.value)}
                        className={inputCls}
                    />
                </div>

                {/* Optional task filter */}
                <div className="flex items-center gap-2 min-w-[160px]">
                    <Hash className="w-4 h-4 text-slate-400 flex-shrink-0" />
                    <input
                        type="text"
                        placeholder="Task ID (optional)"
                        value={taskId}
                        onChange={e => onTaskIdChange(e.target.value)}
                        className={inputCls}
                    />
                </div>

                {/* Compare button */}
                <button
                    onClick={onCompare}
                    disabled={isLoading || !leftBranch.trim() || !rightBranch.trim()}
                    className="
                        inline-flex items-center gap-2 px-5 py-2 rounded-lg text-sm font-medium
                        bg-blue-600 hover:bg-blue-700 text-white
                        disabled:opacity-40 disabled:cursor-not-allowed
                        transition-colors duration-150
                    "
                >
                    {isLoading ? <LoadingSpinner size="sm" /> : <GitCompareArrows className="w-4 h-4" />}
                    {isLoading ? 'Comparing…' : 'Compare'}
                </button>
            </div>
        </div>
    );
};

// ─── Props ────────────────────────────────────────────────────────────────────

export interface BranchDiffViewProps {
    /** Pre-fill the left branch name */
    defaultLeftBranch?: string;
    /** Pre-fill the right branch name */
    defaultRightBranch?: string;
    /** Narrow comparison to a specific task */
    defaultTaskId?: string;
}

// ─── Main component ───────────────────────────────────────────────────────────

export const BranchDiffView: React.FC<BranchDiffViewProps> = ({
    defaultLeftBranch = 'main',
    defaultRightBranch = '',
    defaultTaskId = '',
}) => {
    const [leftBranch, setLeftBranch] = useState(defaultLeftBranch);
    const [rightBranch, setRightBranch] = useState(defaultRightBranch);
    const [taskId, setTaskId] = useState(defaultTaskId);
    const [isLoading, setIsLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [result, setResult] = useState<BranchCompareResult | null>(null);
    const [hideUnchanged, setHideUnchanged] = useState(true);

    const compare = useCallback(async () => {
        if (!leftBranch.trim() || !rightBranch.trim()) return;
        setIsLoading(true);
        setError(null);
        try {
            const data = await checkpointsService.compareBranches(
                leftBranch.trim(),
                rightBranch.trim(),
                taskId.trim() || undefined,
            );
            setResult(data);
        } catch (err: any) {
            const msg = err?.response?.data?.detail || err?.message || 'Comparison failed';
            setError(msg);
            showToast.error(msg);
        } finally {
            setIsLoading(false);
        }
    }, [leftBranch, rightBranch, taskId]);

    const totalChanges = result
        ? result.summary.added + result.summary.removed + result.summary.changed
        : 0;

    return (
        <div className="space-y-5">
            {/* ── Header ──────────────────────────────────────────────────────── */}
            <div className="flex items-start justify-between gap-4">
                <div>
                    <h2 className="text-lg font-semibold text-slate-800 dark:text-slate-100 flex items-center gap-2">
                        <GitCompareArrows className="w-5 h-5 text-blue-500" />
                        Branch Diff
                    </h2>
                    <p className="text-sm text-slate-500 dark:text-slate-400 mt-0.5">
                        Side-by-side comparison of checkpoint state across branches
                    </p>
                </div>
            </div>

            {/* ── Input bar ───────────────────────────────────────────────────── */}
            <BranchInputBar
                leftBranch={leftBranch}
                rightBranch={rightBranch}
                taskId={taskId}
                onLeftChange={setLeftBranch}
                onRightChange={setRightBranch}
                onTaskIdChange={setTaskId}
                onCompare={compare}
                isLoading={isLoading}
            />

            {/* ── Error ───────────────────────────────────────────────────────── */}
            {error && (
                <div className="flex items-start gap-3 rounded-xl border border-red-200 dark:border-red-500/25 bg-red-50 dark:bg-red-500/8 px-4 py-3">
                    <AlertCircle className="w-4 h-4 text-red-500 mt-0.5 flex-shrink-0" />
                    <p className="text-sm text-red-700 dark:text-red-300">{error}</p>
                </div>
            )}

            {/* ── Results ─────────────────────────────────────────────────────── */}
            {result && (
                <div className="space-y-4">
                    {/* Comparison header */}
                    <div className="rounded-xl border border-slate-200 dark:border-[#1e2535] bg-white dark:bg-[#161b27] px-5 py-4">
                        <div className="flex flex-wrap items-center justify-between gap-4">
                            {/* Branch labels */}
                            <div className="flex items-center gap-3 text-sm">
                                <div className="flex items-center gap-1.5">
                                    <GitBranch className="w-3.5 h-3.5 text-slate-400" />
                                    <code className="font-mono font-semibold text-slate-700 dark:text-slate-200">{result.left_branch}</code>
                                    <span className="text-[10px] text-slate-400 dark:text-slate-500 flex items-center gap-1">
                                        <Clock className="w-3 h-3" />
                                        {new Date(result.left_created_at).toLocaleString()}
                                    </span>
                                </div>
                                <GitCompareArrows className="w-4 h-4 text-slate-400" />
                                <div className="flex items-center gap-1.5">
                                    <GitBranch className="w-3.5 h-3.5 text-slate-400" />
                                    <code className="font-mono font-semibold text-slate-700 dark:text-slate-200">{result.right_branch}</code>
                                    <span className="text-[10px] text-slate-400 dark:text-slate-500 flex items-center gap-1">
                                        <Clock className="w-3 h-3" />
                                        {new Date(result.right_created_at).toLocaleString()}
                                    </span>
                                </div>
                            </div>

                            {/* Summary pills */}
                            <div className="flex flex-wrap items-center gap-2">
                                <SummaryBadge count={result.summary.added} status="added" />
                                <SummaryBadge count={result.summary.removed} status="removed" />
                                <SummaryBadge count={result.summary.changed} status="changed" />
                                {totalChanges === 0 && (
                                    <span className="text-xs text-slate-500 dark:text-slate-400">Branches are identical</span>
                                )}
                            </div>
                        </div>

                        {/* Column headers for side-by-side */}
                        <div className="grid grid-cols-2 gap-px mt-4 rounded-lg overflow-hidden border border-slate-200 dark:border-[#1e2535]">
                            <div className="bg-slate-50 dark:bg-[#0f1117] px-4 py-2 text-xs font-semibold text-slate-500 dark:text-slate-400 uppercase tracking-wider flex items-center gap-1.5">
                                <span className="w-2 h-2 rounded-full bg-slate-400 dark:bg-slate-600 inline-block" />
                                {result.left_branch}
                            </div>
                            <div className="bg-slate-50 dark:bg-[#0f1117] px-4 py-2 text-xs font-semibold text-slate-500 dark:text-slate-400 uppercase tracking-wider flex items-center gap-1.5 border-l border-slate-200 dark:border-[#1e2535]">
                                <span className="w-2 h-2 rounded-full bg-blue-500 inline-block" />
                                {result.right_branch}
                            </div>
                        </div>
                    </div>

                    {/* Hide unchanged toggle */}
                    <div className="flex items-center justify-end gap-2">
                        <label className="flex items-center gap-2 text-xs text-slate-600 dark:text-slate-400 cursor-pointer select-none">
                            <div
                                onClick={() => setHideUnchanged(x => !x)}
                                className={`relative w-8 h-4 rounded-full transition-colors duration-200 ${
                                    hideUnchanged ? 'bg-blue-500' : 'bg-slate-300 dark:bg-slate-600'
                                }`}
                            >
                                <span className={`absolute top-0.5 w-3 h-3 bg-white rounded-full shadow transition-transform duration-200 ${
                                    hideUnchanged ? 'translate-x-4' : 'translate-x-0.5'
                                }`} />
                            </div>
                            Hide unchanged fields
                        </label>
                    </div>

                    {/* ── Task State Section ──────────────────────────────────── */}
                    <Section
                        icon={<FileText className="w-4 h-4" />}
                        title="Task State Snapshot"
                        subtitle={`${result.task_state_diffs.filter(d => d.status !== 'unchanged').length} of ${result.task_state_diffs.length} fields differ`}
                        badge={
                            <div className="flex gap-1.5 mr-2">
                                <SummaryBadge count={result.task_state_diffs.filter(d => d.status === 'added').length} status="added" />
                                <SummaryBadge count={result.task_state_diffs.filter(d => d.status === 'removed').length} status="removed" />
                                <SummaryBadge count={result.task_state_diffs.filter(d => d.status === 'changed').length} status="changed" />
                            </div>
                        }
                    >
                        {result.task_state_diffs.length === 0 ? (
                            <p className="text-xs text-slate-400 dark:text-slate-600 px-5 py-4">No task state recorded.</p>
                        ) : (
                            <div>
                                {result.task_state_diffs.map(d => (
                                    <DiffRow key={d.key} diff={d} hideUnchanged={hideUnchanged} />
                                ))}
                                {hideUnchanged && result.task_state_diffs.every(d => d.status === 'unchanged') && (
                                    <p className="text-xs text-slate-400 dark:text-slate-600 px-5 py-4">All fields identical.</p>
                                )}
                            </div>
                        )}
                    </Section>

                    {/* ── Agent State Section ─────────────────────────────────── */}
                    <Section
                        icon={<Bot className="w-4 h-4" />}
                        title="Agent States"
                        subtitle={`${result.agent_state_diffs.length} agent${result.agent_state_diffs.length !== 1 ? 's' : ''} tracked`}
                        badge={
                            <div className="flex gap-1.5 mr-2">
                                <SummaryBadge count={result.agent_state_diffs.filter(a => a.status === 'added').length} status="added" />
                                <SummaryBadge count={result.agent_state_diffs.filter(a => a.status === 'removed').length} status="removed" />
                                <SummaryBadge count={result.agent_state_diffs.filter(a => a.status === 'changed').length} status="changed" />
                            </div>
                        }
                    >
                        {result.agent_state_diffs.length === 0 ? (
                            <p className="text-xs text-slate-400 dark:text-slate-600 px-5 py-4">No agent states recorded.</p>
                        ) : (
                            result.agent_state_diffs.map(a => (
                                <AgentDiffBlock key={a.agent_id} agent={a} hideUnchanged={hideUnchanged} />
                            ))
                        )}
                    </Section>

                    {/* ── Artifacts Section ───────────────────────────────────── */}
                    <Section
                        icon={<PackageOpen className="w-4 h-4" />}
                        title="Artifacts"
                        subtitle={`${result.artifact_diffs.length} artifact${result.artifact_diffs.length !== 1 ? 's' : ''}`}
                        badge={
                            <div className="flex gap-1.5 mr-2">
                                <SummaryBadge count={result.artifact_diffs.filter(a => a.status === 'added').length} status="added" />
                                <SummaryBadge count={result.artifact_diffs.filter(a => a.status === 'removed').length} status="removed" />
                                <SummaryBadge count={result.artifact_diffs.filter(a => a.status === 'changed').length} status="changed" />
                            </div>
                        }
                    >
                        {result.artifact_diffs.length === 0 ? (
                            <p className="text-xs text-slate-400 dark:text-slate-600 px-5 py-4">No artifacts recorded.</p>
                        ) : (
                            result.artifact_diffs.map(a => (
                                <ArtifactDiffBlock key={a.key} artifact={a} hideUnchanged={hideUnchanged} />
                            ))
                        )}
                    </Section>
                </div>
            )}

            {/* ── Prompt state ─────────────────────────────────────────────────── */}
            {!result && !isLoading && !error && (
                <div className="flex flex-col items-center justify-center py-16 gap-3 text-slate-400 dark:text-slate-600">
                    <GitCompareArrows className="w-10 h-10 opacity-40" />
                    <p className="text-sm">Enter two branch names above and click Compare</p>
                    <p className="text-xs text-slate-300 dark:text-slate-700">
                        Each branch's latest checkpoint will be diffed
                    </p>
                </div>
            )}
        </div>
    );
};

export default BranchDiffView;
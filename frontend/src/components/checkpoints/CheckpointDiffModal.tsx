import { showToast } from '@/hooks/useToast';
import React, { useState, useEffect } from 'react';
import { AlertCircle, X, ChevronRight, ChevronDown, Plus, Minus, FileText } from 'lucide-react';
import { checkpointsService, BranchCompareResult, FieldDiff, AgentStateDiff, ArtifactDiff } from '../../services/checkpoints';
import { toast } from 'react-hot-toast';

interface CheckpointDiffModalProps {
    taskId?: string;
    leftBranch: string;
    rightBranch: string;
    onClose: () => void;
}

// ─── Shared Components ───────────────────────────────────────────────────────

const DiffBadge: React.FC<{ type: 'added' | 'removed' | 'changed' | 'unchanged', count?: number }> = ({ type, count }) => {
    if (count === 0) return null;
    
    const colors = {
        added: 'bg-emerald-100 text-emerald-800 dark:bg-emerald-500/20 dark:text-emerald-300 border-emerald-200 dark:border-emerald-500/30',
        removed: 'bg-rose-100 text-rose-800 dark:bg-rose-500/20 dark:text-rose-300 border-rose-200 dark:border-rose-500/30',
        changed: 'bg-amber-100 text-amber-800 dark:bg-amber-500/20 dark:text-amber-300 border-amber-200 dark:border-amber-500/30',
        unchanged: 'bg-slate-100 text-slate-600 dark:bg-slate-700/50 dark:text-slate-400 border-slate-200 dark:border-slate-600',
    };
    
    const labels = {
        added: '+ Added',
        removed: '- Removed',
        changed: '~ Changed',
        unchanged: '= Unchanged',
    };

    return (
        <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium border ${colors[type]}`}>
            {labels[type]} {count !== undefined ? `(${count})` : ''}
        </span>
    );
};

const ValueDisplay: React.FC<{ value: any; isDiff?: boolean; type?: 'added' | 'removed' }> = ({ value, isDiff, type }) => {
    const isObj = typeof value === 'object' && value !== null;
    const text = isObj ? JSON.stringify(value, null, 2) : String(value);
    
    let bgClass = 'bg-slate-50 dark:bg-[#0f1117]';
    let textClass = 'text-slate-700 dark:text-slate-300';
    let borderClass = 'border-slate-200 dark:border-[#1e2535]';

    if (isDiff) {
        if (type === 'added') {
            bgClass = 'bg-emerald-50 dark:bg-emerald-900/10';
            textClass = 'text-emerald-800 dark:text-emerald-300';
            borderClass = 'border-emerald-200 dark:border-emerald-800/30';
        } else if (type === 'removed') {
            bgClass = 'bg-rose-50 dark:bg-rose-900/10';
            textClass = 'text-rose-800 dark:text-rose-300';
            borderClass = 'border-rose-200 dark:border-rose-800/30';
        }
    }

    return (
        <pre className={`text-xs font-mono border rounded-lg p-2 overflow-auto max-h-40 whitespace-pre-wrap break-all transition-colors ${bgClass} ${textClass} ${borderClass}`}>
            {text}
        </pre>
    );
};

const FieldDiffView: React.FC<{ diff: FieldDiff }> = ({ diff }) => {
    if (diff.status === 'unchanged') return null;

    return (
        <div className="mb-4 last:mb-0">
            <div className="flex items-center gap-2 mb-1">
                <span className="text-sm font-semibold font-mono text-slate-700 dark:text-slate-200">{diff.key}</span>
                <DiffBadge type={diff.status} />
            </div>
            
            {diff.status === 'added' ? (
                <ValueDisplay value={diff.right} isDiff type="added" />
            ) : diff.status === 'removed' ? (
                <ValueDisplay value={diff.left} isDiff type="removed" />
            ) : (
                <div className="grid grid-cols-2 gap-2">
                    <div>
                        <div className="text-xs text-slate-500 mb-1">Previous ({diff.key})</div>
                        <ValueDisplay value={diff.left} isDiff type="removed" />
                    </div>
                    <div>
                        <div className="text-xs text-slate-500 mb-1">New ({diff.key})</div>
                        <ValueDisplay value={diff.right} isDiff type="added" />
                    </div>
                </div>
            )}
        </div>
    );
};

// ─── Main Modal Component ────────────────────────────────────────────────────

export const CheckpointDiffModal: React.FC<CheckpointDiffModalProps> = ({
    taskId, leftBranch, rightBranch, onClose
}) => {
    const [result, setResult] = useState<BranchCompareResult | null>(null);
    const [isLoading, setIsLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [activeTab, setActiveTab] = useState<'task' | 'agents' | 'artifacts'>('task');

    useEffect(() => {
        let isMounted = true;
        const fetchDiff = async () => {
            try {
                const data = await checkpointsService.compareBranches(leftBranch, rightBranch, taskId);
                if (isMounted) setResult(data);
            } catch (err: any) {
                if (isMounted) {
                    const msg = err?.response?.data?.detail || err?.message || 'Failed to compare branches';
                    setError(msg);
                    showToast.error(msg);
                }
            } finally {
                if (isMounted) setIsLoading(false);
            }
        };
        fetchDiff();
        return () => { isMounted = false; };
    }, [taskId, leftBranch, rightBranch]);

    // Derived counts
    const hasTaskDiffs = result?.task_state_diffs.some(d => d.status !== 'unchanged');
    const changedAgents = result?.agent_state_diffs.filter(a => a.status !== 'unchanged') || [];
    const changedArtifacts = result?.artifact_diffs.filter(a => a.status !== 'unchanged') || [];

    return (
        <div 
            className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm p-4"
            onClick={onClose}
        >
            <div 
                className="bg-white dark:bg-[#161b27] border border-slate-200 dark:border-[#1e2535] rounded-2xl shadow-2xl w-full max-w-5xl max-h-[90vh] flex flex-col"
                onClick={e => e.stopPropagation()}
            >
                {/* Header */}
                <div className="flex items-center justify-between px-6 py-4 border-b border-slate-200 dark:border-[#1e2535] bg-slate-50/50 dark:bg-[#1e2535]/20 rounded-t-2xl">
                    <div className="flex-1">
                        <div className="flex items-center gap-3">
                            <h2 className="text-lg font-bold text-slate-900 dark:text-white flex items-center gap-2">
                                <GitBranch className="w-5 h-5 text-violet-500" />
                                Branch Comparison
                            </h2>
                            <span className="text-slate-400 dark:text-slate-500 mx-1">/</span>
                            <div className="flex items-center gap-2 font-mono text-sm">
                                <span className="px-2 py-0.5 rounded bg-rose-100 text-rose-700 dark:bg-rose-500/10 dark:text-rose-400 border border-rose-200 dark:border-rose-500/20">{leftBranch}</span>
                                <ChevronRight className="w-4 h-4 text-slate-400" />
                                <span className="px-2 py-0.5 rounded bg-emerald-100 text-emerald-700 dark:bg-emerald-500/10 dark:text-emerald-400 border border-emerald-200 dark:border-emerald-500/20">{rightBranch}</span>
                            </div>
                        </div>
                        {result && (
                            <div className="flex items-center gap-2 mt-2">
                                <DiffBadge type="added" count={result.summary.added} />
                                <DiffBadge type="removed" count={result.summary.removed} />
                                <DiffBadge type="changed" count={result.summary.changed} />
                            </div>
                        )}
                    </div>
                    <button 
                        onClick={onClose}
                        className="p-2 text-slate-400 hover:text-slate-600 hover:bg-slate-100 dark:hover:text-slate-300 dark:hover:bg-[#1e2535] rounded-xl transition-colors"
                    >
                        <X className="w-5 h-5" />
                    </button>
                </div>

                {/* Body elements */}
                {isLoading ? (
                    <div className="flex-1 flex flex-col items-center justify-center p-12 text-slate-400">
                        <LoadingSpinner size="lg" />
                        <p>Computing diffs...</p>
                    </div>
                ) : error ? (
                    <div className="flex-1 flex flex-col items-center justify-center p-12 text-center">
                        <AlertCircle className="w-10 h-10 text-rose-500 mb-4 opacity-80" />
                        <p className="text-rose-600 dark:text-rose-400 font-medium mb-2">{error}</p>
                        <button 
                            onClick={onClose}
                            className="text-sm px-4 py-2 bg-slate-100 dark:bg-slate-800 rounded-lg hover:bg-slate-200 dark:hover:bg-slate-700 transition-colors"
                        >
                            Close
                        </button>
                    </div>
                ) : !result ? null : (
                    <div className="flex-1 flex flex-col min-h-0">
                        
                        {/* Tabs */}
                        <div className="flex px-6 space-x-4 border-b border-slate-200 dark:border-[#1e2535]">
                            <button
                                onClick={() => setActiveTab('task')}
                                className={`px-4 py-3 text-sm font-medium border-b-2 transition-colors ${activeTab === 'task' ? 'border-violet-500 text-violet-600 dark:text-violet-400' : 'border-transparent text-slate-500 hover:text-slate-700 dark:hover:text-slate-300'}`}
                            >
                                Task State {hasTaskDiffs ? <span className="ml-1 text-xs px-1.5 py-0.5 rounded-full bg-violet-100 text-violet-600 dark:bg-violet-500/20 dark:text-violet-400">Changed</span> : ''}
                            </button>
                            <button
                                onClick={() => setActiveTab('agents')}
                                className={`px-4 py-3 text-sm font-medium border-b-2 transition-colors ${activeTab === 'agents' ? 'border-violet-500 text-violet-600 dark:text-violet-400' : 'border-transparent text-slate-500 hover:text-slate-700 dark:hover:text-slate-300'}`}
                            >
                                Agent States {changedAgents.length > 0 ? <span className="ml-1 text-xs px-1.5 py-0.5 rounded-full bg-violet-100 text-violet-600 dark:bg-violet-500/20 dark:text-violet-400">{changedAgents.length}</span> : ''}
                            </button>
                            <button
                                onClick={() => setActiveTab('artifacts')}
                                className={`px-4 py-3 text-sm font-medium border-b-2 transition-colors ${activeTab === 'artifacts' ? 'border-violet-500 text-violet-600 dark:text-violet-400' : 'border-transparent text-slate-500 hover:text-slate-700 dark:hover:text-slate-300'}`}
                            >
                                Artifacts {changedArtifacts.length > 0 ? <span className="ml-1 text-xs px-1.5 py-0.5 rounded-full bg-violet-100 text-violet-600 dark:bg-violet-500/20 dark:text-violet-400">{changedArtifacts.length}</span> : ''}
                            </button>
                        </div>

                        {/* Scrollable Content Area */}
                        <div className="flex-1 overflow-y-auto p-6 bg-slate-50/50 dark:bg-[#0f1117]/50">
                            
                            {/* TASK STATE */}
                            {activeTab === 'task' && (
                                <div className="space-y-2">
                                    {!hasTaskDiffs ? (
                                        <div className="text-center py-8 text-slate-500 dark:text-slate-400">
                                            No differences in Task State between these branches.
                                        </div>
                                    ) : (
                                        <div className="bg-white dark:bg-[#161b27] border border-slate-200 dark:border-[#1e2535] rounded-xl p-5 shadow-sm">
                                            {result.task_state_diffs.map((diff, i) => (
                                                <FieldDiffView key={i} diff={diff} />
                                            ))}
                                        </div>
                                    )}
                                </div>
                            )}

                            {/* AGENT STATES */}
                            {activeTab === 'agents' && (
                                <div className="space-y-4">
                                    {changedAgents.length === 0 ? (
                                        <div className="text-center py-8 text-slate-500 dark:text-slate-400">
                                            No differences in Agent States between these branches.
                                        </div>
                                    ) : (
                                        changedAgents.map((agentDiff, i) => (
                                            <div key={i} className="bg-white dark:bg-[#161b27] border border-slate-200 dark:border-[#1e2535] rounded-xl overflow-hidden shadow-sm">
                                                <div className="px-5 py-3 border-b border-slate-100 dark:border-[#1e2535] bg-slate-50/80 dark:bg-[#1e2535]/30 flex items-center gap-3">
                                                    <h3 className="font-mono text-sm font-bold text-slate-800 dark:text-slate-200 flex-1">
                                                        Agent: {agentDiff.agent_id}
                                                    </h3>
                                                    <DiffBadge type={agentDiff.status} />
                                                </div>
                                                <div className="p-5">
                                                    {agentDiff.diffs.filter(d => d.status !== 'unchanged').map((d, j) => (
                                                        <FieldDiffView key={j} diff={d} />
                                                    ))}
                                                    {agentDiff.diffs.filter(d => d.status !== 'unchanged').length === 0 && (
                                                        <div className="text-xs text-slate-500">No field-level diffs parsed.</div>
                                                    )}
                                                </div>
                                            </div>
                                        ))
                                    )}
                                </div>
                            )}

                            {/* ARTIFACTS */}
                            {activeTab === 'artifacts' && (
                                <div className="space-y-4">
                                    {changedArtifacts.length === 0 ? (
                                        <div className="text-center py-8 text-slate-500 dark:text-slate-400">
                                            No differences in Artifacts between these branches.
                                        </div>
                                    ) : (
                                        changedArtifacts.map((artDiff, i) => (
                                            <div key={i} className="bg-white dark:bg-[#161b27] border border-slate-200 dark:border-[#1e2535] rounded-xl overflow-hidden shadow-sm">
                                                <div className="px-5 py-3 border-b border-slate-100 dark:border-[#1e2535] bg-slate-50/80 dark:bg-[#1e2535]/30 flex items-center gap-3">
                                                    <FileText className="w-4 h-4 text-slate-400" />
                                                    <h3 className="font-mono text-sm font-bold text-slate-800 dark:text-slate-200 flex-1">
                                                        Artifact: {artDiff.key}
                                                    </h3>
                                                    <DiffBadge type={artDiff.status} />
                                                </div>
                                                <div className="p-5">
                                                    <FieldDiffView diff={{
                                                        key: artDiff.key,
                                                        status: artDiff.status,
                                                        left: artDiff.left,
                                                        right: artDiff.right
                                                    }} />
                                                </div>
                                            </div>
                                        ))
                                    )}
                                </div>
                            )}

                        </div>
                    </div>
                )}
            </div>
        </div>
    );
};

// Required wrapper to provide GitBranch icon
import { GitBranch } from 'lucide-react';
import { LoadingSpinner } from '@/components/ui/LoadingSpinner';
